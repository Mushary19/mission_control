"""/api/events/{event_id}/raw."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.schemas.event import RawResponse
from app.services.raw_reader import read_raw
from app.store import Store, get_store

router = APIRouter(prefix="/api", tags=["events"])


@router.get(
    "/events/{event_id:path}/raw",
    response_model=RawResponse,
    summary="The original raw line(s) from data/, unchanged (screen sessions: every frame)",
)
def raw(event_id: str, store: Annotated[Store, Depends(get_store)]) -> RawResponse:
    return read_raw(store, event_id)
