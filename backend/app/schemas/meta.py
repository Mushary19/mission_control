"""Coverage, export window and pipeline counts."""

from __future__ import annotations

from pydantic import Field

from app.schemas.common import Model


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
