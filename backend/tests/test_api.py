"""One test per endpoint (status 200 + shape)."""

from __future__ import annotations

import pytest
from conftest import BRAM, HAS_DATA, ROOT, ok
from fastapi.testclient import TestClient


def test_meta(client: TestClient) -> None:
    m = ok(client, "/api/meta")
    assert m["coverage"]["label"] == "Data from 6 of 12 staff."
    assert m["coverage"]["staff_exported"] == 6 and len(m["coverage"]["not_exported"]) == 6
    assert {x["key"] for x in m["seen_not_modelled"]} == {"recruiting", "birthdays", "laptop_replacements", "payroll_queries"}
    assert m["stage_counts"]["raw"] == 11346


def test_processes(client: TestClient) -> None:
    ps = ok(client, "/api/processes")
    assert [p["process"] for p in ps] == ["leave", "offboarding", "onboarding"]
    assert {p["process"]: p["path_confidence"]["level"] for p in ps}["onboarding"] == "low"


def test_process_detail(client: TestClient) -> None:
    p = ok(client, "/api/processes/leave")
    assert p["main_path"]["activities"][0] == "leave_requested"
    assert p["variants"] and p["dfg"][0]["from"] and p["open_questions"][0]["id"].startswith("leave-q")
    assert client.get("/api/processes/recruiting").status_code == 404


def test_cases_list_and_filters(client: TestClient) -> None:
    all_ = ok(client, "/api/cases")
    assert len(all_) == 70
    assert all(c["process"] == "leave" for c in ok(client, "/api/cases?process=leave"))
    assert all(c["status"] == "cancelled" for c in ok(client, "/api/cases?status=cancelled"))
    assert any(c["case_id"] == BRAM for c in ok(client, "/api/cases?q=bram"))
    flagged = ok(client, "/api/cases?flagged=true")
    assert flagged and len(flagged) < len(all_)


def test_case_detail(client: TestClient) -> None:
    c = ok(client, f"/api/cases/{BRAM}")
    assert c["subject_name"] == "Bram Montague" and c["started_before_window"]
    acts = [s["activity"] for s in c["steps"]]
    assert "laptop_received" in acts and "offboarding_completed" in acts
    rec = next(s for s in c["steps"] if s["activity"] == "laptop_received")
    assert rec["resolution"]["method"] == "context" and rec["resolution"]["reason"]
    assert any(s["likely"] for s in c["steps"])
    assert any(f["rule"] == "activity_after_last_day" for f in c["related_flags"])  # leave approved after offboarding
    assert client.get("/api/cases/nope").status_code == 404


def test_event_raw_all_sources(fake_raw_client: TestClient) -> None:
    """Raw lines come back byte-for-byte from the FAKE fixture, for every source."""
    from fixtures.fake_raw import FAKE_DATA, FAKE_EVENTS

    for eid, (source, file, lines) in FAKE_EVENTS.items():
        r = ok(fake_raw_client, f"/api/events/{eid}/raw")
        assert r["source"] == source and r["line_count"] == len(lines)
        content = (FAKE_DATA / file.removeprefix("data/")).read_text(encoding="utf-8").split("\n")
        assert [x["raw"] for x in r["lines"]] == [content[n - 1] for n in lines]  # unchanged
        assert all(x["record"] for x in r["lines"])
    assert "Test Person" in ok(fake_raw_client, "/api/events/mail:fake-0001@test.example/raw")["lines"][0]["raw"]


@pytest.mark.skipif(not HAS_DATA, reason="data/ export not present")
def test_event_raw_real_export(client: TestClient) -> None:
    """With the real export present: a mail and a multi-frame screen session (nothing is stored in the repo)."""
    c = ok(client, f"/api/cases/{BRAM}")
    mail = next(s for s in c["steps"] if s["source"] == "mail")
    r = ok(client, f"/api/events/{mail['event_id']}/raw")
    line = (ROOT / r["lines"][0]["file"]).read_text(encoding="utf-8").split("\n")[r["lines"][0]["line"] - 1]
    assert r["lines"][0]["raw"] == line
    sess = next(s for s in c["steps"] if s["source"] == "screen")
    assert ok(client, f"/api/events/{sess['event_id']}/raw")["line_count"] == sess["session"]["frame_count"]


def test_insights(client: TestClient) -> None:
    ins = ok(client, "/api/insights")
    kinds = {i["kind"] for i in ins}
    assert kinds == {"process_insight", "case_flag"}
    assert any(i["id"] == "ins:onboarding:laptop_late" for i in ins)


def test_flags(client: TestClient) -> None:
    fs = ok(client, "/api/flags")
    assert fs and all(f["evidence_event_ids"] for f in fs)


def test_person(client: TestClient) -> None:
    p = ok(client, "/api/people/p_luca-bellweather")
    assert p["possible_same_person"] and p["possible_same_person"][0]["person_id"] == "p_luca-bellweather-personal"
    b = ok(client, "/api/people/p_bram-montague")
    assert {c["process"] for c in b["cases"]} == {"leave", "offboarding"}


def test_openapi_docs(client: TestClient) -> None:
    spec = ok(client, "/openapi.json")
    assert len([p for p in spec["paths"] if p.startswith("/api/")]) == 12
    assert client.get("/docs").status_code == 200


def test_out_files(client: TestClient) -> None:
    r = client.get("/api/files/3_cases.json")
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/json")
    assert r.json()["cases"]
    assert client.get("/api/files/1_events.jsonl").headers["content-type"].startswith("application/x-ndjson")
    for bad in ("feedback.jsonl", "..%2Fdata%2F_shared%2Fdirectory.json", "../README.md", "nope.json"):
        assert client.get(f"/api/files/{bad}").status_code == 404, bad


def test_raw_without_data_says_so(tmp_path) -> None:
    from app.main import create_app

    app = create_app(data_dir=tmp_path / "no-data", db_path=tmp_path / "fb.db", feedback_jsonl=tmp_path / "fb.jsonl")
    with TestClient(app) as c:
        eid = ok(c, f"/api/cases/{BRAM}")["steps"][-1]["event_id"]
        r = c.get(f"/api/events/{eid}/raw")
        assert r.status_code == 503 and "Raw data not available on this server" in r.json()["detail"]


def test_spa_fallback(tmp_path) -> None:
    from app.main import create_app

    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>Mission Control</title>")
    (dist / "assets" / "app.js").write_text("console.log(1)")
    import os

    os.environ["MC_FRONTEND_DIST"] = str(dist)
    try:
        app = create_app(db_path=tmp_path / "fb.db", feedback_jsonl=tmp_path / "fb.jsonl")
    finally:
        del os.environ["MC_FRONTEND_DIST"]
    with TestClient(app) as c:
        assert "Mission Control" in c.get("/").text
        assert "Mission Control" in c.get("/cases/offboarding:bram-montague").text  # client-side route
        assert c.get("/assets/app.js").text == "console.log(1)"
        assert c.get("/api/meta").status_code == 200
        assert c.get("/api/nope").status_code == 404
        assert c.get("/docs").status_code == 200
