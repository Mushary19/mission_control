"""Writes docs/schemas.md: for each pipeline step its input, output file, schema (field · type · meaning), one real
example and the rules that apply; then feedback, the API and ID conventions. Field tables come from the Pydantic
models in backend/app/schemas/ where one exists, otherwise from the hand-written tables below; examples come
from out/ and the API. The raw-record example comes from the
FAKE fixture in backend/tests/fixtures/data (invented people); this script never reads the real data/.

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
sys.path.insert(0, str(ROOT / "backend" / "tests"))

from app.main import create_app
from app.schemas import case, event, feedback, insight, meta, person, process
from fastapi.testclient import TestClient
from fixtures.fake_raw import FAKE_DATA, build_out
from pydantic import BaseModel

OUT = ROOT / "out"


# Meanings for fields whose Pydantic model has no description. "Model.field" wins over "field".
MEANING = {
    "activities": "activity ids in order", "activity": "activity id, e.g. `it_ready`", "actor_id": "person id of who did it",
    "actor_name": "display name of who did it", "affected_case_ids": "cases the insight covers", "candidates": "person ids that fit the name",
    "case_count": "cases containing it", "case_id": "case id (see ID conventions)", "case_ids": "cases following this variant",
    "cases_following_exactly": "complete in-window cases whose steps match the main path exactly", "category": "`process`, `context`, `noise` or `out_of_scope`",
    "confidence": "`high`, `medium` or `low`", "confidence_mix": "steps per confidence level", "DfgEdge.count": "times `from` is directly followed by `to`",
    "Variant.count": "cases with this exact sequence", "coverage": "staff in the directory vs. exported", "display_name": "name shown in the UI",
    "emails": "every address seen for this person", "eligible_cases": "cases the rule could apply to", "end_local": "last frame, local time",
    "end_utc": "last frame, UTC", "event_id": "event id (see ID conventions)", "evidence": "the numbers behind the question",
    "evidence_event_ids": "events that prove the flag", "exported": "their mailbox is in the export", "fields": "values extracted by the rule (dates, client, needed-by, `rule_id`)",
    "flag_id": "flag id (see ID conventions)", "flag_ids": "flags behind this line", "frame_count": "screen frames in the session",
    "from": "activity before", "id": "id (see ID conventions)", "insight_id": "insight the feedback is about", "job_title": "from the staff directory",
    "kind": "type of record", "Insight.kind": "`process_insight` (pattern) or `case_flag` (one case)", "Person.kind": "`staff`, `it`, `worker`, `new_starter`, `client`, `vendor`, `candidate`, `unknown`",
    "label": "readable activity name", "labels": "readable names of the main path", "level": "`high`, `medium` or `low`",
    "line_count": "number of raw lines (screen sessions: one per frame)", "lines": "the raw lines", "link_reason": "plain sentence: why the step joined this case",
    "mailbox": "the exported mailbox the record came from", "median_from_case_start_h": "median hours from case start to this step",
    "median_to_next_h": "median hours to the next main-path step", "merge_reason": "why records were merged", "merged_ids": "person ids merged into this one",
    "message": "plain-English explanation", "meta": "source-specific extras (chat members, raw line numbers of screen frames)", "method": "how the main path was chosen",
    "minutes": "session length", "next_on_main_path": "the following main-path activity", "noise_reason": "why it is noise or out of scope",
    "note": "free-text comment or answer", "on_main_path": "the step is on the main path", "optional": "under 50% support or off the main path",
    "org": "org id", "org_name": "organisation name", "out_files": "pipeline files in out/", "path": "activity ids in order",
    "per_case": "one line per affected case", "person_id": "person id (see ID conventions)", "person_name": "display name", "possible_same_person": "records that may be the same person, with a reason",
    "process": "`leave`, `offboarding` or `onboarding`", "question": "the question for staff", "question_id": "open question being answered",
    "raw_name": "the name as written", "raw_ref": "file + line of the original record", "reason": "plain-English reason", "recipients": "person ids it was sent to",
    "resolution": "how `subject_person_id` was found", "rule": "rule id", "Flag.rule": "rule that fired (table below)", "rules": "rule ids involved",
    "scope": "`case` or `process`", "screen_only": "seen only on screens", "seen_in": "mailboxes that had a copy", "seen_not_modelled": "out-of-scope work found, with counts",
    "session": "screen session details (screen events only)", "severity": "`info` or `warning`", "source": "`mail`, `calendar`, `teams_chat`, `teams_channel` or `screen`",
    "stage_counts": "record counts per pipeline stage", "start_local": "first frame, local time", "start_utc": "first frame, UTC",
    "statuses": "cases per status", "subject_person_id": "person the record is about", "support_pct": "% of the process's cases containing the step",
    "target": "what the feedback is about", "text": "message text, cut to 200 characters", "text_truncated": "`text` was cut",
    "thread_key": "conversation key used to join replies", "tied_alternatives": "other variants with the same support", "time_local": "Sri Lanka time (UTC+05:30)",
    "time_utc": "UTC", "timezone_note": "shown under every time", "title": "subject, meeting title or window title", "Insight.title": "short headline",
    "to": "activity after", "verdict": "`confirm`, `reject`, `add` or `answer`", "why": "what in the data raised it", "window": "export window",
}


def type_name(ann: object) -> str:
    s = ann.__name__ if isinstance(ann, type) and not typing.get_args(ann) else repr(ann)
    s = s.replace("typing.", "").replace("app.schemas.", "")
    for mod in ("case.", "event.", "feedback.", "insight.", "meta.", "person.", "process.", "common."):
        s = s.replace(mod, "")
    s = s.replace("NoneType", "None").replace("<class '", "").replace("'>", "")
    s = s.replace("Optional[", "").replace(" | None", "")
    if s.endswith("]") and s.count("[") < s.count("]"):
        s = s[:-1]
    s = s.replace("Literal[", "one of [").replace("str", "string").replace("dict[string, Any]", "object")
    return s.replace("|", "\\|")


def fields_table(model: type[BaseModel]) -> str:
    rows = ["| field | type | required | meaning |", "|---|---|---|---|"]
    hints = typing.get_type_hints(model)
    for name, f in model.model_fields.items():
        alias = f.alias or name
        meaning = f.description or MEANING.get(f"{model.__name__}.{alias}") or MEANING.get(alias, "")
        rows.append(f"| `{alias}` | `{type_name(hints.get(name, f.annotation))}` | {'yes' if f.is_required() else 'no'} | {meaning.replace('|', '/').replace('<', '&lt;')} |")
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


def table(rows: list[tuple[str, str, str]]) -> str:
    """Hand-written field table for out/ shapes that have no Pydantic model."""
    return "\n".join(["| field | type | meaning |", "|---|---|---|"] + [f"| `{f}` | `{t}` | {m} |" for f, t, m in rows]).replace(" / ", " · ")


def load(name: str):
    return json.loads((OUT / name).read_text(encoding="utf-8"))


def sample_link(name: str) -> str:
    return f"[sample](../out/samples/{name.split('.')[0]}.sample.json)"


TOBIAS = "teams_chat:19:f28c105d-3926-4a17-aa09-f29d953f48f1_6bf46c69-0a09-4f64-aab1-c3ba13deef86@unq.gbl.spaces:1773025571882"
CHIARA = "onboarding:chiara-ekwueme"


def main() -> None:
    tmp = Path(tempfile.mkdtemp())
    # data_dir = the fake fixture: the real export is never read here
    app = create_app(out_dir=build_out(tmp), data_dir=FAKE_DATA, db_path=tmp / "fb.db", feedback_jsonl=tmp / "fb.jsonl")
    with TestClient(app) as c:
        get = lambda u: c.get(u).json()
        posted = c.post("/api/feedback", json={"user": "Lerato Faraday", "target": "case_step", "verdict": "confirm", "case_id": CHIARA,
                                               "event_id": TOBIAS, "activity": "it_ready", "process": "onboarding",
                                               "note": "Yes, Tobias confirmed IT was ready."}).json()
        raw = get("/api/events/teams_chat:19:fake-sam_fake-it@unq.gbl.spaces:1000000000001/raw")
        meta_ex = get("/api/meta")

    profile, people, cases_doc = load("0_profile.json"), load("2_people.json"), load("3_cases.json")
    procs, flags, insights = load("4_processes.json"), load("5_flags.json"), load("6_insights.json")
    screen, report = load("2_screen_summary.json"), load("pipeline_report.json")
    sc = report["stage_counts"]
    chiara = next(x for x in cases_doc["cases"] if x["case_id"] == CHIARA)
    onboarding = next(p for p in procs["processes"] if p["process"] == "onboarding")
    leave = next(p for p in procs["processes"] if p["process"] == "leave")
    rule_counts: dict[str, int] = {}
    for f in flags["flags"]:
        rule_counts[f["rule"]] = rule_counts.get(f["rule"], 0) + 1

    md: list[str] = []
    add = md.extend
    add([
        "# Schemas and outputs",
        "",
        ("Generated by [`scripts/gen_schemas.py`](../scripts/gen_schemas.py); do not edit by hand. For each pipeline step: what it reads, the file it writes, "
        "the fields, one real example (long lists cut to 2 items) and the rules that apply. Field tables come from the Pydantic models in "
        "[`backend/app/schemas/`](../backend/app/schemas/) where one exists. Small readable samples of every file are in [`out/samples/`](../out/samples/) "
        "([`scripts/make_samples.py`](../scripts/make_samples.py))."),
        "",
        "| step | reads | writes | records | sample |",
        "|---|---|---|---|---|",
        f"| 0 Profile | `data/` | [`0_profile.json`](../out/0_profile.json) | {profile['totals']['raw_records']:,} raw records counted | {sample_link('0_profile.json')} |",
        f"| 1 Ingest | `data/` | [`1_events.jsonl`](../out/1_events.jsonl) | {sc['1_events (non-screen)']:,} events (+ {sc['screen_sessions']:,} screen sessions kept for step 2) | {sample_link('1_events.jsonl')} |",
        f"| 2 Clean | step 1 | [`2_events_clean.jsonl`](../out/2_events_clean.jsonl) | {sum(1 for _ in (OUT / '2_events_clean.jsonl').open(encoding='utf-8')):,} events | {sample_link('2_events_clean.jsonl')} |",
        f"| | | [`2_people.json`](../out/2_people.json) | {len(people['people'])} people, {len(people['orgs'])} organisations | {sample_link('2_people.json')} |",
        f"| | | [`2_screen_summary.json`](../out/2_screen_summary.json) | {len(screen['rows']):,} rows ({sum(v['sessions'] for v in screen['totals'].values()):,} sessions) | {sample_link('2_screen_summary.json')} |",
        f"| 3 Cases | step 2 | [`3_cases.json`](../out/3_cases.json) | {len(cases_doc['cases'])} cases, {sc['case_steps']} steps | {sample_link('3_cases.json')} |",
        f"| 4 Discover | step 3 | [`4_processes.json`](../out/4_processes.json) | {len(procs['processes'])} process models, {sum(len(p['open_questions']) for p in procs['processes'])} open questions | {sample_link('4_processes.json')} |",
        f"| 5 Flags | steps 2–4 | [`5_flags.json`](../out/5_flags.json) | {len(flags['flags'])} flags | {sample_link('5_flags.json')} |",
        f"| | | [`pipeline_report.json`](../out/pipeline_report.json) | counts per stage | {sample_link('pipeline_report.json')} |",
        f"| 6 Insights | step 5 | [`6_insights.json`](../out/6_insights.json) | {insights['counts']['process_insight']} patterns, {insights['counts']['case_flag']} case flags | {sample_link('6_insights.json')} |",
        "| runtime | the UI | `backend/feedback.db`, `out/feedback.jsonl` | one row per feedback | – |",
        "",
        ("**Conventions.** `*_local` times are Sri Lanka time (UTC+05:30), `*_utc` times are UTC. Keys that are null or empty are left out of the "
        "`.jsonl` files. Message `text` is cut to 200 characters; `GET /api/events/{id}/raw` returns the full original line(s). Every `.json` file except `pipeline_report.json` has a "
        "`step` key naming the step that wrote it."),
        "",
        "## ID conventions",
        "",
        "| id | format | example |",
        "|---|---|---|",
        "| `event_id` | `<source>:<native id>`: mail `internetMessageId`, calendar `iCalUId`, Teams chat `chatId:messageId`, Teams channel message id | `teams_channel:1772439208663` |",
        "| screen `event_id` | `screen:<mailbox>:<line of the first frame>` | `screen:hana:3` |",
        "| `person_id` | `p_<first>-<last>`; a personal-address record kept apart gets `-personal` | `p_chiara-ekwueme`, `p_luca-bellweather-personal` |",
        "| `org_id` | `o_<short name>` | `o_fennimore` |",
        "| `case_id` | leave: `leave:<person>:<first day>_<last day>`; offboarding and onboarding: `<process>:<person>` (one case per person) | `leave:amara-jaramillo:2026-03-23_2026-03-23`, `onboarding:chiara-ekwueme` |",
        "| `flag_id` | `<rule>:<case_id>`, or `<rule>:<process>` for process-level rules | `laptop_requested_late:onboarding:chiara-ekwueme`, `sick_leave_two_ways:leave` |",
        "| insight `id` | patterns: `ins:<process>:<name>`; case flags: `flag:<flag_id>` | `ins:onboarding:laptop_late` |",
        "| open question `id` | `<process>-q<n>` | `leave-q1` |",
        "| feedback `id` | 12 hex characters, random | `6cadb282fb65` |",
        "",
    ])

    # ---------------------------------------------------------------- step 0
    add([
        "## Step 0 · Profile",
        "",
        ("**Reads** every file in `data/`. **Writes** [`out/0_profile.json`](../out/0_profile.json) "
        f"({sample_link('0_profile.json')}): what is in the export before anything is changed."),
        "",
        table([
            ("coverage", "object", "staff in the directory vs. exported (`label`: \"Data from 6 of 12 staff.\"), with names and job titles"),
            ("export_window", "object", "`start`, `end`, `timezone`, exported `mailboxes`"),
            ("per_person.<mailbox>.sources.<source>", "object", "file, record count, time field and format variants, time range, duplicates, records outside the window"),
            ("shared", "object", "the same for shared files (Teams channel)"),
            ("dedup_summary.<source>", "object", "dedup key, raw records, unique items, removed by dedup"),
            ("totals.raw_records", "int", "all raw records"),
        ]),
        "",
        "Example (`coverage`, `dedup_summary.mail`):",
        "",
        block({"coverage": {k: profile["coverage"][k] for k in ("label", "staff_in_directory", "staff_exported", "not_exported")},
               "dedup_summary": {"mail": profile["dedup_summary"]["mail"]}}),
        "",
        "Rules: nothing is filtered or changed here. Coverage is shown on every page of the UI.",
        "",
    ])

    # ---------------------------------------------------------------- step 1
    ev1 = jsonl_first(OUT / "1_events.jsonl", lambda e: e["event_id"] == TOBIAS)
    add([
        "## Step 1 · Ingest",
        "",
        (f"**Reads** mail, calendar, Teams chat, Teams channel and screen logs from `data/`. **Writes** [`out/1_events.jsonl`](../out/1_events.jsonl) "
        f"({sample_link('1_events.jsonl')}): one event per mail, calendar or Teams record. Screen sessions are built here but written in step 2."),
        "",
        fields_table(event.Event),
        "",
        "Example (Tobias's Teams message, before cleaning):",
        "",
        block(ev1),
        "",
        "Rules:",
        "",
        "* Every time is converted to Sri Lanka time and UTC, whatever the source format (UTC `Z`, `+05:30`, or a naive time with a Windows time-zone name).",
        "* The same item seen in several mailboxes becomes one event (mail by `internetMessageId`, calendar by `iCalUId`, Teams by chat + message id); `seen_in` lists the mailboxes.",
        "* Screen frames of the same window (same mailbox and title, short gaps) become one session.",
        "* `raw_ref` (file + 1-based line) always points back to the original line.",
        "",
    ])

    # ---------------------------------------------------------------- step 2
    ev2 = jsonl_first(OUT / "2_events_clean.jsonl", lambda e: e["event_id"] == TOBIAS)
    sess = jsonl_first(OUT / "2_events_clean.jsonl", lambda e: e["source"] == "screen" and e.get("session", {}).get("frame_count", 0) > 1)
    luca = next(p for p in people["people"] if p.get("possible_same_person"))
    add([
        "## Step 2 · Clean",
        "",
        "**Reads** the step 1 events and screen sessions. **Writes** three files:",
        "",
        f"### `2_events_clean.jsonl` ({sample_link('2_events_clean.jsonl')})",
        "",
        ("The step 1 event plus its label: `category`, `process`, `activity`, `subject_person_id`, `resolution` and extracted `fields` "
        "(`rule_id`, dates, client, needed-by date). Same fields as the Event table above. Inside it:"),
        "",
        "Resolution (how the person the event is about was found):",
        "",
        fields_table(event.Resolution),
        "",
        "Session (screen events only):",
        "",
        fields_table(event.Session),
        "",
        "Example (the same Teams message after cleaning):",
        "",
        block({k: ev2[k] for k in ("event_id", "category", "process", "activity", "subject_person_id", "resolution", "fields")}),
        "",
        "Example screen session:",
        "",
        block({k: sess[k] for k in ("event_id", "source", "title", "category", "activity", "session") if k in sess}),
        "",
        "Rules:",
        "",
        ("* `category`: `process` (a step of leave, offboarding or onboarding), `context` (related but not a step), `noise` (small talk, newsletters, lock screen), "
        "`out_of_scope` (recruitment, birthdays, laptop replacements, payroll). Nothing is deleted; `noise_reason` says why."),
        "* Activities come from one rule table (`pipeline/rules.py`); `fields.rule_id` names the rule that fired.",
        "* Screens are read by window title and address, never by the app name.",
        ("* Names are resolved in this order: email, sender, chat member, thread, full name, first name + initial, unique first name, typo (fuzzy), case context. "
        "Every match stores a plain `reason`. When more than one person fits, `method` is `ambiguous` and `candidates` lists them; nothing is guessed."),
        "",
        f"### `2_people.json` ({sample_link('2_people.json')})",
        "",
        "`people[]`, `orgs[]` and `identity_merges[]`.",
        "",
        fields_table(person.Person),
        "",
        "Example (a person with a possible duplicate):",
        "",
        block(luca),
        "",
        ("Rules: a personal and a work address are merged only with onboarding evidence (personal address used first, work address later, same client); "
        "`merge_reason` says why. Otherwise both records stay and `possible_same_person` asks staff \"Is this the same person?\"."),
        "",
        f"### `2_screen_summary.json` ({sample_link('2_screen_summary.json')})",
        "",
        "Context, noise and out-of-scope screen sessions, too many to list one by one, summarised as table rows.",
        "",
        table([(col, "int" if col in ("sessions", "frames") else ("float" if col == "minutes" else "string"),
                {"mailbox": "whose screen", "day": "local date", "category": "context / noise / out_of_scope", "title": "window title",
                 "sessions": "sessions of that title that day", "frames": "screen frames", "minutes": "time on screen"}[col]) for col in screen["columns"]]),
        "",
        "`rows` are arrays in `columns` order; `reason_by_title` gives the label reason per title; `totals` sums sessions and frames per category.",
        "",
        "Example row:",
        "",
        block(dict(zip(screen["columns"], screen["rows"][0]))),
        "",
    ])

    # ---------------------------------------------------------------- step 3
    case_rows = [
        ("case_id", "string", "see ID conventions"), ("process", "string", "`leave`, `offboarding`, `onboarding`"),
        ("subject_person_id / subject_name", "string", "who the case is about"), ("client", "string", "`org_id` of the client, if any"),
        ("owner_staff_id", "string", "People team member who handled it"), ("staff_involved", "string[]", "person ids of staff who did steps"),
        ("handoff", "bool", "more than one staff member did the steps"), ("key", "object", "what identifies the case: leave `dates` and `leave_type`, `last_day`, `first_day`"),
        ("status", "string", "outcome: `complete`, `in_progress`, `declined`, `cancelled`"),
        ("started_before_window / ends_after_window", "bool", "window badges: steps likely before 2 Mar / after 29 Mar"),
        ("window_notes", "string[]", "why a badge was set"), ("start / end / last_activity", "string", "local times of the first and last step"),
        ("steps", "CaseStep[]", "the case's steps in time order (table below)"), ("flags", "string[]", "`flag_id`s from step 5"),
        ("out_of_order", "object[]", "pairs of steps in an unexpected order"), ("summary", "string", "one-line plain-English summary"),
    ]
    step_ex = next(s for s in chiara["steps"] if s["event_id"] == TOBIAS)
    add([
        "## Step 3 · Cases",
        "",
        (f"**Reads** clean events and people. **Writes** [`out/3_cases.json`](../out/3_cases.json) ({sample_link('3_cases.json')}): "
        "`cases[]`, plus `person_last_days[]` (each leaver's last day, for cross-process checks) and `unlinked_process_events[]`."),
        "",
        table(case_rows),
        "",
        "Case step:",
        "",
        fields_table(case.CaseStep),
        "",
        "Example (Chiara's case, with the step made from Tobias's message):",
        "",
        block({**{k: v for k, v in chiara.items() if k != "steps"}, "steps": [step_ex, f"… {len(chiara['steps']) - 1} more"]}),
        "",
        "Rules:",
        "",
        "* Leave cases are keyed by person and dates; offboarding and onboarding have one case per person. A step joins by thread first, then dates, then person, then time (`link`, with a `link_reason`).",
        ("* **Confidence** of a step: `high` = an explicit message names the action and the person, or it is in the same thread; `medium` = a calendar entry, "
        "or the person was matched by a short name, typo or case context; `low` = seen on screen or linked by time only."),
        "* **Likely**: every screen-based step has `likely: true` and is shown as \"Likely\": a screen shows what was open, not what was done.",
        ("* **Status vs window badges**: `status` is only the outcome. Whether steps fall outside 2–29 March is shown separately by "
        "`started_before_window` and `ends_after_window`, never as missing steps."),
        "",
    ])

    # ---------------------------------------------------------------- step 4
    it_ready = next(s for s in onboarding["steps"] if s["activity"] == "it_ready")
    add([
        "## Step 4 · Discover",
        "",
        (f"**Reads** cases. **Writes** [`out/4_processes.json`](../out/4_processes.json) ({sample_link('4_processes.json')}): `processes[]`, one model per process. "
        "The same model is served by `GET /api/processes/{process}`."),
        "",
        table([
            ("process", "string", "`leave`, `offboarding`, `onboarding`"), ("case_count", "int", "cases of this process"),
            ("full_trace_cases", "int", "complete cases that start inside the window: what the main path rests on"),
            ("status_counts / window_badges", "object", "cases per status / per badge"), ("main_path", "MainPath", "the usual order of steps"),
            ("steps", "ProcessStep[]", "every activity seen, with support and timing"), ("dfg", "DfgEdge[]", "directly-follows graph: how often step A is followed by step B"),
            ("variants", "Variant[]", "distinct step sequences and their cases"), ("open_questions", "OpenQuestion[]", "questions for staff where the data is thin"),
            ("path_confidence", "PathConfidence", "high / medium / low, with the reason and the rule"),
            ("insight_ids / process_flags", "string[]", "links to step 5 and 6"),
        ]),
        "",
        "MainPath:", "", fields_table(process.MainPath), "",
        "ProcessStep:", "", fields_table(process.ProcessStep), "",
        "Variant:", "", fields_table(process.Variant), "",
        "DfgEdge:", "", fields_table(process.DfgEdge), "",
        "OpenQuestion:", "", fields_table(process.OpenQuestion), "",
        "PathConfidence:", "", fields_table(process.PathConfidence), "",
        "Example (onboarding: the \"IT ready\" step, path confidence, one open question):",
        "",
        block({"process": "onboarding", "steps": [it_ready], "path_confidence": onboarding["path_confidence"], "open_questions": [leave["open_questions"][0]]}),
        "",
        "Rules:",
        "",
        "* No order is hard-coded: the main path is the most common complete variant, or a consensus order when none repeats (`main_path.method`).",
        "* `support_pct` = share of the process's cases that contain the step. Steps under 50% or off the main path are shown as optional.",
        "* Variants use explicit steps only (screen steps are left out) and collapse repeats.",
        f"* Path confidence: {onboarding['path_confidence']['rule']}.",
        "",
    ])

    # ---------------------------------------------------------------- step 5
    flag_ex = next(f for f in flags["flags"] if f["rule"] == "activity_after_last_day")
    rule_text = {
        "activity_after_last_day": "a step (often an approved leave) on or after the person's last day",
        "onboarded_before_laptop": "the starter was confirmed onboarded before the laptop arrived",
        "laptop_requested_late": "the laptop was requested after the needed-by date",
        "onboarded_with_open_issue": "confirmed onboarded while a day-one issue was still open",
        "cancel_no_followup": "a leave cancellation with no reply, client update or tracker change",
        "sick_leave_two_ways": "sick leave handled two ways (client asked vs. only told); process-level",
    }
    add([
        "## Step 5 · Flags",
        "",
        (f"**Reads** cases and process models. **Writes** [`out/5_flags.json`](../out/5_flags.json) ({sample_link('5_flags.json')}) and "
        f"[`out/pipeline_report.json`](../out/pipeline_report.json) ({sample_link('pipeline_report.json')}, counts per stage and per activity)."),
        "",
        fields_table(insight.Flag),
        "",
        "Example:",
        "",
        block(flag_ex),
        "",
        "Rules (flags in this run):",
        "",
        "| rule | fires when | flags |",
        "|---|---|---|",
        *[f"| `{r}` | {rule_text.get(r, '')} | {n} |" for r, n in sorted(rule_counts.items(), key=lambda x: -x[1])],
        "",
        "Every flag lists `evidence_event_ids`, and its id is written back onto the case (`flags[]`).",
        "",
    ])

    # ---------------------------------------------------------------- step 6
    ins_ex = next(i for i in insights["insights"] if i["id"] == "ins:onboarding:laptop_late")
    add([
        "## Step 6 · Insights",
        "",
        f"**Reads** flags. **Writes** [`out/6_insights.json`](../out/6_insights.json) ({sample_link('6_insights.json')}): `insights[]` and `counts`.",
        "",
        fields_table(insight.Insight),
        "",
        "Per case (inside a pattern):",
        "",
        fields_table(insight.InsightCase),
        "",
        "Example:",
        "",
        block(ins_ex),
        "",
        ("Rules: a rule becomes a pattern (`process_insight`) when it hits at least 3 cases and at least half of the eligible ones, or the same issue "
        "appears at 3 or more clients; otherwise each hit stays a `case_flag`. A starter's two laptop flags are merged into one line."),
        "",
    ])

    # ---------------------------------------------------------------- feedback
    add([
        "## Feedback (runtime)",
        "",
        ("**Written by** `POST /api/feedback` to SQLite (`backend/feedback.db`) and appended to `out/feedback.jsonl` (git-ignored). "
        "`GET /api/feedback/export` downloads all rows as JSONL."),
        "",
        "Request (`FeedbackIn`):",
        "",
        fields_table(feedback.FeedbackIn),
        "",
        "Stored row (`Feedback` = request + `id` + `created_at`). Example (produced against a temporary database):",
        "",
        block(posted),
        "",
        ("Rules: `target` is one of `process_step`, `case_step`, `case`, `open_question`, `insight`, `identity`; `verdict` is `confirm`, `reject`, `add`, "
        "or `answer` (open questions only, and an answer needs a `note`). The target must exist (unknown case, step, question, insight or person → 422). "
        "`add` needs `proposed_step` or a note."),
        "",
    ])

    # ---------------------------------------------------------------- API
    add([
        "## API responses",
        "",
        "Every endpoint and its full response model is listed at `/docs` (OpenAPI) when the app runs.",
        "",
        "| endpoint | returns |",
        "|---|---|",
        "| `GET /api/meta` | `Meta`: coverage, export window, stage counts, out/ files |",
        "| `GET /api/processes` · `/api/processes/{process}` | `ProcessSummary[]` · `ProcessDetail` (step 4 model + insights) |",
        "| `GET /api/cases` · `/api/cases/{case_id}` | `CaseSummary[]` (filters: process, status, flagged, q) · `CaseDetail` (step 3 case + names, flags, insights) |",
        "| `GET /api/events/{event_id}/raw` | `RawResponse`: the original line(s), unchanged |",
        "| `GET /api/insights` · `/api/flags` | `Insight[]` · `Flag[]` |",
        "| `GET /api/people/{person_id}` | `PersonDetail`: person + their cases |",
        "| `GET /api/files/{name}` | one `out/` file (allow-list) |",
        "| `POST /api/feedback` · `GET /api/feedback` · `GET /api/feedback/export` | `Feedback` · `FeedbackList` · JSONL |",
        "",
        "Raw record (`RawResponse`). Example from the invented test fixture; the real export is not in this repo:",
        "",
        fields_table(event.RawResponse),
        "",
        block(raw),
        "",
        "Meta (`GET /api/meta`):",
        "",
        fields_table(meta.Meta),
        "",
        block(meta_ex),
        "",
    ])
    (ROOT / "docs" / "schemas.md").write_text("\n".join(md), encoding="utf-8")
    print(f"wrote docs/schemas.md ({len(md)} lines)")


if __name__ == "__main__":
    main()
