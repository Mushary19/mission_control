"""Discovered processes: main path, steps, DFG, variants, open questions."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from app.schemas.common import Confidence, Model, Process
from app.schemas.insight import Insight


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
