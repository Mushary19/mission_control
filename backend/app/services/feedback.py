"""Feedback: validate against the store, save to SQLite, append to feedback.jsonl, export as JSONL."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from app.db import FeedbackDB
from app.schemas.feedback import Feedback, FeedbackIn
from app.store import Store


def _require(ok: object, message: str) -> None:
    if not ok:
        raise HTTPException(422, message)


def validate(store: Store, item: FeedbackIn) -> None:
    """422 unless the feedback points at things that exist and carries what its verdict needs."""
    _require(item.user.strip(), "user is required")
    _require((item.verdict == "answer") == (item.target == "open_question"), 'verdict "answer" is used for open questions (and only for them)')
    if item.target == "open_question":
        _require(item.question_id in store.questions, "unknown question_id")
        _require(item.note.strip(), "an answer needs text in note")
    if item.target == "insight":
        _require(item.insight_id in store.insight_by_id, "unknown insight_id")
    if item.target == "identity":
        _require(item.person_id in store.people and item.other_person_id in store.people, "identity feedback needs person_id and other_person_id")
    if item.target in ("case", "case_step"):
        _require(item.case_id in store.cases, "unknown case_id")
    if item.target == "case_step" and item.verdict != "add":
        _require(item.event_id in {st["event_id"] for st in store.cases[item.case_id]["steps"]}, "event_id is not a step of this case")
    if item.target == "process_step":
        _require(item.process in store.processes, "process_step feedback needs a process")
        activities = {x["activity"] for x in store.processes[item.process]["steps"]}
        _require(item.verdict == "add" or item.activity in activities, "unknown activity for this process")
    if item.verdict == "add":
        _require(item.proposed_step or item.note.strip(), 'verdict "add" needs proposed_step or a note')


def _jsonl_line(row: dict[str, Any]) -> str:
    return json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"


def submit(store: Store, db: FeedbackDB, jsonl_path: Path, item: FeedbackIn) -> Feedback:
    """Validate, store in SQLite and append to the JSONL copy. Returns the saved feedback."""
    validate(store, item)
    fb = Feedback(id=uuid.uuid4().hex[:12], created_at=datetime.now(timezone.utc), **item.model_dump())
    row = fb.model_dump(mode="json")
    db_row = {**row, "proposed_step": json.dumps(row["proposed_step"]) if row["proposed_step"] is not None else None}
    with db.write_lock:
        db.insert(db_row)
        jsonl_path.parent.mkdir(parents=True, exist_ok=True)
        with jsonl_path.open("a", encoding="utf-8") as fh:
            fh.write(_jsonl_line(row))
    return fb


def list_feedback(db: FeedbackDB, **filters: str | None) -> list[Feedback]:
    """Saved feedback matching every given column filter, oldest first."""
    items = []
    for row in db.select(filters):
        row["proposed_step"] = json.loads(row["proposed_step"]) if row["proposed_step"] else None
        items.append(Feedback(**row))
    return items


def export_jsonl(db: FeedbackDB) -> str:
    """All feedback, one JSON object per line."""
    return "".join(_jsonl_line(f.model_dump(mode="json")) for f in list_feedback(db))
