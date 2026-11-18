"""Case summaries and the case detail view."""

from __future__ import annotations

from app.schemas.case import CaseDetail, CaseStep, CaseSummary
from app.schemas.common import PersonRef
from app.store import Doc, Store


def case_summary(store: Store, c: Doc) -> CaseSummary:
    """One row of the case list."""
    return CaseSummary(
        case_id=c["case_id"],
        process=c["process"],
        subject_person_id=c["subject_person_id"],
        subject_name=c["subject_name"],
        client=c.get("client"),
        client_name=store.org_name(c.get("client")),
        owner_staff_id=c.get("owner_staff_id"),
        owner_name=store.name(c.get("owner_staff_id")),
        status=c["status"],
        started_before_window=c["started_before_window"],
        ends_after_window=c["ends_after_window"],
        step_count=len(c["steps"]),
        flag_count=len(c["flags"]),
        start=c["start"],
        last_activity=c["last_activity"],
        summary=c["summary"],
    )


def case_step(store: Store, step: Doc) -> CaseStep:
    """A case step plus the title, text and person resolution of its event."""
    event = store.events.get(step["event_id"], {})
    fields = {k: v for k, v in step.items() if k in CaseStep.model_fields}
    return CaseStep(**fields, title=event.get("title"), text=event.get("text"), resolution=event.get("resolution"))


def case_detail(store: Store, case_id: str) -> CaseDetail:
    """Steps with confidence, flags (own and on the person's other cases), insights."""
    c = store.get_case(case_id)
    return CaseDetail(
        **case_summary(store, c).model_dump(),
        key=c["key"],
        handoff=c["handoff"],
        window_notes=c["window_notes"],
        staff_involved=[PersonRef(person_id=p, name=store.name(p)) for p in c["staff_involved"]],
        steps=[case_step(store, st) for st in c["steps"]],
        flags=[store.flag_by_id[f] for f in c["flags"]],
        related_flags=[f for f in store.flags if f["person_id"] == c["subject_person_id"] and f["case_id"] != case_id],
        insights=store.case_insights.get(case_id, []),
        out_of_order=c["out_of_order"],
    )
