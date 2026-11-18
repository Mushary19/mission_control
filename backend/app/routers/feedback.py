"""/api/feedback: post, list, export."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse

from app.config import Settings, get_settings
from app.db import FeedbackDB, get_feedback_db
from app.schemas.feedback import Feedback, FeedbackIn, FeedbackList
from app.services import feedback as svc
from app.store import Store, get_store

router = APIRouter(prefix="/api", tags=["feedback"])
DB = Annotated[FeedbackDB, Depends(get_feedback_db)]


@router.post(
    "/feedback",
    response_model=Feedback,
    status_code=201,
    summary="Confirm / reject / add a step, or answer an open question",
)
def post_feedback(
    item: FeedbackIn,
    store: Annotated[Store, Depends(get_store)],
    db: DB,
    settings: Annotated[Settings, Depends(get_settings)],
) -> Feedback:
    return svc.submit(store, db, settings.feedback_jsonl, item)


@router.get("/feedback", response_model=FeedbackList)
def get_feedback(
    db: DB,
    target: str | None = None,
    case_id: str | None = None,
    process: str | None = None,
    user: str | None = None,
) -> FeedbackList:
    items = svc.list_feedback(db, target=target, case_id=case_id, process=process, user=user)
    return FeedbackList(count=len(items), items=items)


@router.get("/feedback/export", response_class=PlainTextResponse, summary="All feedback as JSONL (download)")
def export_feedback(db: DB) -> PlainTextResponse:
    return PlainTextResponse(
        svc.export_jsonl(db),
        media_type="application/x-ndjson",
        headers={"Content-Disposition": 'attachment; filename="feedback.jsonl"'},
    )
