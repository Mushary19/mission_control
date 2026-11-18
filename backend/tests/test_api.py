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


@pytest.mark.skipif(not HAS_DATA, reason="data/ export not present")
def test_event_raw(client: TestClient) -> None:
    c = ok(client, f"/api/cases/{BRAM}")
    mail = next(s for s in c["steps"] if s["source"] == "mail")
    r = ok(client, f"/api/events/{mail['event_id']}/raw")
    line = (ROOT / r["lines"][0]["file"]).read_text(encoding="utf-8").split("\n")[r["lines"][0]["line"] - 1]
    assert r["lines"][0]["raw"] == line  # unchanged
    sess = next(s for s in c["steps"] if s["source"] == "screen")
    rs = ok(client, f"/api/events/{sess['event_id']}/raw")
    assert rs["line_count"] == sess["session"]["frame_count"]


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
    assert len([p for p in spec["paths"] if p.startswith("/api/")]) == 11
    assert client.get("/docs").status_code == 200
