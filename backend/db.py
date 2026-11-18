"""Feedback store: SQLite (backend/feedback.db) + an append-only copy in out/feedback.jsonl."""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from schemas import Feedback, FeedbackIn

COLUMNS = ["id", "created_at", "user", "target", "verdict", "process", "case_id", "activity", "event_id", "question_id", "insight_id", "person_id", "other_person_id", "note", "proposed_step"]


class FeedbackStore:
    def __init__(self, db_path: Path, jsonl_path: Path):
        self.db_path, self.jsonl_path = Path(db_path), Path(jsonl_path)
        self.lock = threading.Lock()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            c.execute(
                "CREATE TABLE IF NOT EXISTS feedback ("
                "id TEXT PRIMARY KEY, created_at TEXT NOT NULL, user TEXT NOT NULL, target TEXT NOT NULL, verdict TEXT NOT NULL,"
                "process TEXT, case_id TEXT, activity TEXT, event_id TEXT, question_id TEXT, insight_id TEXT, person_id TEXT,"
                "other_person_id TEXT, note TEXT, proposed_step TEXT)"
            )

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def add(self, item: FeedbackIn) -> Feedback:
        fb = Feedback(id=uuid.uuid4().hex[:12], created_at=datetime.now(timezone.utc), **item.model_dump())
        row = fb.model_dump(mode="json")
        values = [json.dumps(row[k]) if k == "proposed_step" and row[k] is not None else row[k] for k in COLUMNS]
        with self.lock:
            with self._conn() as c:
                c.execute(f"INSERT INTO feedback ({','.join(COLUMNS)}) VALUES ({','.join('?' * len(COLUMNS))})", values)
            self.jsonl_path.parent.mkdir(parents=True, exist_ok=True)
            with self.jsonl_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        return fb

    def list(self, **filters) -> list[Feedback]:
        where = [(k, v) for k, v in filters.items() if v is not None]
        sql = "SELECT * FROM feedback" + (" WHERE " + " AND ".join(f"{k} = ?" for k, _ in where) if where else "") + " ORDER BY created_at, id"
        with self._conn() as c:
            rows = c.execute(sql, [v for _, v in where]).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["proposed_step"] = json.loads(d["proposed_step"]) if d["proposed_step"] else None
            out.append(Feedback(**d))
        return out
