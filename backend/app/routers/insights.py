"""/api/insights and /api/flags."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends

from app.schemas.insight import Flag, Insight
from app.services.filters import filter_flags, filter_insights
from app.store import Store, get_store

router = APIRouter(prefix="/api", tags=["insights"])


@router.get("/insights", response_model=list[Insight], summary="Process insights (systemic) and case flags (specific)")
def insights(
    store: Annotated[Store, Depends(get_store)], process: str | None = None, kind: str | None = None
) -> list[dict[str, Any]]:
    return filter_insights(store, process, kind)


@router.get("/flags", response_model=list[Flag], summary="Raw flag rule hits (before grouping into insights)")
def flags(
    store: Annotated[Store, Depends(get_store)], rule: str | None = None, process: str | None = None
) -> list[dict[str, Any]]:
    return filter_flags(store, rule, process)
