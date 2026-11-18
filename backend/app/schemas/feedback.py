"""Staff feedback on steps, cases, insights, identities and open questions."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from app.schemas.common import Model, Process

FeedbackTarget = Literal["process_step", "case_step", "case", "open_question", "insight", "identity"]
Verdict = Literal["confirm", "reject", "add", "answer"]


class FeedbackIn(Model):
    user: str = Field(description="Who is reviewing (no auth; picked in the UI)", examples=["Hana Pemberton"])
    target: FeedbackTarget
    verdict: Verdict
    process: Process | None = None
    case_id: str | None = None
    activity: str | None = None
    event_id: str | None = None
    question_id: str | None = None
    insight_id: str | None = None
    person_id: str | None = None
    other_person_id: str | None = Field(None, description="identity feedback: the possible_same_person counterpart")
    note: str = ""
    proposed_step: dict[str, Any] | None = Field(None, description='verdict "add": e.g. {"activity": "...", "after": "...", "description": "..."}')


class Feedback(FeedbackIn):
    id: str
    created_at: datetime


class FeedbackList(Model):
    count: int
    items: list[Feedback]
