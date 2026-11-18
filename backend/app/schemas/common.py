"""Shared base model and enums."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

Process = Literal["leave", "offboarding", "onboarding"]
Status = Literal["complete", "in_progress", "declined", "cancelled"]
Confidence = Literal["high", "medium", "low"]
Source = Literal["mail", "calendar", "teams_chat", "teams_channel", "screen"]
Category = Literal["process", "context", "noise", "out_of_scope"]
PersonKind = Literal["staff", "it", "worker", "new_starter", "client", "vendor", "candidate", "unknown"]


class Model(BaseModel):
    model_config = ConfigDict(populate_by_name=True)


class PersonRef(Model):
    person_id: str | None
    name: str | None
