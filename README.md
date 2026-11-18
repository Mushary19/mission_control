# Mission Control

A process-intelligence prototype for the People team of Harbourline Talent (synthetic data, 2–29 March 2026).
It rebuilds **leave, offboarding and onboarding** from mail, calendar, Teams and screen activity, shows each case with proof,
and lets staff **confirm, reject or add** steps and answer open questions. Everything runs locally; no data leaves the machine.

![Overview](docs/screenshots/01-overview.png)

## Run it

```bash
make install start          # Python venv + npm deps, build the UI, serve UI + API on http://localhost:8000
```

`out/` is committed, so the app runs without the raw export. To rebuild `out/` and see the raw "Proof" records,
put the export in `data/` (`data/_shared/…`, `data/<person>/…`; it is git-ignored) and run `make pipeline`.

| command | what it does |
|---|---|
| `make install` | `.venv` with backend + test deps, `npm ci` in `frontend/` |
| `make pipeline` | `data/` → `out/` (7 steps, deterministic) |
| `make dev` | API on :8000 (reload) + Vite on :5173 (proxies `/api`) |
| `make test` | 102 pytest tests (pipeline rules, name resolution, every endpoint, API snapshots) + ruff |
| `make build` / `make start` | build `frontend/dist`; FastAPI serves it at `/` and the API at `/api` (docs at `/docs`) |
| `docker build -t mission-control . && docker run -p 8000:8000 mission-control` | same, in one image |

**Hosted demo (Render):** `render.yaml` defines one Docker web service. Deploy it from a **private copy of the repo that includes `data/`**.
The raw export must not go into a public repo. Without `data/` the app works, but the Proof panel says "Raw data not available on this server".
On the free plan, feedback (SQLite) is lost on redeploy.

## What it found

1. **Laptops come after the start date, for every new starter (9 of 9).** Requests went to Procurement 2–4 days after the needed-by date, which is always the start date. 5 starters were confirmed "onboarded" 5–10 days before their laptop arrived.
2. **Starters are confirmed onboarded with client DMS access still missing:** 4 of the 9 who answered the day-one check-in, at 4 different clients.
3. **Leave approved after people had left:** Bram Montague, Ines Marchetti, Jasper Haverford and Pilar Lowther. A replacement laptop was also ordered for Paloma Larkspur on her last day.
4. **Sick leave is handled two ways:** 7 of 12 sick-leave cases asked the client for approval, 5 only told the client. Both staff members do both.
5. **Some loops never close.** Two leave cancellations have no follow-up. The Leave tracker is opened right after an approval in only 8 of 41 leave cases, so it is probably updated in batches. That is one of the 14 open questions for staff.

## How it works

Raw files → 7 pipeline steps (profile, ingest, clean, cases, discover, flags, insights), each writing one `out/` file → FastAPI → React → feedback back to SQLite and `out/feedback.jsonl`.
Details and diagram: [docs/architecture.md](docs/architecture.md). Every file and response shape: [docs/schemas.md](docs/schemas.md).

## Design choices and trade-offs

* **Rules, not an LLM.** The messages are templated, so 84 text rules in one table (`pipeline/rules.py`) label every record. They are explainable and repeatable, and no data goes to an external API. In production an LLM would fit at three points: free-text mail that matches no template, suggesting rules for new templates (a human reviews them), and a fallback for names the rules leave `ambiguous`. Staff confirm the result in this UI either way.
* **A screen shows what was open, not what was done.** Screen-based steps are always "Likely". Windows are read by title and address, never by the app name, which is unreliable.
* **Window badges, not "missing steps".** The export covers 2–29 March. Cases that start earlier or continue later get a badge, and the status stays the outcome (complete, in progress, declined, cancelled).
* **Name resolution with reasons.** Email, then full name, then first name plus initial, then first name or typo using case context (same process, open case, same dates or client). Every match stores a sentence, for example "Only Callum with an offboarding case near this date; last day Mon 13 Apr matches". When more than one person fits, it is marked `ambiguous` instead of guessed. A personal and a work address are merged only with onboarding evidence; otherwise the UI asks "Is this the same person?".
* **Data from 6 of 12 staff.** Account Managers, IT and Finance were not exported, so some triggers and confirmations are invisible. The UI says so on every page.

## Limits

* One month of synthetic, templated data. The rules would need work for real free text.
* Onboarding has only 3 complete in-window cases, so its path confidence is **low**. Offboarding (4) is medium. Leave (29) is high.
* Nameless screen steps (the Leave tracker, SwiftParcel, the Academy) join a case by time only. Most Leave-tracker sessions stay unlinked.
* There is no login: "Reviewing as" is a picker. Feedback does not change the model yet.

## What I'd do next

1. Feed confirmed and rejected steps back into the rules and case linking, and re-run with a "validated" layer.
2. Ask staff the 14 open questions, then encode the answers: sick-leave rule, tracker batching, when to request laptops.
3. Add the Account Manager and IT mailboxes to close the missing triggers. Use an LLM only for the free-text and ambiguous-name fallback.
4. Turn the patterns into alerts: "laptop not requested 5 days before start", "leave request after last day".

## Repo map

```
pipeline/       pipeline.py (steps 0–6), rules.py (rule table), tests/test_rules.py
out/            committed outputs of every step (+ feedback.jsonl at runtime, git-ignored)
backend/app/    main.py, config.py, store.py, db.py, routers/, services/, schemas/ (Pydantic)
backend/tests/  endpoint tests, feedback round trip, API snapshots
frontend/       React + Vite + TS + Tailwind; scripts/screenshots.mjs (demo-path check)
docs/           architecture.md, schemas.md, demo-script.md, BUILD_PROMPT.md, screenshots/
scripts/        gen_schemas.py (writes docs/schemas.md)
Makefile  Dockerfile  render.yaml  requirements.txt  requirements-dev.txt
```
