"""/api/cases."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.schemas.case import CaseDetail, CaseSummary
from app.services import cases as svc
from app.services.filters import filter_cases
from app.store import Store, get_store

router = APIRouter(prefix="/api", tags=["cases"])


@router.get("/cases", response_model=list[CaseSummary])
def cases(
    store: Annotated[Store, Depends(get_store)],
    process: str | None = None,
    status: str | None = None,
    flagged: bool | None = None,
    q: str | None = Query(None, description="search person, client, case id, summary"),
) -> list[CaseSummary]:
    return [svc.case_summary(store, c) for c in filter_cases(store, process, status, flagged, q)]


@router.get(
    "/cases/{case_id}",
    response_model=CaseDetail,
    summary="One case: steps with confidence, likely flag, resolution reason; flags",
)
def case_detail(case_id: str, store: Annotated[Store, Depends(get_store)]) -> CaseDetail:
    return svc.case_detail(store, case_id)
