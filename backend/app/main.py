"""Mission Control API: FastAPI app, CORS, routers, startup.

Run:  uvicorn app.main:app --app-dir backend --reload      (API at /api, docs at /docs)
Paths and CORS origins come from app.config (env vars MC_OUT_DIR, MC_DATA_DIR, MC_DB, MC_FEEDBACK_JSONL, MC_CORS).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import load_settings
from app.db import FeedbackDB
from app.routers import cases, events, feedback, insights, meta, people, processes
from app.store import Store

DESCRIPTION = (
    "Process intelligence for the Harbourline Talent People team (synthetic data, 2–29 Mar 2026). "
    "Data from 6 of 12 staff. All times in Sri Lanka time (UTC+05:30). Read-only pipeline outputs + staff feedback."
)


def create_app(
    out_dir: Path | None = None,
    data_dir: Path | None = None,
    db_path: Path | None = None,
    feedback_jsonl: Path | None = None,
) -> FastAPI:
    """Build the app. Arguments override the env/default paths (tests use this)."""
    settings = load_settings(out_dir, data_dir, db_path, feedback_jsonl)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.store = Store.load(settings.out_dir, settings.data_dir)
        app.state.feedback_db = FeedbackDB(settings.db_path)
        yield

    app = FastAPI(title="Mission Control API", version="0.4.0", description=DESCRIPTION, lifespan=lifespan)
    app.state.settings = settings
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["GET", "POST"], allow_headers=["*"])
    for module in (meta, processes, cases, events, insights, people, feedback):
        app.include_router(module.router)
    return app


app = create_app()
