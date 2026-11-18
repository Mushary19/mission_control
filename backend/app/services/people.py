"""The person detail view."""

from __future__ import annotations

from app.schemas.person import PersonDetail, PossibleSame
from app.services.cases import case_summary
from app.store import Store

HIDDEN_FIELDS = ("possible_same_person", "teams_ids", "export_folder")


def person_detail(store: Store, person_id: str) -> PersonDetail:
    """A person, their possible duplicates (with names) and the cases they are the subject of."""
    p = store.get_person(person_id)
    same = [
        PossibleSame(person_id=x["person_id"], name=store.name(x["person_id"]), reason=x["reason"])
        for x in p.get("possible_same_person", [])
    ]
    return PersonDetail(
        **{k: v for k, v in p.items() if k not in HIDDEN_FIELDS},
        org_name=store.org_name(p.get("org")),
        possible_same_person=same,
        cases=[case_summary(store, c) for c in store.cases.values() if c["subject_person_id"] == person_id],
    )
