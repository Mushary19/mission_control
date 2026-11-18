"""Shared test setup: puts backend/ on sys.path and gives each test module its own client.

Uses the committed out/ files; feedback goes to a temp SQLite + JSONL, never to backend/feedback.db.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.main import create_app

BRAM = "offboarding:bram-montague"
HAS_DATA = (ROOT / "data" / "_shared" / "directory.json").exists()


def ok(client: TestClient, url: str) -> dict:
    """GET that must return 200; the parsed JSON body."""
    r = client.get(url)
    assert r.status_code == 200, (url, r.status_code, r.text[:300])
    return r.json()


def make_client(tmp: Path) -> TestClient:
    """A TestClient (use it as a context manager) whose feedback DB and JSONL live in `tmp`."""
    app = create_app(db_path=tmp / "feedback.db", feedback_jsonl=tmp / "feedback.jsonl")
    app.state.tmp = tmp
    return TestClient(app)


@pytest.fixture(scope="module")
def client(tmp_path_factory: pytest.TempPathFactory) -> Iterator[TestClient]:
    with make_client(tmp_path_factory.mktemp("fb")) as c:
        yield c
