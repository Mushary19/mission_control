"""/api/meta and /api/health."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.schemas.meta import Meta
from app.services.meta import build_meta
from app.store import Store, get_store

router = APIRouter(prefix="/api", tags=["meta"])


@router.get("/meta", response_model=Meta, summary="Coverage, export window, pipeline counts")
def meta(store: Annotated[Store, Depends(get_store)]) -> Meta:
    return build_meta(store)


@router.get("/health", include_in_schema=False)
def health() -> dict[str, bool]:
    return {"ok": True}
