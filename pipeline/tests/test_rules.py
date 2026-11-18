"""Must-pass tests: rules, name resolution (spec section 6) and case building.

Runs the real pipeline (steps 1-3) once on data/ into a temp folder; never touches out/.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pipeline as pl  # noqa: E402
import rules as R  # noqa: E402

pytestmark = pytest.mark.skipif(not (pl.DATA / "_shared/directory.json").exists(), reason="data/ export not present")


@pytest.fixture(scope="session")
def run(tmp_path_factory):
    pl.OUT = tmp_path_factory.mktemp("out")
    ingest = pl.step1_ingest()
    clean = pl.step2_clean(ingest)
    cases = pl.step3_cases(clean)
    reg = clean["registry"]
    return {"events": clean["events"], "reg": reg, "cases": cases["cases"], "doc": cases["doc"], "merges": clean["merges"]}


# ----------------------------------------------------------------------------- helpers


def pid(run, name: str, kind: str | None = None) -> str:
    ids = [p for p, x in run["reg"].people.items() if x["display_name"] == name and (kind is None or x["kind"] == kind)]
    assert len(ids) == 1, f"{name}: {ids}"
    return ids[0]


def events_where(run, text: str, activity: str | None = None):
    return [e for e in run["events"] if text in (e["text"] or "") + " " + (e["title"] or "") and (activity is None or e["activity"] == activity)]


def one(run, text: str, activity: str | None = None) -> dict:
    evs = events_where(run, text, activity)
    assert len(evs) == 1, f"{text!r}: {len(evs)} events"
    return evs[0]


def cases_of(run, name: str, process: str | None = None):
    return [c for c in run["cases"] if c["subject_name"] == name and (process is None or c["process"] == process)]


def subject(run, ev) -> str | None:
    return run["reg"].name(ev["subject_person_id"])


# ----------------------------------------------------------------------------- unit: rules + helpers


@pytest.mark.parametrize("a,b,d", [("hmaza", "hamza", 1), ("snane", "sanne", 1), ("qunin", "quinn", 1), ("chaira", "chiara", 1), ("jvoana", "jovana", 1), ("hana", "hamza", 2)])
def test_osa_distance(a, b, d):
    assert pl.osa_distance(a, b) == d


def test_parse_range_and_weekday():
    r = pl.parse_range("Tue 31 Mar – Thu 2 Apr")
    assert (r["start"], r["end"]) == ("2026-03-31", "2026-04-02") and "warnings" not in r
    assert pl.parse_day("Mon 31 Mar")[1]  # wrong weekday is reported, not silently fixed


@pytest.mark.parametrize("text", ["lunch?", "coffee ☕", "thanks!", "👍", "running 5 min late", "are you joining the sync?", "can you cover my inbox for an hour", "the VPN is slow again", "did you see Lionel Penhaligon's message?", "who's updating the tracker today?"])
def test_small_talk_is_noise(text):
    rule = next(r for r in R.RULES if r.sources == ("teams_chat",) and r.category == "noise" and r.rx("text").search(text))
    assert rule.reason == "small talk"


def test_screen_app_field_is_ignored(run):
    peoplehub = [e for e in run["events"] if e["source"] == "screen" and (e["title"] or "").endswith(" - PeopleHub")]
    assert peoplehub and all(e["activity"] == "peoplehub_opened" for e in peoplehub)
    assert any("excel" in e["meta"]["apps"] for e in peoplehub)  # mislabelled app still classified by title


def test_screen_sessions_merge_frames(run):
    sessions = [e for e in run["events"] if e["source"] == "screen"]
    assert sum(e["session"]["frame_count"] for e in sessions) == 9927
    assert all("raw_ref" in e for e in sessions)


def test_text_truncated_in_out_files(run):
    import json

    for line in (pl.OUT / "2_events_clean.jsonl").open(encoding="utf-8"):
        assert len(json.loads(line).get("text", "")) <= pl.TEXT_LIMIT + 1


# ----------------------------------------------------------------------------- spec section 6 must-pass


def test_bram_laptop_back_is_montague(run):
    ev = one(run, "Got Bram's laptop back, wiped")
    assert subject(run, ev) == "Bram Montague" and ev["process"] == "offboarding"
    assert ev["resolution"]["method"] == "context"
    assert not cases_of(run, "Bram Danforth", "offboarding")  # new starter, nothing to return
    assert cases_of(run, "Bram Danforth", "onboarding")


def test_mateus_zielinski_is_not_staff_mateus(run):
    staff = pid(run, "Mateus Vasquez-Lowe")
    assert run["reg"].people[staff]["kind"] == "staff"
    assert all(e["subject_person_id"] != staff for e in run["events"])
    ev = one(run, "Mateus Zielinski finished induction")
    assert subject(run, ev) == "Mateus Zielinski"
    assert run["reg"].people[ev["subject_person_id"]]["kind"] == "new_starter"


def test_three_hamzas(run):
    vl = cases_of(run, "Hamza Vasquez-Lowe", "leave")
    assert len(vl) == 1 and vl[0]["status"] == "cancelled"
    assert cases_of(run, "Hamza Pemberton", "leave") and cases_of(run, "Hamza Pemberton", "offboarding")
    assert cases_of(run, "Hamza Galloway", "leave") and not cases_of(run, "Hamza Galloway", "offboarding")
    hmaza = one(run, "Hamza has asked for annual leave on Mon 23 Mar")  # subject line says 'Hmaza'
    assert subject(run, hmaza) == "Hamza Vasquez-Lowe"


def test_two_quinns(run):
    qunin = one(run, "Qunin Ellingham finishes")
    assert subject(run, qunin) == "Quinn Ellingham" and qunin["resolution"]["method"] == "fuzzy"
    assert subject(run, one(run, "Got Quinn's laptop back")) == "Quinn Ellingham"
    assert cases_of(run, "Quinn Ellingham", "offboarding")
    assert cases_of(run, "Quinn Quillfeather", "leave") and not cases_of(run, "Quinn Quillfeather", "offboarding")


def test_hana_prescott_is_not_staff_hana(run):
    staff = pid(run, "Hana Pemberton")
    assert run["reg"].people[staff]["kind"] == "staff"
    assert all(e["subject_person_id"] != staff for e in run["events"])
    assert cases_of(run, "Hana Prescott", "leave")


def test_ravi_kettering_is_not_staff_ravi(run):
    staff = pid(run, "Ravi Larkspur")
    assert all(e["subject_person_id"] != staff for e in run["events"])
    order = one(run, "Deliver to: Ravi Kettering")
    assert order["category"] == "out_of_scope" and "replacement" in order["noise_reason"]
    assert not cases_of(run, "Ravi Kettering")


@pytest.mark.parametrize("client,other,other_kind", [
    ("Kavya Quintero", "Kavya Jaramillo", "it"),
    ("Chiara Yilmaz", "Chiara Ekwueme", "new_starter"),
    ("Jasper Dunmore", "Jasper Haverford", "worker"),
    ("Jovana Ashcombe", "Jovana Penhaligon", "worker"),
    ("Noor Galloway", "Noor Yardley", None),
])
def test_clients_are_not_workers(run, client, other, other_kind):
    c = pid(run, client)
    assert run["reg"].people[c]["kind"] == "client"
    assert all(e["subject_person_id"] != c for e in run["events"])
    others = [p for p, x in run["reg"].people.items() if x["display_name"] == other]
    assert others and c not in others
    if other_kind:
        assert any(run["reg"].people[o]["kind"] == other_kind for o in others)


def test_tobias_worker_vs_it(run):
    assert run["reg"].people[pid(run, "Tobias Northcott")]["kind"] == "it"
    assert run["reg"].people[pid(run, "Tobias Trelawney")]["kind"] == "worker"
    assert cases_of(run, "Tobias Trelawney", "leave")


def test_typos_chiara_and_sanne(run):
    assert subject(run, one(run, "Chaira Ekwueme onboarded")) == "Chiara Ekwueme"
    snane = one(run, "Laptop needed for Snane (new starter), Greythorne")
    assert subject(run, snane) == "Sanne Yilmaz" and snane["resolution"]["method"] == "fuzzy"


def test_jovana_two_leave_cases(run):
    cs = {(c["key"]["dates"]["start"], c["key"]["dates"]["end"]): c for c in cases_of(run, "Jovana Penhaligon", "leave")}
    assert set(cs) == {("2026-04-01", "2026-04-02"), ("2026-03-31", "2026-04-01")}
    hana_case, lerato_case = cs[("2026-04-01", "2026-04-02")], cs[("2026-03-31", "2026-04-01")]
    assert run["reg"].name(hana_case["owner_staff_id"]) == "Hana Pemberton" and hana_case["status"] == "declined"
    assert "client_declined" in [s["activity"] for s in hana_case["steps"]]
    assert run["reg"].name(lerato_case["owner_staff_id"]) == "Lerato Faraday" and lerato_case["status"] == "complete"


def test_callum_finishes_mon_13_apr(run):
    ev = one(run, "Callum finishes Mon 13 Apr")
    r = ev["resolution"]
    assert r["method"] in ("context", "ambiguous")
    if r["method"] == "context":
        assert subject(run, ev) == "Callum Montague"
        assert "13 Apr" in r["reason"]


def test_staff_are_never_case_subjects(run):
    staff = {p for p, x in run["reg"].people.items() if x["kind"] in ("staff", "it")}
    assert not any(c["subject_person_id"] in staff for c in run["cases"])
    assert subject(run, one(run, "Lerato finished induction")) == "Lerato Thorne"


# ----------------------------------------------------------------------------- extra tests (review)


def test_five_callums(run):
    callums = sorted(x["display_name"] for x in run["reg"].people.values() if x["display_name"].startswith("Callum ") and x["kind"] not in pl.NOT_SUBJECT)
    assert callums == ["Callum Bellweather", "Callum Delacroix", "Callum Grünewald", "Callum Lindqvist", "Callum Montague"]
    assert subject(run, one(run, "callum has asked for annual leave on Thu 26 Mar")) == "Callum Grünewald"
    assert subject(run, one(run, "callum has asked for annual leave on Tue 10 Mar")) == "Callum Montague"


def test_three_palomas(run):
    assert subject(run, one(run, "Paloma finishes Tue 24 Mar")) == "Paloma Larkspur"
    assert cases_of(run, "Paloma Larkspur", "offboarding")
    pm = cases_of(run, "Paloma Montague", "leave")
    assert len(pm) == 1 and pm[0]["status"] == "cancelled" and not cases_of(run, "Paloma Montague", "offboarding")
    assert not cases_of(run, "Paloma Brannigan")  # birthday gift only: out of scope


def test_identity_merge_needs_onboarding_evidence(run):
    reg = run["reg"]
    chiara = pid(run, "Chiara Ekwueme")
    assert {"cekwueme@postbox.example", "chiara.ekwueme@harbourline.example"} <= set(reg.people[chiara]["emails"])
    assert reg.people[chiara].get("merged_ids")
    for name in ("Jun Hargreaves", "Noor Yardley", "Wanjiru Castellano", "Luca Bellweather", "Mateus Jaramillo"):
        ids = [p for p, x in reg.people.items() if x["display_name"] == name]
        assert len(ids) == 2, name  # kept apart
        assert all(reg.people[i].get("possible_same_person") for i in ids), name


def test_courier_delivery_links_by_open_return(run):
    for c in cases_of(run, "Pilar Lowther", "offboarding"):
        acts = [s["activity"] for s in c["steps"]]
        assert acts.index("laptop_return_arranged") < acts.index("courier_delivered") < acts.index("laptop_received")


def test_every_case_step_has_raw_ref(run):
    assert all(s["raw_ref"]["file"].startswith("data/") and s["raw_ref"]["line"] > 0 for c in run["cases"] for s in c["steps"])


def test_status_is_outcome_and_window_badges(run):
    assert {c["status"] for c in run["cases"]} <= {"complete", "in_progress", "declined", "cancelled"}
    for name, process in [("Bram Danforth", "onboarding"), ("Mateus Zielinski", "onboarding"), ("Luca Bellweather", "onboarding")]:
        cs = cases_of(run, name, process)
        assert cs and all(c["ends_after_window"] and c["status"] == "in_progress" for c in cs), name
    for name, process in [("Aarav Thorne", "offboarding"), ("Yara Hargreaves", "leave")]:
        cs = cases_of(run, name, process)
        assert cs and all(c["started_before_window"] and c["status"] == "complete" for c in cs), name


def test_last_days_for_cross_process_checks(run):
    ld = {r["name"]: r for r in run["doc"]["person_last_days"]}
    assert ld["Callum Montague"]["last_day"] == "2026-04-13"
    assert ld["Paloma Larkspur"]["last_day"] == "2026-03-24"
    assert ld["Bram Montague"]["last_day"] is None and ld["Bram Montague"]["effective_end"] == "2026-03-24"


# ----------------------------------------------------------------------------- phase 3: flags + discovery


@pytest.fixture(scope="session")
def p3(run):
    cases_out = {"cases": run["cases"], "events": run["events"], "registry": run["reg"], "doc": run["doc"]}
    return pl.run_phase3(cases_out)


def flagged(p3, rule):
    return {f["person_name"] for f in p3["flags"] if f["rule"] == rule}


def test_flag_leave_after_last_day(p3):
    assert {"Bram Montague", "Ines Marchetti"} <= flagged(p3, "activity_after_last_day")


def test_flag_onboarded_before_laptop(p3):
    assert {"Chiara Ekwueme", "Gulnara Brannigan"} <= flagged(p3, "onboarded_before_laptop")


def test_flag_open_issue_and_cancel(p3):
    assert "Otto Vasquez-Lowe" in flagged(p3, "onboarded_with_open_issue")
    assert "Hamza Vasquez-Lowe" in flagged(p3, "cancel_no_followup")
    assert any(f["rule"] == "sick_leave_two_ways" and f["scope"] == "process" for f in p3["flags"])


def test_every_flag_has_evidence(p3):
    assert all(f["evidence_event_ids"] and f["message"] for f in p3["flags"])


def test_discovery_not_hardcoded(p3):
    leave = p3["models"]["leave"]
    assert leave["main_path"]["activities"][0] == "leave_requested"
    assert all(3 <= len(m["open_questions"]) <= 5 for m in p3["models"].values())
