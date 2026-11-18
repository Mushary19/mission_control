"""/api/processes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.schemas.process import ProcessDetail, ProcessSummary
from app.services import processes as svc
from app.store import Store, get_store

router = APIRouter(prefix="/api", tags=["processes"])


@router.get("/processes", response_model=list[ProcessSummary])
def processes(store: Annotated[Store, Depends(get_store)]) -> list[ProcessSummary]:
    return svc.list_processes(store)


@router.get(
    "/processes/{process}",
    response_model=ProcessDetail,
    summary="Discovered process: main path, steps, DFG, variants, open questions, insights",
)
def process_detail(process: str, store: Annotated[Store, Depends(get_store)]) -> ProcessDetail:
    return svc.process_detail(store, process)
