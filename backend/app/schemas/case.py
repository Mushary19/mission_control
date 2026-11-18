"""Cases: one person going through one process."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from app.schemas.common import Confidence, Model, PersonRef, Process, Source, Status
from app.schemas.event import RawRef, Resolution, Session
from app.schemas.insight import Flag


class CaseStep(Model):
    activity: str
    label: str
    event_id: str
    time_local: str
    actor_id: str | None = None
    actor_name: str | None = None
    source: Source
    confidence: Confidence
    likely: bool = Field(description="True for screen-based steps: the screen shows what was open, not what was done")
    link: str = Field(description="How the step joined the case: thread | dates | person | time")
    link_reason: str
    raw_ref: RawRef
    session: Session | None = None
    title: str | None = None
    text: str | None = None
    resolution: Resolution | None = None


class CaseSummary(Model):
    case_id: str
    process: Process
    subject_person_id: str
    subject_name: str
    client: str | None = None
    client_name: str | None = None
    owner_staff_id: str | None = None
    owner_name: str | None = None
    status: Status
    started_before_window: bool
    ends_after_window: bool
    step_count: int
    flag_count: int
    start: str
    last_activity: str
    summary: str


class CaseDetail(CaseSummary):
    key: dict[str, Any]
    staff_involved: list[PersonRef]
    handoff: bool
    window_notes: list[str]
    steps: list[CaseStep]
    flags: list[Flag]
    related_flags: list[Flag] = Field([], description="flags on this person's other cases (cross-process, e.g. leave after the last day)")
    insights: list[str] = Field(description="ids of process insights that include this case")
    out_of_order: list[dict[str, Any]]
