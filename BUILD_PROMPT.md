# Mission Control: build spec for Claude Code

> How to use: put this file in the repo root as `BUILD_PROMPT.md`, with the data in `data/`.
> Tell Claude Code: **"Read BUILD_PROMPT.md. Do Phase 0 only. Stop and print the phase report."**
> Then do one phase at a time. Do not start a new phase until the human says so.

---

## 1. Goal

Build **Mission Control**, a process-intelligence prototype for Teams Squared.
It rebuilds real work processes from digital traces (mail, calendar, Teams, screen logs) for the People team of Harbourline Talent (fictional, synthetic data, 2–29 March 2026, Asia/Colombo), and lets staff **confirm, reject, or add** steps.

Deliverables (from the brief):

1. Clickable prototype (runs locally with one command; deployable to Render)
2. Architecture: how data moves from raw files to screens
3. Schemas and the output file of each pipeline step (committed in `out/`)
4. Short README

Scope, in priority order: **Leave → Offboarding → Onboarding (with induction)**. Recruitment (HireTrack / Recruitment tracker) and laptop _replacements_ are out of scope. Show them as "seen, not modelled".

Treat the data as real employee data: no data leaves the machine, and no external APIs.

---

## 2. Tech stack (fixed)

| Layer    | Choice                                                                                                   |
| -------- | -------------------------------------------------------------------------------------------------------- |
| Pipeline | Python 3.11+, standard library + `pydantic`. One file: `pipeline/pipeline.py`                            |
| Backend  | FastAPI + Pydantic v2 + SQLite (`sqlite3` or SQLModel). File: `backend/app.py`                           |
| Frontend | React + Vite + TypeScript + Tailwind CSS + shadcn/ui + lucide-react icons                                |
| Tests    | `pytest` for pipeline rules and name matching                                                            |
| Deploy   | One Dockerfile. FastAPI serves the built frontend at `/` and the API at `/api`. `render.yaml` for Render |

No LLM calls. Classification uses explicit text rules (the messages are templated). The README must explain where an LLM would fit in production (free-text mail, new templates, name resolution fallback).

---

## 3. Repo layout

```
mission-control/
  data/                      # raw export (read-only, never modified)
  pipeline/
    pipeline.py              # all steps; `python pipeline/pipeline.py`
    rules.py                 # optional: regex rule table if pipeline.py gets too long
    tests/test_rules.py
  out/                       # committed outputs of each step
    0_profile.json
    1_events.jsonl
    2_events_clean.jsonl
    2_people.json
    3_cases.json
    4_processes.json
    5_flags.json
    pipeline_report.json
  backend/
    app.py
    db.py
    schemas.py               # Pydantic models = the documented schemas
  frontend/                  # Vite app
  docs/
    architecture.md          # Mermaid diagram + explanation
    schemas.md               # generated or hand-written from schemas.py
  Dockerfile
  render.yaml
  Makefile                   # make pipeline / make dev / make build
  README.md
```

---

## 4. The data: facts you must respect

Files: `data/_shared/{directory.json, export_window.json, teams_channel/messages.jsonl}` and `data/<person>/{outlook/messages.jsonl, outlook/calendar.jsonl, teams/messages.jsonl, screens/screen_log.jsonl}` for `hana, lerato, pavel, mateus, ravi, yannick`.

- `directory.json` has 12 staff; only 6 are exported (`exported: true`). The other 6 (Account Managers Teodor, Vesna, Kenji; IT Kavya, Tobias; Finance Ilse) appear only as senders or recipients. **The UI must always say: "Data from 6 of 12 staff."**
- Workers, new starters and client contacts are **not** in the directory. Build your own person registry.
- Hana and Lerato (People Operations) run leave, onboarding and offboarding. Pavel and Mateus V-L (Talent Partners) do recruiting. Ravi buys laptops. Yannick (Head of People) approves.

### Time formats (convert everything to Asia/Colombo, and also store UTC)

| Source               | Field                                                             | Format                                            |
| -------------------- | ----------------------------------------------------------------- | ------------------------------------------------- |
| Mail                 | `sentDateTime` (fallback `receivedDateTime`)                      | UTC `...Z`                                        |
| Teams chat / channel | `createdDateTime`                                                 | UTC `...Z`                                        |
| Calendar             | `start.dateTime` + `start.timeZone` = `"Sri Lanka Standard Time"` | naive local; map Windows TZ name → `Asia/Colombo` |
| Screen log           | `captured_at`                                                     | `+05:30` offset; ~5% have microseconds            |

### Duplicates

The same item appears in several mailboxes. Deduplicate and keep a `seen_in: [mailboxes]` list:

- mail by `internetMessageId`
- Teams chat by message `id` (both members export the same chat)
- calendar by `iCalUId` (the team sync is in all 6 calendars)

### Screen log

- `app` is **not reliable**: PeopleHub pages sometimes have `app: "excel"`, and the Leave tracker sometimes has `app: "chrome"`. Classify by `window_title` and `url` only.
- A screen record shows what was **open**, not what was **done**. Every step from screen data is labelled **"likely"**.
- Drop as noise: BBC, YouTube, Spotify, lock screen (`lockapp`), LinkedIn feed, Google Search, timeanddate, File Explorer, and any record with `idle_seconds` > 300.
- Generic screens (`Inbox - ... - Outlook`, `Chat | Microsoft Teams`, `Activity | ...`) are kept as "context" but never become case steps.
- `Leave tracker 2026.xlsx` has **no person name**. Link it to a case only by time (within 30 min after a PeopleHub or approval step by the same staff member) with confidence `low`.

### Noise (classify, never delete; keep with `category: "noise"` and a reason)

- Teams small talk: `lunch?`, `coffee ☕`, `thanks!`, `👍`, `running 5 min late`, `are you joining the sync?`, `can you cover my inbox for an hour`, `the VPN is slow again`, `did you see X's message?`, `who's updating the tracker today?`
- Mail newsletters: senders `@hrbrew.example`, `@hiretrack.example`, `@linkedin.example`
- Mail out of scope: payslip, timesheet and invoice queries
- Calendar out of scope: `Weekly People team sync`, `1:1 ...`, `Focus time`
- Channel `General` posts

---

## 5. Activity rules (text → activity label)

Match case-insensitively on body text (strip HTML), subject and window title. Each rule outputs `activity`, `subject_name_raw` (the name as written), and extracted fields (dates, client, etc.). Put the rules in one table so the README can show them.

### Leave

| activity                        | source                                   | pattern (simplified)                                                                          |
| ------------------------------- | ---------------------------------------- | --------------------------------------------------------------------------------------------- |
| `leave_requested`               | Teams                                    | `can I take (annual leave\|sick leave\|a personal day) on <dates>`                            |
| `leave_requested`               | Mail in                                  | subject `Leave request – <dates>`, body `I'd like to request <type> for <dates>`              |
| `peoplehub_opened` (likely)     | Screen                                   | title `Leave - <Full Name> - PeopleHub`                                                       |
| `client_check_sent`             | Mail out                                 | subject `Leave request – <name> – <dates>`, body `has asked for ... Is that ok on your side?` |
| `client_notified_sick`          | Mail out                                 | subject `<Name> – sick leave <dates>`, body `is unwell and off`                               |
| `client_approved`               | Mail in (reply in same `conversationId`) | `Approved, thanks` \| `Yes, that's fine` \| `No problem`                                      |
| `client_declined`               | Mail in                                  | `could they pick other dates`                                                                 |
| `worker_approved`               | Teams / Mail out                         | `Your leave for <dates> is approved`                                                          |
| `worker_asked_other_dates`      | Teams / Mail out                         | `The client asked if you could choose other dates`                                            |
| `cancel_requested`              | Teams / Mail                             | `won't need the leave on <dates> after all`                                                   |
| `tracker_updated` (likely, low) | Screen                                   | `Leave tracker 2026.xlsx` (time link only)                                                    |

Leave case key = **worker + date range**. Join with, in this order: (1) `conversationId` / `chatId` threads, (2) date range + resolved worker, (3) time order.
Real pattern found: PeopleHub opens 10–15 min **before** the client check. Do not hardcode that order; discover it (Section 8).

### Offboarding

| activity                     | pattern                                                                                                                                                                                  |
| ---------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `resignation_received`       | subject `Resignation`, body `my last working day will be <date>`                                                                                                                         |
| `client_ended_engagement`    | subject `<Name> – end of engagement`, body `last day <date>`                                                                                                                             |
| `offboarding_acknowledged`   | `I'll send the next steps shortly` \| `we'll handle the offboarding`                                                                                                                     |
| `access_disable_requested`   | Teams to IT: `<name> finishes <date>, can you disable access end of day`                                                                                                                 |
| `courier_booked` (likely)    | Screen `Book a pickup \| SwiftParcel`                                                                                                                                                    |
| `laptop_return_arranged`     | Mail out `Returning your laptop`                                                                                                                                                         |
| `courier_delivered` (likely) | Mail from `@swiftparcel.example` `Delivered: consignment SP...`. **No name**: link to the open return case whose `laptop_return_arranged` is before it and `laptop_received` is after it |
| `laptop_received`            | Teams from IT `Got <name>'s laptop back, wiped`                                                                                                                                          |
| `offboarding_completed`      | Mail out `Offboarding complete – <Full Name>`                                                                                                                                            |

### Onboarding (one lifecycle: induction → placement; one case per new starter; the case can span Hana's and Lerato's files)

| activity                                                | pattern                                                                                                                                                                                      |
| ------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `contract_sent`                                         | Mail out `Your contractor agreement – Harbourline Talent` (to a personal email)                                                                                                              |
| `contract_reminder`                                     | `Just a gentle reminder about the agreement`                                                                                                                                                 |
| `contract_signed`                                       | Mail in `Signed copy attached`                                                                                                                                                               |
| `training_enrolled`                                     | Mail out `Pre-start training modules`; screen `Learners - Harbourline Academy` = likely                                                                                                      |
| `induction_meeting`                                     | Calendar `Induction – <First> <Initial>.` (use attendee email to resolve)                                                                                                                    |
| `induction_completed`                                   | Teams `<name> finished induction, good to go for <Client>`                                                                                                                                   |
| `welcome_sent`                                          | Mail `Welcome to Harbourline Talent!` → extract `first day with <Client> is <date>`                                                                                                          |
| `laptop_requested`                                      | Channel Procurement root `Laptop needed for <name> (new starter), <Client>, needed by <date>`. `(replacement)` = out of scope                                                                |
| `laptop_quote` / `laptop_approved` / `laptop_delivered` | Replies in the same thread (`replyToId`): `<model> from <vendor>, ~N AUD, ok?` / Yannick `Approved\|ok approved\|Go ahead` / `<name> has the laptop now`                                     |
| `it_requested`                                          | Teams to IT `can you set up M365, VPN and the timesheet app for <name>? Starts <date> at <Client>`                                                                                           |
| `it_ready`                                              | `all set for <name>` \| `Accounts created 👍` \| `Done, temp password sent to their personal email` (the last two have no name: link to the latest open `it_requested` in the **same chat**) |
| `kickoff_meeting`                                       | Calendar `Kick-off: <Full Name> x <Client>`                                                                                                                                                  |
| `day_one_checkin` / `day_one_reply`                     | `How was day one?` and the reply. Flag the reply if it mentions a problem ("still waiting", "missing")                                                                                       |
| `onboarded_confirmed`                                   | Teams `<name> onboarded at <Client> ✅`                                                                                                                                                      |

---

## 6. Name resolution (the hardest part; test it well)

Build `people.json` from every email address and display name seen. Each person gets a stable `person_id`.

Resolution order for a raw name in text:

1. **Email address**: exact.
2. **Full name**: exact, case-insensitive. Merge personal and work addresses with the same full name (for example `cekwueme@postbox.example` and `chiara.ekwueme@harbourline.example`).
3. **First name + initial** (`Vida F.`, `Otto V.`, `Luca B.`).
4. **First name only, or a typo** (edit distance ≤ 2: `Chaira`, `Hmaza`, `Jvoana`, `Qunin`, `Snane`→Sanne): pick from candidates that have an open case **of the same process** near that date, with the same client if one is named. If more than one candidate remains, mark it `ambiguous`. Do not guess.
5. Staff names are never case subjects (`Lerato finished induction` = Lerato **Thorne**, a new starter, not Lerato Faraday).

Store `resolution: {method, confidence, candidates}` on each event.

### Must-pass tests (put these in `pipeline/tests/test_rules.py`)

- `Got Bram's laptop back, wiped` (23 Mar) → **Bram Montague** (offboarding). Bram Danforth is a new starter (starts 30 Mar) with no laptop to return.
- Mateus **Zielinski** (new starter) ≠ Mateus **Vasquez-Lowe** (staff).
- Three Hamzas: Vasquez-Lowe (leave, then cancelled), Pemberton (leave + resignation), Galloway (leave).
- Two Quinns: Ellingham (offboarding, "Qunin" typo) ≠ Quillfeather (leave).
- Hana **Prescott** (worker asking for leave) ≠ Hana **Pemberton** (staff).
- Ravi **Kettering** (laptop replacement) ≠ Ravi **Larkspur** (staff).
- Clients vs workers: Kavya Quintero (client) ≠ Kavya Jaramillo (IT); Chiara Yilmaz (client) ≠ Chiara Ekwueme; Jasper Dunmore (client) ≠ Jasper Haverford; Jovana Ashcombe (client) ≠ Jovana Penhaligon; Noor Galloway (client) ≠ Noor Yardley; Tobias Trelawney (worker) ≠ Tobias Northcott (IT).
- `Chaira Ekwueme onboarded` → Chiara Ekwueme. `Snane (new starter), Greythorne` → Sanne Yilmaz.
- Jovana Penhaligon has **two** leave cases: 1–2 Apr (Hana, client declined) and 31 Mar–1 Apr (Lerato, approved).
- Lerato: `Callum finishes Mon 13 Apr` must be resolved by context or marked `ambiguous` (four Callums exist).

---

## 7. Case status and confidence

**Case status:** `complete` | `in_progress` | `cut_off` (the case starts before 2 Mar or its expected end is after 29 Mar) | `declined` | `cancelled`.
Cut-off examples: Bram Danforth, Mateus Zielinski and Luca Bellweather start after 29 Mar; Aarav Thorne's offboarding trigger is before 2 Mar; Yara's leave request is before the window. Never call a cut-off case "missing step".

**Step confidence:**

- `high`: an explicit message names the action and the person, or the event is linked by thread id
- `medium`: a calendar event, or the person was resolved by fuzzy/context match
- `low`: a screen-only step, or linked by time only. The UI shows this as **"Likely"**

---

## 8. Process discovery (do not hardcode the order)

For each process, from its cases:

- step frequency (% of cases that contain each activity)
- directly-follows graph (counts of A → B)
- main path = the most common ordered variant; other variants listed with counts (for example "client declined" and "cancelled")
- median time between consecutive main-path steps
- the steps with low support, shown as "optional"

Write the result to `out/4_processes.json`.

---

## 9. Flags (anomalies: the "insight" part of the demo)

Rules → `out/5_flags.json`, each with `case_id`, `rule`, `message`, `evidence_event_ids`:

- leave approved for a date on or after the person's last day or offboarding completion (Bram Montague 30 Mar; Ines Marchetti 31 Mar)
- `onboarded_confirmed` before `laptop_delivered` (Chiara, Gulnara)
- `laptop_requested` posted after its own "needed by" date (about 8 cases)
- `onboarded_confirmed` while the day-one reply reports an open issue (Otto: DMS access)
- `cancel_requested` with no later action in the data
- sick leave handled two ways (notify vs ask the client): a process-level flag asking staff to confirm the rule

---

## 10. Schemas (Pydantic in `backend/schemas.py`, documented in `docs/schemas.md`)

```python
class Event:          # out/1 and out/2
    event_id: str            # "<source>:<native id>"
    source: Literal["mail","calendar","teams_chat","teams_channel","screen"]
    mailbox: str             # whose export it came from (first seen)
    seen_in: list[str]
    time_utc: datetime
    time_local: datetime     # Asia/Colombo
    actor_id: str | None
    recipients: list[str]
    title: str | None        # subject / window title / meeting subject
    text: str                # plain text
    category: Literal["process","context","noise","out_of_scope"]
    noise_reason: str | None
    activity: str | None
    process: Literal["leave","offboarding","onboarding"] | None
    subject_person_id: str | None
    resolution: dict | None  # method, confidence, candidates
    fields: dict             # dates, client, vendor, amount...
    thread_key: str | None   # conversationId / chatId / replyToId root
    raw_ref: {"file": str, "line": int}

class Person:   person_id, display_name, emails[], kind ("staff"|"worker"|"new_starter"|"client"|"it"|"vendor"|"unknown"), org, exported: bool
class CaseStep: activity, event_id, time_local, actor_id, confidence ("high"|"medium"|"low"), likely: bool
class Case:     case_id, process, subject_person_id, owner_staff_id, client, status, start, end, steps[CaseStep], flags[str], summary: str
class ProcessModel: process, case_count, status_counts, steps[{activity, label, support_pct, confidence_mix, median_to_next_h}], dfg[{from,to,count}], variants[{path[], count, case_ids[]}]
class Feedback: id, created_at, user, target ("process_step"|"case_step"|"case"), process, case_id?, activity?, event_id?, verdict ("confirm"|"reject"|"add"), note, proposed_step?
```

---

## 11. Backend API (FastAPI)

- `GET  /api/meta`: coverage (6/12 staff, who is missing), export window, pipeline counts per stage
- `GET  /api/processes` / `GET /api/processes/{process}`
- `GET  /api/cases?process=&status=&flagged=&q=` / `GET /api/cases/{case_id}`
- `GET  /api/events/{event_id}/raw`: returns the **original raw JSON line**, unchanged, with file + line number
- `GET  /api/flags`
- `GET  /api/people/{person_id}`
- `POST /api/feedback` / `GET /api/feedback` / `GET /api/feedback/export` (JSONL download)

Load `out/*.json` at startup (read-only). Feedback goes to SQLite (`backend/feedback.db`) **and** is appended to `out/feedback.jsonl`. Pydantic models for all responses, so `/docs` is clean (reviewers will open it).

---

## 12. UI spec: minimal, professional, calm

**Style:** Linear / Vercel dashboard. White background, zinc grays, **one** accent (indigo-600), Inter font, 14px base, 8px radius, 1px borders, no shadows, no gradients, no emoji in the UI chrome. Dense, aligned tables. Lots of white space. Light mode only (dark mode is optional, at the end).

**Layout:** left sidebar (Overview, Leave, Offboarding, Onboarding, Cases, Flags, Feedback, How it works) + a slim top bar showing a persistent coverage notice: _"Data from 6 of 12 staff (People team). Account Managers, IT and Finance not exported."_ + a "Reviewing as: [Hana ▾]" selector (no auth).

**Screens**

1. **Overview**: 4 stat tiles (raw records → after cleaning → cases → steps waiting for review); 3 process cards (case count, % complete, median duration, validation progress bar); top 5 flags.
2. **Process page**: the **process map** (horizontal boxes and arrows for the main path; each box shows label, `% of cases`, a confidence dot, median time to the next step; optional steps dashed; variants as small branches or a list below). Click a step → side panel with example evidence and Confirm / Reject / Comment. "Add a missing step" button.
3. **Cases**: table (person, process, client, status badge, steps, flags, last activity) with filters and search.
4. **Case detail**: header (person, client, owner, status, dates); vertical **timeline** of steps (time, label, actor, source icon, confidence badge; "Likely" tag on screen-based steps); each step expands to show the **raw record** (pretty JSON, file + line) and Confirm / Reject; flags panel; "Add a missing step" form.
5. **Flags**: list grouped by rule, linking to cases.
6. **Feedback**: log table + "Export JSONL".
7. **How it works**: the pipeline as 6 boxes with record counts per stage, links to each `out/` file, and the rule table.

**UX details:** skeleton loaders; empty states; toast on feedback saved; the URL holds state (`/cases/:id`); keyboard focus visible; no raw ids in the UI (show names). The timezone note "All times in Sri Lanka time (UTC+05:30)" sits under each timeline.

---

## 13. Phases (stop after each one and print the report)

**Phase 0, Setup + profile.** Create the repo layout. Write `out/0_profile.json`: per person per source: record counts, time range, time-format variants, duplicate counts across mailboxes. Report: a counts table.

**Phase 1, Ingest + clean.** Steps 1–2 → `1_events.jsonl`, `2_events_clean.jsonl`, `2_people.json`. Report: counts at each stage (raw, after dedup, noise, out of scope, process events); the 20 hardest name resolutions with method; all `ambiguous` ones.

**Phase 2, Cases.** → `3_cases.json`. Report: cases per process and status; full step list for these test cases: Hamza Vasquez-Lowe leave, Jovana's two leave cases, Bram Montague offboarding, Bram Danforth onboarding, Vida Faraday onboarding (Hana → Lerato handoff), Otto Vasquez-Lowe onboarding (Lerato → Hana). `pytest` must pass.

**Phase 3, Discovery + flags.** → `4_processes.json`, `5_flags.json`, `pipeline_report.json`. Report: the main path per process with support %, the variants, and all flags.

**Phase 4, Backend.** FastAPI + SQLite feedback. Report: list of endpoints, and sample curl output for `/api/cases/{one id}`.

**Phase 5, Frontend.** All screens in Section 12. Report: screenshots or the list of routes, plus any spec item not done.

**Phase 6, Ship.** `README.md` (what it is, how to run in one command, architecture, design choices, limits, what's next), `docs/architecture.md` (Mermaid), `docs/schemas.md`, Dockerfile, `render.yaml`, Makefile. Check a clean clone runs with: `make pipeline && make dev`.

---

## 14. Rules for Claude Code

- Never modify `data/`.
- Every case step must link to a raw record (`raw_ref`). No step without proof.
- Prefer marking something `ambiguous` or `low` over guessing. Honest labels beat clever guesses.
- Keep `pipeline.py` deterministic: same input → same output (sort keys, stable ids).
- If a rule in this spec conflicts with what the data shows, **stop and report it**. Do not silently "fix" the spec.
- Commit at the end of each phase with a clear message.
