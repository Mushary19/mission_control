"""/api/people/{person_id}."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.schemas.person import PersonDetail
from app.services.people import person_detail
from app.store import Store, get_store

router = APIRouter(prefix="/api", tags=["people"])


@router.get("/people/{person_id}", response_model=PersonDetail)
def person(person_id: str, store: Annotated[Store, Depends(get_store)]) -> PersonDetail:
    return person_detail(store, person_id)
