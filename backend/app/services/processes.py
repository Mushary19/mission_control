"""Process summaries and detail views."""

from __future__ import annotations

from app.schemas.process import ProcessDetail, ProcessSummary
from app.store import Doc, Store

PROCESS_LABELS = {"leave": "Leave", "offboarding": "Offboarding", "onboarding": "Onboarding"}


def process_summary(store: Store, p: Doc) -> ProcessSummary:
    """Headline numbers for one process."""
    return ProcessSummary(
        process=p["process"],
        label=PROCESS_LABELS[p["process"]],
        case_count=p["case_count"],
        status_counts=p["status_counts"],
        window_badges=p["window_badges"],
        full_trace_cases=p["full_trace_cases"],
        path_confidence=p["path_confidence"],
        main_path_labels=p["main_path"]["labels"],
        open_question_count=len(p["open_questions"]),
        insight_count=len(store.process_insights(p["process"])),
    )


def list_processes(store: Store) -> list[ProcessSummary]:
    """Summaries of every discovered process."""
    return [process_summary(store, p) for p in store.processes.values()]


def process_detail(store: Store, process: str) -> ProcessDetail:
    """Main path, steps, DFG, variants, open questions and insights of one process."""
    p = store.get_process(process)
    return ProcessDetail(
        **process_summary(store, p).model_dump(),
        main_path=p["main_path"],
        steps=p["steps"],
        dfg=p["dfg"],
        variants=p["variants"],
        open_questions=p["open_questions"],
        insights=store.process_insights(process),
    )
