"""SQLite connection and the feedback table (backend/feedback.db by default)."""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Any

from fastapi import Request

COLUMNS = [
    "id", "created_at", "user", "target", "verdict", "process", "case_id", "activity", "event_id",
    "question_id", "insight_id", "person_id", "other_person_id", "note", "proposed_step",
]
SCHEMA = (
    "CREATE TABLE IF NOT EXISTS feedback ("
    "id TEXT PRIMARY KEY, created_at TEXT NOT NULL, user TEXT NOT NULL, target TEXT NOT NULL, verdict TEXT NOT NULL,"
    "process TEXT, case_id TEXT, activity TEXT, event_id TEXT, question_id TEXT, insight_id TEXT, person_id TEXT,"
    "other_person_id TEXT, note TEXT, proposed_step TEXT)"
)


class FeedbackDB:
    """The feedback table. `write_lock` serialises writes (the DB insert plus the JSONL append)."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.write_lock = threading.Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def insert(self, row: dict[str, Any]) -> None:
        """Insert one row; `row` holds a value for every column."""
        sql = f"INSERT INTO feedback ({','.join(COLUMNS)}) VALUES ({','.join('?' * len(COLUMNS))})"
        with self._connect() as conn:
            conn.execute(sql, [row[k] for k in COLUMNS])

    def select(self, filters: dict[str, str | None]) -> list[dict[str, Any]]:
        """Rows matching every non-None filter (column = value), oldest first."""
        where = [(k, v) for k, v in filters.items() if v is not None and k in COLUMNS]
        sql = "SELECT * FROM feedback"
        if where:
            sql += " WHERE " + " AND ".join(f"{k} = ?" for k, _ in where)
        with self._connect() as conn:
            rows = conn.execute(sql + " ORDER BY created_at, id", [v for _, v in where]).fetchall()
        return [dict(r) for r in rows]


def get_feedback_db(request: Request) -> FeedbackDB:
    """FastAPI dependency: the feedback DB opened at startup."""
    return request.app.state.feedback_db
