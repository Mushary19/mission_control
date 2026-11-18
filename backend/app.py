"""Mission Control API (FastAPI). Reads the pipeline outputs in out/ once at startup (read-only).

Run:  uvicorn app:app --app-dir backend --reload      (API at /api, docs at /docs)
Env:  MC_OUT_DIR (default out/), MC_DATA_DIR (default data/), MC_DB (default backend/feedback.db),
      MC_FEEDBACK_JSONL (default out/feedback.jsonl), MC_CORS (comma-separated origins)
"""

from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse

sys.path.insert(0, str(Path(__file__).resolve().parent))
from db import FeedbackStore  # noqa: E402
from schemas import (  # noqa: E402
    CaseDetail, CaseStep, CaseSummary, Coverage, Feedback, FeedbackIn, FeedbackList, Flag, Insight, Meta,
    PersonDetail, PersonRef, PossibleSame, ProcessDetail, ProcessSummary, RawLine, RawResponse, SeenNotModelled,
    StaffRef, Window,
)

ROOT = Path(__file__).resolve().parent.parent
PROCESS_LABELS = {"leave": "Leave", "offboarding": "Offboarding", "onboarding": "Onboarding"}
SEEN_NOT_MODELLED = [  # (key, label, substring of noise_reason)
    ("recruiting", "Recruitment (HireTrack, Recruitment tracker, LinkedIn)", "recruitment"),
    ("birthdays", "Birthday gifts", "birthday"),
    ("laptop_replacements", "Laptop replacements", "laptop replacement"),
    ("payroll_queries", "Payslip / timesheet / invoice queries", "payslip"),
]


class Store:
    """Everything the API serves, loaded once from out/."""

    def __init__(self, out_dir: Path, data_dir: Path):
        self.out, self.data = Path(out_dir), Path(data_dir)
        j = lambda name: json.loads((self.out / name).read_text(encoding="utf-8"))  # noqa: E731
        self.profile = j("0_profile.json")
        people_doc = j("2_people.json")
        self.people = {p["person_id"]: p for p in people_doc["people"]}
        self.orgs = {o["org_id"]: o for o in people_doc["orgs"]}
        cases_doc = j("3_cases.json")
        self.cases = {c["case_id"]: c for c in cases_doc["cases"]}
        self.processes = {p["process"]: p for p in j("4_processes.json")["processes"]}
        self.flags = j("5_flags.json")["flags"]
        ins = j("6_insights.json")
        self.insights = ins["insights"]
        self.report = j("pipeline_report.json")
        self.screen_summary = j("2_screen_summary.json")
        self.events = {}
        with (self.out / "2_events_clean.jsonl").open(encoding="utf-8") as fh:
            for line in fh:
                e = json.loads(line)
                self.events[e["event_id"]] = e
        self.flag_by_id = {f["flag_id"]: f for f in self.flags}
        self.insight_by_id = {i["id"]: i for i in self.insights}
        self.case_insights = defaultdict(list)
        for i in self.insights:
            if i["kind"] == "process_insight":
                for cid in i["affected_case_ids"]:
                    self.case_insights[cid].append(i["id"])
        self.questions = {q["id"]: q for p in self.processes.values() for q in p["open_questions"]}
        self._raw_cache: dict[str, list[str]] = {}

    def name(self, pid):
        return self.people.get(pid, {}).get("display_name") if pid else None

    def org_name(self, oid):
        return self.orgs.get(oid, {}).get("name") if oid else None

    def raw_lines(self, rel_file: str) -> list[str]:
        if rel_file not in self._raw_cache:
            path = (ROOT / rel_file).resolve() if not Path(rel_file).is_absolute() else Path(rel_file)
            if rel_file.startswith("data/"):
                path = (self.data / rel_file[len("data/"):]).resolve()
            if self.data.resolve() not in path.parents:
                raise HTTPException(400, "raw_ref outside data/")
            if not path.exists():
                raise HTTPException(503, f"raw export not available on this server ({rel_file}); put the export in data/")
            self._raw_cache[rel_file] = path.read_text(encoding="utf-8").split("\n")
        return self._raw_cache[rel_file]


def case_summary(s: Store, c: dict) -> CaseSummary:
    return CaseSummary(
        case_id=c["case_id"], process=c["process"], subject_person_id=c["subject_person_id"], subject_name=c["subject_name"],
        client=c.get("client"), client_name=s.org_name(c.get("client")), owner_staff_id=c.get("owner_staff_id"), owner_name=s.name(c.get("owner_staff_id")),
        status=c["status"], started_before_window=c["started_before_window"], ends_after_window=c["ends_after_window"],
        step_count=len(c["steps"]), flag_count=len(c["flags"]), start=c["start"], last_activity=c["last_activity"], summary=c["summary"],
    )


def process_summary(s: Store, p: dict) -> dict:
    return dict(
        process=p["process"], label=PROCESS_LABELS[p["process"]], case_count=p["case_count"], status_counts=p["status_counts"],
        window_badges=p["window_badges"], full_trace_cases=p["full_trace_cases"], path_confidence=p["path_confidence"],
        main_path_labels=p["main_path"]["labels"], open_question_count=len(p["open_questions"]),
        insight_count=sum(1 for i in s.insights if i["process"] == p["process"]),
    )


def create_app(out_dir: Path | None = None, data_dir: Path | None = None, db_path: Path | None = None, feedback_jsonl: Path | None = None) -> FastAPI:
    out_dir = Path(out_dir or os.environ.get("MC_OUT_DIR", ROOT / "out"))
    data_dir = Path(data_dir or os.environ.get("MC_DATA_DIR", ROOT / "data"))
    s = Store(out_dir, data_dir)
    fb = FeedbackStore(Path(db_path or os.environ.get("MC_DB", ROOT / "backend" / "feedback.db")), Path(feedback_jsonl or os.environ.get("MC_FEEDBACK_JSONL", out_dir / "feedback.jsonl")))

    app = FastAPI(
        title="Mission Control API",
        version="0.4.0",
        description="Process intelligence for the Harbourline Talent People team (synthetic data, 2–29 Mar 2026). "
        "Data from 6 of 12 staff. All times in Sri Lanka time (UTC+05:30). Read-only pipeline outputs + staff feedback.",
    )
    origins = os.environ.get("MC_CORS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
    app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["GET", "POST"], allow_headers=["*"])
    app.state.store, app.state.feedback = s, fb

    # ------------------------------------------------------------------ meta
    @app.get("/api/meta", response_model=Meta, tags=["meta"], summary="Coverage, export window, pipeline counts")
    def meta():
        cov = s.profile["coverage"]
        win = s.profile["export_window"]
        seen = []
        rows = s.screen_summary["rows"]
        reason_by_title = s.screen_summary["reason_by_title"]
        cols = s.screen_summary["columns"]
        for key, label, needle in SEEN_NOT_MODELLED:
            ev = sum(1 for e in s.events.values() if e.get("category") == "out_of_scope" and needle in (e.get("noise_reason") or ""))
            ss = sum(r[cols.index("sessions")] for r in rows if r[cols.index("category")] == "out_of_scope" and needle in (reason_by_title.get(r[cols.index("title")]) or ""))
            seen.append(SeenNotModelled(key=key, label=label, events=ev, screen_sessions=ss))
        return Meta(
            coverage=Coverage(
                staff_total=cov["staff_in_directory"], staff_exported=cov["staff_exported"], label=cov["label"],
                exported=[StaffRef(name=x["name"], job_title=x["jobTitle"], folder=x["folder"]) for x in cov["exported"]],
                not_exported=[StaffRef(name=x["name"], job_title=x["jobTitle"]) for x in cov["not_exported"]],
            ),
            window=Window(start=win["start"], end=win["end"], timezone=win["timezone"], note=win.get("note")),
            timezone_note="All times in Sri Lanka time (UTC+05:30)",
            stage_counts={k: int(v) for k, v in s.report["stage_counts"].items()},
            seen_not_modelled=seen,
            out_files=sorted(p.name for p in s.out.glob("*") if p.suffix in (".json", ".jsonl") and p.name != "feedback.jsonl"),
        )

    # ------------------------------------------------------------------ processes
    @app.get("/api/processes", response_model=list[ProcessSummary], tags=["processes"])
    def processes():
        return [ProcessSummary(**process_summary(s, p)) for p in s.processes.values()]

    @app.get("/api/processes/{process}", response_model=ProcessDetail, tags=["processes"], summary="Discovered process: main path, steps, DFG, variants, open questions, insights")
    def process_detail(process: str):
        p = s.processes.get(process)
        if not p:
            raise HTTPException(404, f"unknown process {process!r}")
        return ProcessDetail(
            **process_summary(s, p), main_path=p["main_path"], steps=p["steps"], dfg=p["dfg"], variants=p["variants"],
            open_questions=p["open_questions"], insights=[i for i in s.insights if i["process"] == process],
        )

    # ------------------------------------------------------------------ cases
    @app.get("/api/cases", response_model=list[CaseSummary], tags=["cases"])
    def cases(process: str | None = None, status: str | None = None, flagged: bool | None = None, q: str | None = Query(None, description="search person, client, case id, summary")):
        out = []
        for c in sorted(s.cases.values(), key=lambda c: c["last_activity"], reverse=True):
            if process and c["process"] != process or status and c["status"] != status:
                continue
            is_flagged = bool(c["flags"]) or bool(s.case_insights.get(c["case_id"]))
            if flagged is not None and is_flagged != flagged:
                continue
            if q:
                hay = " ".join([c["case_id"], c["subject_name"], s.org_name(c.get("client")) or "", c["summary"]]).lower()
                if q.lower() not in hay:
                    continue
            out.append(case_summary(s, c))
        return out

    @app.get("/api/cases/{case_id}", response_model=CaseDetail, tags=["cases"], summary="One case: steps with confidence, likely flag, resolution reason; flags")
    def case_detail(case_id: str):
        c = s.cases.get(case_id)
        if not c:
            raise HTTPException(404, f"unknown case {case_id!r}")
        steps = []
        for st in c["steps"]:
            e = s.events.get(st["event_id"], {})
            steps.append(CaseStep(**{k: v for k, v in st.items() if k in CaseStep.model_fields}, title=e.get("title"), text=e.get("text"), resolution=e.get("resolution")))
        return CaseDetail(
            **case_summary(s, c).model_dump(), key=c["key"], handoff=c["handoff"], window_notes=c["window_notes"],
            staff_involved=[PersonRef(person_id=p, name=s.name(p)) for p in c["staff_involved"]],
            steps=steps, flags=[s.flag_by_id[f] for f in c["flags"]],
            related_flags=[f for f in s.flags if f["person_id"] == c["subject_person_id"] and f["case_id"] != case_id],
            insights=s.case_insights.get(case_id, []), out_of_order=c["out_of_order"],
        )

    # ------------------------------------------------------------------ raw records
    @app.get("/api/events/{event_id:path}/raw", response_model=RawResponse, tags=["events"], summary="The original raw line(s) from data/, unchanged (screen sessions: every frame)")
    def raw(event_id: str):
        e = s.events.get(event_id)
        if not e:
            raise HTTPException(404, f"unknown event {event_id!r} (context/noise screen sessions are only summarised)")
        ref = e["raw_ref"]
        lines = e.get("meta", {}).get("raw_lines") or [ref["line"]]
        content = s.raw_lines(ref["file"])
        out = []
        for n in lines:
            raw_line = content[n - 1]
            out.append(RawLine(file=ref["file"], line=n, raw=raw_line, record=json.loads(raw_line)))
        return RawResponse(event_id=event_id, source=e["source"], line_count=len(out), lines=out)

    # ------------------------------------------------------------------ insights + flags
    @app.get("/api/insights", response_model=list[Insight], tags=["insights"], summary="Process insights (systemic) and case flags (specific)")
    def insights(process: str | None = None, kind: str | None = None):
        return [i for i in s.insights if (not process or i["process"] == process) and (not kind or i["kind"] == kind)]

    @app.get("/api/flags", response_model=list[Flag], tags=["insights"], summary="Raw flag rule hits (before grouping into insights)")
    def flags(rule: str | None = None, process: str | None = None):
        return [f for f in s.flags if (not rule or f["rule"] == rule) and (not process or f["process"] == process)]

    # ------------------------------------------------------------------ people
    @app.get("/api/people/{person_id}", response_model=PersonDetail, tags=["people"])
    def person(person_id: str):
        p = s.people.get(person_id)
        if not p:
            raise HTTPException(404, f"unknown person {person_id!r}")
        same = [PossibleSame(person_id=x["person_id"], name=s.name(x["person_id"]), reason=x["reason"]) for x in p.get("possible_same_person", [])]
        data = {k: v for k, v in p.items() if k not in ("possible_same_person", "teams_ids", "export_folder")}
        return PersonDetail(**data, org_name=s.org_name(p.get("org")), possible_same_person=same,
                            cases=[case_summary(s, c) for c in s.cases.values() if c["subject_person_id"] == person_id])

    # ------------------------------------------------------------------ feedback
    def validate(item: FeedbackIn) -> None:
        def need(cond, msg):
            if not cond:
                raise HTTPException(422, msg)

        need(item.user.strip(), "user is required")
        need((item.verdict == "answer") == (item.target == "open_question"), 'verdict "answer" is used for open questions (and only for them)')
        if item.target == "open_question":
            need(item.question_id in s.questions, "unknown question_id")
            need(item.note.strip(), "an answer needs text in note")
        if item.target == "insight":
            need(item.insight_id in s.insight_by_id, "unknown insight_id")
        if item.target == "identity":
            need(item.person_id in s.people and item.other_person_id in s.people, "identity feedback needs person_id and other_person_id")
        if item.target in ("case", "case_step"):
            need(item.case_id in s.cases, "unknown case_id")
        if item.target == "case_step" and item.verdict != "add":
            need(item.event_id in {st["event_id"] for st in s.cases[item.case_id]["steps"]}, "event_id is not a step of this case")
        if item.target == "process_step":
            need(item.process in s.processes, "process_step feedback needs a process")
            need(item.verdict == "add" or item.activity in {x["activity"] for x in s.processes[item.process]["steps"]}, "unknown activity for this process")
        if item.verdict == "add":
            need(item.proposed_step or item.note.strip(), 'verdict "add" needs proposed_step or a note')

    @app.post("/api/feedback", response_model=Feedback, status_code=201, tags=["feedback"], summary="Confirm / reject / add a step, or answer an open question")
    def post_feedback(item: FeedbackIn):
        validate(item)
        return fb.add(item)

    @app.get("/api/feedback", response_model=FeedbackList, tags=["feedback"])
    def get_feedback(target: str | None = None, case_id: str | None = None, process: str | None = None, user: str | None = None):
        items = fb.list(target=target, case_id=case_id, process=process, user=user)
        return FeedbackList(count=len(items), items=items)

    @app.get("/api/feedback/export", response_class=PlainTextResponse, tags=["feedback"], summary="All feedback as JSONL (download)")
    def export_feedback():
        body = "".join(json.dumps(f.model_dump(mode="json"), ensure_ascii=False, sort_keys=True) + "\n" for f in fb.list())
        return PlainTextResponse(body, media_type="application/x-ndjson", headers={"Content-Disposition": 'attachment; filename="feedback.jsonl"'})

    @app.get("/api/health", tags=["meta"], include_in_schema=False)
    def health():
        return {"ok": True}

    return app


app = create_app()
