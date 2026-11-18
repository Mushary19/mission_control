"""People (staff, workers, clients, ...) after identity resolution."""

from __future__ import annotations

from app.schemas.case import CaseSummary
from app.schemas.common import Model, PersonKind


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


class PersonDetail(Person):
    cases: list[CaseSummary]
