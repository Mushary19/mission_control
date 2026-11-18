"""List filtering: cases (filters + free-text search), insights and flags."""

from __future__ import annotations

from app.store import Doc, Store


def case_is_flagged(store: Store, case: Doc) -> bool:
    """A case is flagged if it has its own flags or is part of a process insight."""
    return bool(case["flags"]) or bool(store.case_insights.get(case["case_id"]))


def case_matches_query(store: Store, case: Doc, q: str) -> bool:
    """Case-insensitive substring search over case id, person, client name and summary."""
    hay = " ".join([case["case_id"], case["subject_name"], store.org_name(case.get("client")) or "", case["summary"]])
    return q.lower() in hay.lower()


def filter_cases(
    store: Store,
    process: str | None = None,
    status: str | None = None,
    flagged: bool | None = None,
    q: str | None = None,
) -> list[Doc]:
    """Cases matching every given filter, most recent activity first."""
    return [
        c
        for c in sorted(store.cases.values(), key=lambda c: c["last_activity"], reverse=True)
        if (not process or c["process"] == process)
        and (not status or c["status"] == status)
        and (flagged is None or case_is_flagged(store, c) == flagged)
        and (not q or case_matches_query(store, c, q))
    ]


def filter_insights(store: Store, process: str | None = None, kind: str | None = None) -> list[Doc]:
    """Insights, optionally limited to one process and/or kind."""
    return [i for i in store.insights if (not process or i["process"] == process) and (not kind or i["kind"] == kind)]


def filter_flags(store: Store, rule: str | None = None, process: str | None = None) -> list[Doc]:
    """Flag rule hits, optionally limited to one rule and/or process."""
    return [f for f in store.flags if (not rule or f["rule"] == rule) and (not process or f["process"] == process)]
