"""One test per endpoint (status 200 + shape) and a feedback round trip. Uses the committed out/ files;
feedback goes to a temp SQLite + JSONL, never to backend/feedback.db."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
_TMP = Path(tempfile.mkdtemp())
os.environ.setdefault("MC_DB", str(_TMP / "default.db"))  # the module-level default app must not touch backend/feedback.db
os.environ.setdefault("MC_FEEDBACK_JSONL", str(_TMP / "default.jsonl"))
from app import create_app  # noqa: E402

BRAM = "offboarding:bram-montague"
HAS_DATA = (ROOT / "data" / "_shared" / "directory.json").exists()


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("fb")
    app = create_app(db_path=tmp / "feedback.db", feedback_jsonl=tmp / "feedback.jsonl")
    app.state.tmp = tmp
    with TestClient(app) as c:
        yield c


def ok(client, url):
    r = client.get(url)
    assert r.status_code == 200, (url, r.status_code, r.text[:300])
    return r.json()


def test_meta(client):
    m = ok(client, "/api/meta")
    assert m["coverage"]["label"] == "Data from 6 of 12 staff."
    assert m["coverage"]["staff_exported"] == 6 and len(m["coverage"]["not_exported"]) == 6
    assert {x["key"] for x in m["seen_not_modelled"]} == {"recruiting", "birthdays", "laptop_replacements", "payroll_queries"}
    assert m["stage_counts"]["raw"] == 11346


def test_processes(client):
    ps = ok(client, "/api/processes")
    assert [p["process"] for p in ps] == ["leave", "offboarding", "onboarding"]
    assert {p["process"]: p["path_confidence"]["level"] for p in ps}["onboarding"] == "low"


def test_process_detail(client):
    p = ok(client, "/api/processes/leave")
    assert p["main_path"]["activities"][0] == "leave_requested"
    assert p["variants"] and p["dfg"][0]["from"] and p["open_questions"][0]["id"].startswith("leave-q")
    assert client.get("/api/processes/recruiting").status_code == 404


def test_cases_list_and_filters(client):
    all_ = ok(client, "/api/cases")
    assert len(all_) == 70
    assert all(c["process"] == "leave" for c in ok(client, "/api/cases?process=leave"))
    assert all(c["status"] == "cancelled" for c in ok(client, "/api/cases?status=cancelled"))
    assert any(c["case_id"] == BRAM for c in ok(client, "/api/cases?q=bram"))
    flagged = ok(client, "/api/cases?flagged=true")
    assert flagged and len(flagged) < len(all_)


def test_case_detail(client):
    c = ok(client, f"/api/cases/{BRAM}")
    assert c["subject_name"] == "Bram Montague" and c["started_before_window"]
    acts = [s["activity"] for s in c["steps"]]
    assert "laptop_received" in acts and "offboarding_completed" in acts
    rec = next(s for s in c["steps"] if s["activity"] == "laptop_received")
    assert rec["resolution"]["method"] == "context" and rec["resolution"]["reason"]
    assert any(s["likely"] for s in c["steps"])
    assert any(f["rule"] == "activity_after_last_day" for f in c["related_flags"])  # leave approved after offboarding
    assert client.get("/api/cases/nope").status_code == 404


@pytest.mark.skipif(not HAS_DATA, reason="data/ export not present")
def test_event_raw(client):
    c = ok(client, f"/api/cases/{BRAM}")
    mail = next(s for s in c["steps"] if s["source"] == "mail")
    r = ok(client, f"/api/events/{mail['event_id']}/raw")
    line = (ROOT / r["lines"][0]["file"]).read_text(encoding="utf-8").split("\n")[r["lines"][0]["line"] - 1]
    assert r["lines"][0]["raw"] == line  # unchanged
    sess = next(s for s in c["steps"] if s["source"] == "screen")
    rs = ok(client, f"/api/events/{sess['event_id']}/raw")
    assert rs["line_count"] == sess["session"]["frame_count"]


def test_insights(client):
    ins = ok(client, "/api/insights")
    kinds = {i["kind"] for i in ins}
    assert kinds == {"process_insight", "case_flag"}
    assert any(i["id"] == "ins:onboarding:laptop_late" for i in ins)


def test_flags(client):
    fs = ok(client, "/api/flags")
    assert fs and all(f["evidence_event_ids"] for f in fs)


def test_person(client):
    p = ok(client, "/api/people/p_luca-bellweather")
    assert p["possible_same_person"] and p["possible_same_person"][0]["person_id"] == "p_luca-bellweather-personal"
    b = ok(client, "/api/people/p_bram-montague")
    assert {c["process"] for c in b["cases"]} == {"leave", "offboarding"}


def test_openapi_docs(client):
    spec = ok(client, "/openapi.json")
    assert len([p for p in spec["paths"] if p.startswith("/api/")]) == 11
    assert client.get("/docs").status_code == 200


def test_feedback_round_trip(client):
    posts = [
        {"user": "Hana Pemberton", "target": "case_step", "verdict": "confirm", "case_id": BRAM, "event_id": ok(client, f"/api/cases/{BRAM}")["steps"][3]["event_id"], "note": "Yes, I booked SwiftParcel for Bram."},
        {"user": "Hana Pemberton", "target": "open_question", "verdict": "answer", "process": "leave", "question_id": "leave-q1", "note": "In batches on Friday."},
        {"user": "Lerato Faraday", "target": "identity", "verdict": "confirm", "person_id": "p_luca-bellweather", "other_person_id": "p_luca-bellweather-personal", "note": "Same person."},
        {"user": "Lerato Faraday", "target": "process_step", "verdict": "add", "process": "onboarding", "proposed_step": {"activity": "dms_access_requested", "after": "it_ready", "description": "Ask the client for DMS access"}},
    ]
    ids = []
    for body in posts:
        r = client.post("/api/feedback", json=body)
        assert r.status_code == 201, r.text
        ids.append(r.json()["id"])
    got = ok(client, "/api/feedback")
    assert got["count"] == len(posts) and [x["id"] for x in got["items"]] == ids
    assert ok(client, f"/api/feedback?case_id={BRAM}")["count"] == 1
    exp = client.get("/api/feedback/export")
    assert exp.status_code == 200 and exp.headers["content-type"].startswith("application/x-ndjson")
    assert [json.loads(l)["id"] for l in exp.text.splitlines()] == ids
    jsonl = (client.app.state.tmp / "feedback.jsonl").read_text().splitlines()
    assert [json.loads(l)["id"] for l in jsonl] == ids
    # validation
    assert client.post("/api/feedback", json={"user": "Hana", "target": "case", "verdict": "answer", "case_id": BRAM}).status_code == 422
    assert client.post("/api/feedback", json={"user": "Hana", "target": "open_question", "verdict": "answer", "question_id": "nope", "note": "x"}).status_code == 422
