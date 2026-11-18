"""Settings: file locations and CORS origins, read from the environment with repo-relative defaults.

MC_OUT_DIR (out/), MC_DATA_DIR (data/), MC_DB (backend/feedback.db),
MC_FEEDBACK_JSONL (<out dir>/feedback.jsonl), MC_CORS (comma-separated origins).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from fastapi import Request

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CORS = "http://localhost:5173,http://127.0.0.1:5173"


@dataclass(frozen=True)
class Settings:
    out_dir: Path
    data_dir: Path
    db_path: Path
    feedback_jsonl: Path
    cors_origins: list[str]


def load_settings(
    out_dir: Path | None = None,
    data_dir: Path | None = None,
    db_path: Path | None = None,
    feedback_jsonl: Path | None = None,
) -> Settings:
    """Settings from explicit arguments, else the environment, else the defaults."""
    out = Path(out_dir or os.environ.get("MC_OUT_DIR", ROOT / "out"))
    return Settings(
        out_dir=out,
        data_dir=Path(data_dir or os.environ.get("MC_DATA_DIR", ROOT / "data")),
        db_path=Path(db_path or os.environ.get("MC_DB", ROOT / "backend" / "feedback.db")),
        feedback_jsonl=Path(feedback_jsonl or os.environ.get("MC_FEEDBACK_JSONL", out / "feedback.jsonl")),
        cors_origins=os.environ.get("MC_CORS", DEFAULT_CORS).split(","),
    )


def get_settings(request: Request) -> Settings:
    """FastAPI dependency: the app's settings."""
    return request.app.state.settings
