"""Flags (rule hits) and insights (grouped flags)."""

from __future__ import annotations

from typing import Literal

from app.schemas.common import Model, Process


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
