"""Writes docs/schemas.md from the Pydantic models in backend/app/schemas/ plus real examples
(out/ files for the pipeline shapes, the API for the response shapes).

Run: .venv/bin/python scripts/gen_schemas.py
"""

from __future__ import annotations

import json
import sys
import tempfile
import typing
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.main import create_app
from app.schemas import case, event, feedback, insight, meta, person, process
from fastapi.testclient import TestClient
from pydantic import BaseModel

OUT = ROOT / "out"


def type_name(ann: object) -> str:
    s = ann.__name__ if isinstance(ann, type) and not typing.get_args(ann) else repr(ann)
    s = s.replace("typing.", "").replace("app.schemas.", "")
    for mod in ("case.", "event.", "feedback.", "insight.", "meta.", "person.", "process.", "common."):
        s = s.replace(mod, "")
    s = s.replace("NoneType", "None").replace("<class '", "").replace("'>", "")
    return s


def fields_table(model: type[BaseModel]) -> str:
    rows = ["| field | type | required | description |", "|---|---|---|---|"]
    hints = typing.get_type_hints(model)
    for name, f in model.model_fields.items():
        alias = f.alias or name
        rows.append(f"| `{alias}` | `{type_name(hints.get(name, f.annotation))}` | {'yes' if f.is_required() else 'no'} | {(f.description or '').replace('|', '/')} |")
    return "\n".join(rows)


def trim(obj, depth=0):
    """Shorten long lists/strings so examples stay readable."""
    if isinstance(obj, list):
        out = [trim(x, depth + 1) for x in obj[:2]]
        if len(obj) > 2:
            out.append(f"… {len(obj) - 2} more")
        return out
    if isinstance(obj, dict):
        return {k: trim(v, depth + 1) for k, v in obj.items()}
    if isinstance(obj, str) and len(obj) > 140:
        return obj[:140] + "…"
    return obj


def block(obj) -> str:
    return "```json\n" + json.dumps(trim(obj), indent=2, ensure_ascii=False) + "\n```"


def jsonl_first(path: Path, pred) -> dict:
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            e = json.loads(line)
            if pred(e):
                return e
    raise LookupError(path)


def main() -> None:
    tmp = Path(tempfile.mkdtemp())
    app = create_app(db_path=tmp / "fb.db", feedback_jsonl=tmp / "fb.jsonl")
    with TestClient(app) as c:
        get = lambda u: c.get(u).json()
        posted = c.post("/api/feedback", json={"user": "Hana Pemberton", "target": "case_step", "verdict": "confirm", "case_id": "offboarding:bram-montague",
                                               "event_id": get("/api/cases/offboarding:bram-montague")["steps"][-1]["event_id"], "note": "Yes, completed that day."}).json()
        bram = get("/api/cases/offboarding:bram-montague")
        sections = [
            ("Pipeline: event (`out/1_events.jsonl`, `out/2_events_clean.jsonl`)",
             "One row per deduplicated record or screen session. Keys that are null or empty are left out of the files. `text` is cut to 200 characters; `/api/events/{id}/raw` returns the full original line(s).",
             event.Event, jsonl_first(OUT / "2_events_clean.jsonl", lambda e: e.get("activity") == "laptop_received")),
            ("Pipeline: screen session (inside an event)", "Frames of one window (same mailbox + title, gaps <= 10 min).", event.Session,
             jsonl_first(OUT / "2_events_clean.jsonl", lambda e: e["source"] == "screen" and e.get("session", {}).get("frame_count", 0) > 1)["session"]),
            ("Pipeline: resolution (inside an event)", "How the person the event is about was found, with a plain reason.", event.Resolution,
             jsonl_first(OUT / "2_events_clean.jsonl", lambda e: (e.get("resolution") or {}).get("method") == "context")["resolution"]),
            ("Pipeline: person (`out/2_people.json` → `people[]`)", "Built from every address and display name seen. `possible_same_person` lists records kept apart on purpose.", person.Person,
             next(p for p in json.loads((OUT / "2_people.json").read_text())["people"] if p.get("possible_same_person"))),
            ("Case (`out/3_cases.json` → `cases[]`, `GET /api/cases/{id}`)", "Status is the outcome only; window badges say whether steps fall outside 2–29 March.", case.CaseDetail, bram),
            ("Case step", "Every step links to a raw record (`raw_ref`).", case.CaseStep, bram["steps"][-1]),
            ("Case summary (`GET /api/cases`)", "", case.CaseSummary, get("/api/cases?q=bram")[0]),
            ("Process model (`out/4_processes.json`, `GET /api/processes/{process}`)", "", process.ProcessDetail, get("/api/processes/leave")),
            ("Process step", "", process.ProcessStep, get("/api/processes/leave")["steps"][0]),
            ("Variant", "", process.Variant, get("/api/processes/leave")["variants"][1]),
            ("Open question", "", process.OpenQuestion, get("/api/processes/leave")["open_questions"][1]),
            ("Path confidence", "", process.PathConfidence, get("/api/processes/onboarding")["path_confidence"]),
            ("Flag (`out/5_flags.json`, `GET /api/flags`)", "A rule hit with plain-English message and evidence.", insight.Flag, get("/api/flags?rule=activity_after_last_day")[0]),
            ("Insight (`out/6_insights.json`, `GET /api/insights`)", "`process_insight` = a pattern across cases; `case_flag` = one case.", insight.Insight,
             next(i for i in get("/api/insights") if i["id"] == "ins:onboarding:laptop_late")),
            ("Meta (`GET /api/meta`)", "", meta.Meta, get("/api/meta")),
            ("Raw record (`GET /api/events/{id}/raw`)", "The original export line(s), unchanged, plus the parsed record.", event.RawResponse,
             c.get(f"/api/events/{bram['steps'][-1]['event_id']}/raw").json()),
            ("Person detail (`GET /api/people/{id}`)", "", person.PersonDetail, get("/api/people/p_luca-bellweather")),
            ("Feedback in (`POST /api/feedback`)", "Targets: process_step, case_step, case, open_question, insight, identity. Verdicts: confirm, reject, add, answer (open questions only).",
             feedback.FeedbackIn, {k: v for k, v in posted.items() if k not in ("id", "created_at")}),
            ("Feedback (stored in SQLite and appended to `out/feedback.jsonl`)", "", feedback.Feedback, posted),
        ]
    parts = [
        "# Schemas",
        "",
        ("Generated by `scripts/gen_schemas.py` from the Pydantic models in [`backend/app/schemas/`](../backend/app/schemas/) "
        "with real examples from `out/` and the API (long lists cut to 2 items). Times: `*_local` = Sri Lanka time (UTC+05:30), `*_utc` = UTC."),
        "",
        ("Other `out/` files: `0_profile.json` (record counts, time formats and duplicates per person and source), "
        "`2_screen_summary.json` (context / noise / out-of-scope screen sessions per mailbox, title and day), "
        "`pipeline_report.json` (counts per stage and phase summaries)."),
        "",
    ]
    for title, note, model, example in sections:
        parts += [f"## {title}", ""]
        if note:
            parts += [note, ""]
        parts += [fields_table(model), "", "Example:", "", block(example), ""]
    (ROOT / "docs" / "schemas.md").write_text("\n".join(parts), encoding="utf-8")
    print("wrote docs/schemas.md")


if __name__ == "__main__":
    main()
