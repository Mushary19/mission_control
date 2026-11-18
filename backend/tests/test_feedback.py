"""Feedback round trip (post, list, filter, export, JSONL copy) and validation."""

from __future__ import annotations

import json

from conftest import BRAM, ok
from fastapi.testclient import TestClient


def test_feedback_round_trip(client: TestClient) -> None:
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
