"""The /api/meta payload: coverage, export window, stage counts, what was seen but not modelled."""

from __future__ import annotations

from app.schemas.meta import Coverage, Meta, SeenNotModelled, StaffRef, Window
from app.store import Store

SEEN_NOT_MODELLED = [  # (key, label, substring of noise_reason)
    ("recruiting", "Recruitment (HireTrack, Recruitment tracker, LinkedIn)", "recruitment"),
    ("birthdays", "Birthday gifts", "birthday"),
    ("laptop_replacements", "Laptop replacements", "laptop replacement"),
    ("payroll_queries", "Payslip / timesheet / invoice queries", "payslip"),
]


def _count_events(store: Store, needle: str) -> int:
    return sum(
        1 for e in store.events.values() if e.get("category") == "out_of_scope" and needle in (e.get("noise_reason") or "")
    )


def _count_screen_sessions(store: Store, needle: str) -> int:
    summary = store.screen_summary
    col = {name: i for i, name in enumerate(summary["columns"])}
    reasons = summary["reason_by_title"]
    return sum(
        r[col["sessions"]]
        for r in summary["rows"]
        if r[col["category"]] == "out_of_scope" and needle in (reasons.get(r[col["title"]]) or "")
    )


def seen_not_modelled(store: Store) -> list[SeenNotModelled]:
    """Out-of-scope work that shows up in the data, with record and screen-session counts."""
    return [
        SeenNotModelled(key=key, label=label, events=_count_events(store, needle), screen_sessions=_count_screen_sessions(store, needle))
        for key, label, needle in SEEN_NOT_MODELLED
    ]


def build_meta(store: Store) -> Meta:
    """Coverage, export window, pipeline stage counts and the list of out/ files."""
    cov = store.profile["coverage"]
    win = store.profile["export_window"]
    return Meta(
        coverage=Coverage(
            staff_total=cov["staff_in_directory"],
            staff_exported=cov["staff_exported"],
            label=cov["label"],
            exported=[StaffRef(name=x["name"], job_title=x["jobTitle"], folder=x["folder"]) for x in cov["exported"]],
            not_exported=[StaffRef(name=x["name"], job_title=x["jobTitle"]) for x in cov["not_exported"]],
        ),
        window=Window(start=win["start"], end=win["end"], timezone=win["timezone"], note=win.get("note")),
        timezone_note="All times in Sri Lanka time (UTC+05:30)",
        stage_counts={k: int(v) for k, v in store.report["stage_counts"].items()},
        seen_not_modelled=seen_not_modelled(store),
        out_files=sorted(
            p.name for p in store.out_dir.glob("*") if p.suffix in (".json", ".jsonl") and p.name != "feedback.jsonl"
        ),
    )
