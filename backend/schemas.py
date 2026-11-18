"""Pydantic v2 models. These ARE the documented schemas (docs/schemas.md is written from them).

Pipeline files (out/) and API responses share these shapes.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Process = Literal["leave", "offboarding", "onboarding"]
Status = Literal["complete", "in_progress", "declined", "cancelled"]
Confidence = Literal["high", "medium", "low"]
Source = Literal["mail", "calendar", "teams_chat", "teams_channel", "screen"]
Category = Literal["process", "context", "noise", "out_of_scope"]
PersonKind = Literal["staff", "it", "worker", "new_starter", "client", "vendor", "candidate", "unknown"]


class Model(BaseModel):
    model_config = ConfigDict(populate_by_name=True)


# ----------------------------------------------------------------------------- pipeline: events + people


class RawRef(Model):
    file: str = Field(description="Path of the raw export file, relative to the repo root (data/...)")
    line: int = Field(description="1-based line number in that file")


class Session(Model):
    start_local: str
    end_local: str
    start_utc: str
    end_utc: str
    frame_count: int
    minutes: float


class Resolution(Model):
    method: str = Field(description="email | sender | chat_member | thread | full_name | initial | first_name_unique | fuzzy | context | chat_pair | ambiguous | unresolved")
    confidence: Confidence | None = None
    reason: str | None = Field(None, description="Plain sentence: why this person was chosen")
    raw_name: str | None = None
    candidates: list[str] = []


class Event(Model):
    """One row of out/1_events.jsonl and out/2_events_clean.jsonl (null / empty keys are omitted in the files)."""

    event_id: str = Field(description='"<source>:<native id>"; screen sessions use "screen:<mailbox>:<first line>"')
    source: Source
    mailbox: str
    seen_in: list[str] = []
    time_utc: str
    time_local: str = Field(description="Asia/Colombo (UTC+05:30)")
    actor_id: str | None = None
    recipients: list[str] = []
    title: str | None = None
    text: str | None = Field(None, description="Plain text, cut to 200 chars; the full record is served by /api/events/{id}/raw")
    text_truncated: bool = False
    category: Category | None = None
    noise_reason: str | None = None
    activity: str | None = None
    process: Process | None = None
    subject_person_id: str | None = None
    resolution: Resolution | None = None
    fields: dict[str, Any] = {}
    thread_key: str | None = None
    raw_ref: RawRef
    session: Session | None = None
    meta: dict[str, Any] = {}


class PersonRef(Model):
    person_id: str | None
    name: str | None


class PossibleSame(Model):
    person_id: str
    name: str | None = None
    reason: str


class Person(Model):
    person_id: str
    display_name: str
    emails: list[str] = []
    kind: PersonKind
    org: str | None = None
    org_name: str | None = None
    exported: bool = False
    job_title: str | None = None
    merged_ids: list[str] = []
    merge_reason: str | None = None
    possible_same_person: list[PossibleSame] = []


# ----------------------------------------------------------------------------- cases


class Flag(Model):
    flag_id: str
    rule: str
    scope: Literal["case", "process"]
    severity: str
    case_id: str | None = None
    process: Process | None = None
    person_id: str | None = None
    person_name: str | None = None
    message: str
    evidence_event_ids: list[str]


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


# ----------------------------------------------------------------------------- processes + insights


class MainPath(Model):
    activities: list[str]
    labels: list[str]
    method: str
    cases_following_exactly: int
    tied_alternatives: list[dict[str, Any]] = []


class ProcessStep(Model):
    activity: str
    label: str
    support_pct: float
    case_count: int
    confidence_mix: dict[str, int]
    on_main_path: bool
    optional: bool
    median_from_case_start_h: float | None = None
    median_to_next_h: float | None = None
    next_on_main_path: str | None = None
    screen_only: bool


class DfgEdge(Model):
    from_: str = Field(alias="from")
    to: str
    count: int


class Variant(Model):
    path: list[str]
    count: int
    case_ids: list[str]
    statuses: dict[str, int]


class OpenQuestion(Model):
    id: str
    process: Process
    question: str
    why: str
    evidence: dict[str, Any] = {}


class PathConfidence(Model):
    level: Confidence
    reason: str
    rule: str


class InsightCase(Model):
    case_id: str
    person_name: str | None = None
    rules: list[str]
    message: str
    flag_ids: list[str]


class Insight(Model):
    id: str
    kind: Literal["process_insight", "case_flag"]
    process: Process | None
    title: str
    message: str
    rules: list[str]
    affected_case_ids: list[str]
    evidence_event_ids: list[str]
    severity: Literal["info", "warning"]
    per_case: list[InsightCase] = []
    eligible_cases: int | None = None


class ProcessSummary(Model):
    process: Process
    label: str
    case_count: int
    status_counts: dict[str, int]
    window_badges: dict[str, int]
    full_trace_cases: int
    path_confidence: PathConfidence
    main_path_labels: list[str]
    open_question_count: int
    insight_count: int


class ProcessDetail(ProcessSummary):
    main_path: MainPath
    steps: list[ProcessStep]
    dfg: list[DfgEdge]
    variants: list[Variant]
    open_questions: list[OpenQuestion]
    insights: list[Insight]


# ----------------------------------------------------------------------------- meta + raw


class StaffRef(Model):
    name: str
    job_title: str
    folder: str | None = None


class Coverage(Model):
    staff_total: int
    staff_exported: int
    label: str = Field(description='Always shown in the UI, e.g. "Data from 6 of 12 staff."')
    exported: list[StaffRef]
    not_exported: list[StaffRef]


class Window(Model):
    start: str
    end: str
    timezone: str
    note: str | None = None


class SeenNotModelled(Model):
    key: str
    label: str
    events: int = Field(description="mail / calendar / Teams records")
    screen_sessions: int


class Meta(Model):
    coverage: Coverage
    window: Window
    timezone_note: str
    stage_counts: dict[str, int]
    seen_not_modelled: list[SeenNotModelled]
    out_files: list[str]


class RawLine(Model):
    file: str
    line: int
    raw: str = Field(description="The original line, byte-for-byte as in the export")
    record: dict[str, Any] = Field(description="The same line parsed as JSON")


class RawResponse(Model):
    event_id: str
    source: Source
    line_count: int
    lines: list[RawLine]


class PersonDetail(Person):
    cases: list[CaseSummary]


# ----------------------------------------------------------------------------- feedback

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
