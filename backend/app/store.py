"""The pipeline outputs in out/, loaded once at startup and only read afterwards."""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import HTTPException, Request

Doc = dict[str, Any]


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[Doc]:
    with path.open(encoding="utf-8") as fh:
        return [json.loads(line) for line in fh]


@dataclass(frozen=True)
class Store:
    """Everything the API serves. Treat every container as read-only."""

    out_dir: Path
    data_dir: Path
    profile: Doc
    report: Doc
    screen_summary: Doc
    people: dict[str, Doc]
    orgs: dict[str, Doc]
    cases: dict[str, Doc]
    processes: dict[str, Doc]
    events: dict[str, Doc]
    flags: list[Doc]
    insights: list[Doc]
    flag_by_id: dict[str, Doc]
    insight_by_id: dict[str, Doc]
    case_insights: dict[str, list[str]]  # case_id -> ids of process insights that include it
    questions: dict[str, Doc]  # open-question id -> question

    @classmethod
    def load(cls, out_dir: Path, data_dir: Path) -> Store:
        """Read out/*.json(l) and build the lookup indexes."""
        out = Path(out_dir)
        people_doc = _read_json(out / "2_people.json")
        processes = {p["process"]: p for p in _read_json(out / "4_processes.json")["processes"]}
        flags = _read_json(out / "5_flags.json")["flags"]
        insights = _read_json(out / "6_insights.json")["insights"]
        case_insights: defaultdict[str, list[str]] = defaultdict(list)
        for i in insights:
            if i["kind"] == "process_insight":
                for cid in i["affected_case_ids"]:
                    case_insights[cid].append(i["id"])
        return cls(
            out_dir=out,
            data_dir=Path(data_dir),
            profile=_read_json(out / "0_profile.json"),
            report=_read_json(out / "pipeline_report.json"),
            screen_summary=_read_json(out / "2_screen_summary.json"),
            people={p["person_id"]: p for p in people_doc["people"]},
            orgs={o["org_id"]: o for o in people_doc["orgs"]},
            cases={c["case_id"]: c for c in _read_json(out / "3_cases.json")["cases"]},
            processes=processes,
            events={e["event_id"]: e for e in _read_jsonl(out / "2_events_clean.jsonl")},
            flags=flags,
            insights=insights,
            flag_by_id={f["flag_id"]: f for f in flags},
            insight_by_id={i["id"]: i for i in insights},
            case_insights=dict(case_insights),
            questions={q["id"]: q for p in processes.values() for q in p["open_questions"]},
        )

    # ------------------------------------------------------------------ lookups (404 when missing)

    def get_process(self, process: str) -> Doc:
        """One discovered process."""
        return _get(self.processes, process, f"unknown process {process!r}")

    def get_case(self, case_id: str) -> Doc:
        """One case."""
        return _get(self.cases, case_id, f"unknown case {case_id!r}")

    def get_event(self, event_id: str) -> Doc:
        """One clean event (context/noise screen sessions are not stored individually)."""
        return _get(self.events, event_id, f"unknown event {event_id!r} (context/noise screen sessions are only summarised)")

    def get_person(self, person_id: str) -> Doc:
        """One person."""
        return _get(self.people, person_id, f"unknown person {person_id!r}")

    # ------------------------------------------------------------------ names

    def name(self, person_id: str | None) -> str | None:
        """Display name of a person id, or None."""
        return self.people.get(person_id, {}).get("display_name") if person_id else None

    def org_name(self, org_id: str | None) -> str | None:
        """Name of an org id, or None."""
        return self.orgs.get(org_id, {}).get("name") if org_id else None

    def process_insights(self, process: str) -> list[Doc]:
        """Insights that belong to one process."""
        return [i for i in self.insights if i["process"] == process]


def _get(index: dict[str, Doc], key: str, missing: str) -> Doc:
    doc = index.get(key)
    if not doc:
        raise HTTPException(404, missing)
    return doc


def get_store(request: Request) -> Store:
    """FastAPI dependency: the store loaded at startup."""
    return request.app.state.store
