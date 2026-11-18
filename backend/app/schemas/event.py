"""Events (out/1_events.jsonl, out/2_events_clean.jsonl) and raw export lines."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from app.schemas.common import Category, Confidence, Model, Process, Source


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
