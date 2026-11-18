"""Mission Control pipeline.

Run:  python pipeline/pipeline.py            (all implemented steps)
      python pipeline/pipeline.py run        (steps 1-3 + report)

Steps (each writes to out/):
  0 profile   -> out/0_profile.json
  1 ingest    -> out/1_events.jsonl                       (Phase 1)
  2 clean     -> out/2_events_clean.jsonl, 2_people.json  (Phase 1)
  3 cases     -> out/3_cases.json                         (Phase 2)
  4 discover  -> out/4_processes.json                     (Phase 3)
  5 flags     -> out/5_flags.json, pipeline_report.json   (Phase 3; also fills case flags in 3_cases.json)

Requires Python 3.10+ (stdlib zoneinfo; no 3.11-only features).
Deterministic: same input -> same output (sorted keys, stable ordering, no wall-clock values).
Never writes to data/.
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT = ROOT / "out"

TZ_LOCAL = ZoneInfo("Asia/Colombo")
# Windows time zone names seen in calendar exports -> IANA
WINDOWS_TZ = {"Sri Lanka Standard Time": "Asia/Colombo", "UTC": "UTC"}

# source name -> (relative path inside a person folder, dedup key field or None)
PERSON_SOURCES = {
    "mail": ("outlook/messages.jsonl", "internetMessageId"),
    "calendar": ("outlook/calendar.jsonl", "iCalUId"),
    "teams_chat": ("teams/messages.jsonl", "chatId+id"),
    "screen": ("screens/screen_log.jsonl", None),
}
CHANNEL_FILE = "_shared/teams_channel/messages.jsonl"


# --------------------------------------------------------------------------- helpers


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def read_jsonl(path: Path):
    """Yield (line_number, record). Line numbers are 1-based, matching the raw file."""
    with path.open(encoding="utf-8") as fh:
        for n, line in enumerate(fh, start=1):
            if line.strip():
                yield n, json.loads(line)


def write_json(path: Path, obj, compact: bool = False) -> None:
    """Pretty JSON for small files; compact=True writes one line per top-level list item (big files)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if not compact:
        path.write_text(json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
        return
    parts = []
    for k in sorted(obj):
        v = obj[k]
        if isinstance(v, list):
            inner = ",\n".join("  " + json.dumps(x, sort_keys=True, ensure_ascii=False, separators=(",", ":")) for x in v)
            parts.append(f'"{k}": [\n{inner}\n]' if v else f'"{k}": []')
        else:
            parts.append(f'"{k}": ' + json.dumps(v, sort_keys=True, ensure_ascii=False, separators=(",", ":")))
    path.write_text("{\n" + ",\n".join(parts) + "\n}\n", encoding="utf-8")


def shape(ts: str) -> str:
    """Format fingerprint of a timestamp string: digits -> 'd'."""
    return re.sub(r"\d", "d", ts)


def parse_utc_z(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(timezone.utc)


def parse_offset(ts: str) -> datetime:
    return datetime.fromisoformat(ts).astimezone(timezone.utc)


def parse_calendar(dt: dict) -> datetime:
    """Calendar: naive local dateTime (7-digit fraction) + Windows TZ name."""
    tz = ZoneInfo(WINDOWS_TZ[dt["timeZone"]])
    raw = dt["dateTime"]
    base, _, frac = raw.partition(".")
    naive = datetime.fromisoformat(base)
    if frac:
        naive = naive.replace(microsecond=int(frac[:6].ljust(6, "0")))
    return naive.replace(tzinfo=tz).astimezone(timezone.utc)


def record_time(source: str, r: dict) -> tuple[datetime, str, str]:
    """Return (utc datetime, raw string, field used)."""
    if source == "mail":
        field = "sentDateTime" if r.get("sentDateTime") else "receivedDateTime"
        return parse_utc_z(r[field]), r[field], field
    if source in ("teams_chat", "teams_channel"):
        return parse_utc_z(r["createdDateTime"]), r["createdDateTime"], "createdDateTime"
    if source == "calendar":
        raw = f'{r["start"]["dateTime"]} [{r["start"]["timeZone"]}]'
        return parse_calendar(r["start"]), raw, "start.dateTime+start.timeZone"
    if source == "screen":
        return parse_offset(r["captured_at"]), r["captured_at"], "captured_at"
    raise ValueError(source)


def iso_pair(dt: datetime) -> dict:
    return {
        "utc": dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "local": dt.astimezone(TZ_LOCAL).isoformat(),
    }


def dedup_key(r: dict, key_field: str) -> str:
    """Dedup key; composite fields are joined with '+', e.g. 'chatId+id' -> '<chatId>|<id>'."""
    return "|".join(str(r.get(f)) for f in key_field.split("+"))


# --------------------------------------------------------------------------- step 0


def load_window() -> tuple[datetime, datetime, dict]:
    w = json.loads((DATA / "_shared/export_window.json").read_text(encoding="utf-8"))
    return datetime.fromisoformat(w["start"]), datetime.fromisoformat(w["end"]), w


def profile_file(source: str, path: Path, win_start: datetime, win_end: datetime) -> tuple[dict, list]:
    """Profile one raw file. Returns (stats, [(dedup_key, line)])."""
    key_field = PERSON_SOURCES.get(source, (None, "id"))[1] if source != "teams_channel" else "id"
    times: list[datetime] = []
    variants: Counter = Counter()
    fields_used: Counter = Counter()
    outside = 0
    keys = []
    extra: Counter = Counter()
    for line, r in read_jsonl(path):
        t, raw, field = record_time(source, r)
        times.append(t)
        variants[shape(raw)] += 1
        fields_used[field] += 1
        if not (win_start <= t <= win_end):
            outside += 1
        if key_field:
            keys.append((dedup_key(r, key_field), line))
        # source-specific facts worth knowing before ingest
        if source == "mail":
            extra[f'folder:{r.get("_folder_path")}'] += 1
        elif source == "calendar":
            extra[f'timeZone:{r["start"]["timeZone"]}'] += 1
            if r.get("isAllDay"):
                extra["all_day"] += 1
            if r.get("isCancelled"):
                extra["cancelled"] += 1
        elif source == "screen":
            if (r.get("idle_seconds") or 0) > 300:
                extra["idle_gt_300s"] += 1
            if "." in r["captured_at"]:
                extra["with_microseconds"] += 1
            extra[f'app:{r.get("app")}'] += 1
        elif source == "teams_channel":
            extra[f'channel:{r["channelIdentity"].get("_channelName")}'] += 1
            extra["root_posts" if r.get("replyToId") is None else "replies"] += 1
    within_dupes = sum(c - 1 for c in Counter(k for k, _ in keys).values() if c > 1)
    stats = {
        "file": rel(path),
        "records": len(times),
        "time_field": dict(sorted(fields_used.items())),
        "time_range": {
            "first": iso_pair(min(times)) if times else None,
            "last": iso_pair(max(times)) if times else None,
        },
        "time_format_variants": dict(sorted(variants.items())),
        "outside_export_window": outside,
        "duplicates_within_file": within_dupes,
        "facts": dict(sorted(extra.items())),
    }
    return stats, keys


def step0_profile() -> dict:
    win_start, win_end, window = load_window()
    directory = json.loads((DATA / "_shared/directory.json").read_text(encoding="utf-8"))["value"]
    exported = [d for d in directory if d.get("exported")]
    folders = sorted(d["export_folder"] for d in exported)
    folder_to_name = {d["export_folder"]: d["displayName"] for d in exported}

    per_person: dict = {}
    # source -> key -> set(mailboxes)
    key_owners: dict[str, dict[str, set]] = defaultdict(lambda: defaultdict(set))
    key_lists: dict[tuple[str, str], list] = {}

    for folder in folders:
        per_person[folder] = {"display_name": folder_to_name[folder], "sources": {}}
        for source, (relpath, _) in PERSON_SOURCES.items():
            path = DATA / folder / relpath
            if not path.exists():
                per_person[folder]["sources"][source] = {"file": rel(path), "missing": True, "records": 0}
                continue
            stats, keys = profile_file(source, path, win_start, win_end)
            per_person[folder]["sources"][source] = stats
            key_lists[(folder, source)] = keys
            for k, _ in keys:
                key_owners[source][k].add(folder)

    # cross-mailbox duplicate counts
    for (folder, source), keys in key_lists.items():
        shared = sum(1 for k, _ in keys if len(key_owners[source][k]) > 1)
        per_person[folder]["sources"][source]["duplicates_across_mailboxes"] = shared
        per_person[folder]["sources"][source]["unique_to_this_mailbox"] = len(keys) - shared

    dedup_summary = {}
    for source in ("mail", "calendar", "teams_chat"):
        owners = key_owners[source]
        raw_total = sum(len(key_lists[(f, source)]) for f in folders if (f, source) in key_lists)
        spread = Counter(len(v) for v in owners.values())
        dedup_summary[source] = {
            "key": PERSON_SOURCES[source][1],
            "raw_records": raw_total,
            "unique_items": len(owners),
            "removed_by_dedup": raw_total - len(owners),
            "items_by_mailbox_count": {str(k): spread[k] for k in sorted(spread)},
        }
    screen_total = sum(per_person[f]["sources"]["screen"]["records"] for f in folders)
    dedup_summary["screen"] = {"key": None, "raw_records": screen_total, "note": "per-person; no cross-mailbox dedup"}

    channel_stats, channel_keys = profile_file("teams_channel", DATA / CHANNEL_FILE, win_start, win_end)
    dedup_summary["teams_channel"] = {
        "key": "id",
        "raw_records": channel_stats["records"],
        "unique_items": len({k for k, _ in channel_keys}),
        "note": "single shared export",
    }

    raw_total = sum(v["raw_records"] for v in dedup_summary.values())
    profile = {
        "step": "0_profile",
        "export_window": window,
        "coverage": {
            "staff_in_directory": len(directory),
            "staff_exported": len(exported),
            "label": f"Data from {len(exported)} of {len(directory)} staff.",
            "exported": [{"folder": d["export_folder"], "name": d["displayName"], "jobTitle": d["jobTitle"]} for d in sorted(exported, key=lambda d: d["export_folder"])],
            "not_exported": [{"name": d["displayName"], "jobTitle": d["jobTitle"], "mail": d["mail"]} for d in sorted(directory, key=lambda d: d["displayName"]) if not d.get("exported")],
        },
        "per_person": per_person,
        "shared": {"teams_channel": channel_stats},
        "dedup_summary": dedup_summary,
        "totals": {"raw_records": raw_total},
    }
    write_json(OUT / "0_profile.json", profile)
    return profile




# --------------------------------------------------------------------------- shared: text + names

import html as _html
import unicodedata
from datetime import date, timedelta

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rules as R  # noqa: E402

YEAR = 2026
MONTHS = {m: i for i, m in enumerate(["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}
WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

VENDOR_DOMAINS = {"hrbrew.example", "hiretrack.example", "linkedin.example", "hamperly.example", "lapworks.example", "techdirect.example", "swiftparcel.example"}
PERSONAL_DOMAINS = {"postbox.example", "mailbox.example", "inbox.example"}
WORK_DOMAIN = "harbourline.example"
STAFF_TITLES_IT = {"IT Support"}
NOT_SUBJECT = {"staff", "it", "client", "vendor"}  # spec 6.5: staff are never case subjects
TEXT_LIMIT = 200  # chars of text kept in out/ files; the full record is read from data/ by raw_ref
SESSION_GAP = timedelta(minutes=10)
IDLE_LIMIT = 300


def strip_html(s: str) -> str:
    s = re.sub(r"<br\s*/?>|</p>", "\n", s or "", flags=re.I)
    s = re.sub(r"<[^>]+>", "", s)
    return _html.unescape(s).replace("\r\n", "\n").strip()


def norm(s: str) -> str:
    """Lowercase, strip accents and possessive, collapse spaces."""
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"['’]s\b", "", s.lower())
    s = re.sub(r"[^\w.\- ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", norm(s)).strip("-")


def osa_distance(a: str, b: str) -> int:
    """Optimal string alignment distance (Levenshtein + adjacent transposition)."""
    d = [[0] * (len(b) + 1) for _ in range(len(a) + 1)]
    for i in range(len(a) + 1):
        d[i][0] = i
    for j in range(len(b) + 1):
        d[0][j] = j
    for i in range(1, len(a) + 1):
        for j in range(1, len(b) + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + cost)
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                d[i][j] = min(d[i][j], d[i - 2][j - 2] + 1)
    return d[len(a)][len(b)]


def closest(dist: dict[str, int], limit: int = 2) -> list[str]:
    """Candidates at the minimum edit distance, if that distance is <= limit."""
    if not dist:
        return []
    best = min(dist.values())
    return sorted(pid for pid, d in dist.items() if d == best) if best <= limit else []


def parse_day(s: str) -> tuple[str | None, str | None]:
    """'Mon 30 Mar' -> ('2026-03-30', warning|None)."""
    m = re.match(r"(\w{3}) (\d{1,2}) (\w{3})", s.strip())
    if not m:
        return None, f"unparsed date {s!r}"
    dow, d, mon = m.groups()
    dt = date(YEAR, MONTHS[mon.title()], int(d))
    warn = None if WEEKDAYS[dt.weekday()] == dow.title() else f"weekday mismatch in {s!r} ({WEEKDAYS[dt.weekday()]})"
    return dt.isoformat(), warn


def parse_range(s: str) -> dict:
    parts = [p.strip() for p in s.split("–")]
    start, w1 = parse_day(parts[0])
    end, w2 = parse_day(parts[-1]) if len(parts) > 1 else (start, None)
    out = {"raw": s, "start": start, "end": end}
    warns = [w for w in (w1, w2) if w]
    if warns:
        out["warnings"] = warns
    return out


def to_iso_z(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def to_local(dt: datetime) -> str:
    return dt.astimezone(TZ_LOCAL).isoformat()


def ts(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def nice_day(iso: str | None) -> str:
    if not iso:
        return "?"
    d = date.fromisoformat(iso)
    return f"{WEEKDAYS[d.weekday()]} {d.day} {['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][d.month-1]}"


def addr(x: dict) -> tuple[str, str]:
    e = x.get("emailAddress", x)
    return e.get("name") or "", (e.get("address") or "").lower()


def domain_of(email: str) -> str:
    return email.split("@")[-1].lower() if email else ""


# --------------------------------------------------------------------------- person registry


class Registry:
    """Identities from headers. One identity per email address; Teams names attach to the work address
    with the same name (a Teams account is an M365 work account). Personal and work addresses with the
    same full name stay SEPARATE here; step 2 merges them only with onboarding evidence."""

    def __init__(self, directory: list[dict], header_pairs: Counter, teams_names: dict[str, set]):
        self.people: dict[str, dict] = {}
        self.by_email: dict[str, str] = {}
        self.by_teams_id: dict[str, str] = {}
        self.by_teams_name: dict[str, str] = {}
        self.orgs: dict[str, dict] = {"o_harbourline": {"org_id": "o_harbourline", "name": "Harbourline Talent", "kind": "employer", "domains": [WORK_DOMAIN]}}
        staff = {d["mail"].lower(): d for d in directory}

        # 1) collect identities: email -> most common display name
        names_for: dict[str, Counter] = defaultdict(Counter)
        for (name, email), n in header_pairs.items():
            if email:
                names_for[email][name] += n
        for email, d in staff.items():
            names_for[email][d["displayName"]] += 1000
        idents = []  # (display, email|None, teams_ids)
        for email in sorted(names_for):
            display = sorted(names_for[email].items(), key=lambda kv: (-kv[1], kv[0]))[0][0] or email
            idents.append({"display": display, "email": email, "teams_ids": set()})
        work_by_name = defaultdict(list)
        any_by_name = defaultdict(list)
        for i in idents:
            any_by_name[norm(i["display"])].append(i)
            if domain_of(i["email"]) == WORK_DOMAIN:
                work_by_name[norm(i["display"])].append(i)
        teams_attach = {}
        for tname in sorted(teams_names):
            n = norm(tname)
            if len(work_by_name[n]) == 1:
                target = work_by_name[n][0]
            elif not work_by_name[n] and len(any_by_name[n]) == 1:
                target = any_by_name[n][0]
            else:
                target = {"display": tname, "email": None, "teams_ids": set()}
                idents.append(target)
                any_by_name[n].append(target)
            target["teams_ids"] |= teams_names[tname]
            teams_attach[n] = target

        # 2) stable ids: per name, work address first, then Teams-only, personal, other
        def rank(i):
            dom = domain_of(i["email"] or "")
            return (0 if dom == WORK_DOMAIN else 1 if i["email"] is None else 2 if dom in PERSONAL_DOMAINS else 3, i["email"] or "")

        groups = defaultdict(list)
        for i in idents:
            groups[slug(i["display"])].append(i)
        for s in sorted(groups):
            used = Counter()
            for k, i in enumerate(sorted(groups[s], key=rank)):
                if k == 0:
                    pid = f"p_{s}"
                else:
                    dom = domain_of(i["email"] or "")
                    label = "personal" if dom in PERSONAL_DOMAINS else "teams" if i["email"] is None else dom.split(".")[0]
                    used[label] += 1
                    pid = f"p_{s}-{label}" + (f"-{used[label]}" if used[label] > 1 else "")
                i["pid"] = pid
        for i in idents:
            email = i["email"]
            d = staff.get(email or "")
            kind = ("it" if d["jobTitle"] in STAFF_TITLES_IT else "staff") if d else self.kind_for_email(email) if email else "unknown"
            p = {"person_id": i["pid"], "display_name": i["display"], "emails": [email] if email else [], "teams_ids": sorted(i["teams_ids"]), "kind": kind, "org": self.org_for_domain(domain_of(email)) if email else None, "exported": bool(d and d.get("exported"))}
            if d:
                p.update(job_title=d["jobTitle"], export_folder=d.get("export_folder"))
                p["teams_ids"] = sorted(set(p["teams_ids"]) | {d["id"]})
            self.people[i["pid"]] = p
            if email:
                self.by_email[email] = i["pid"]
            for t in p["teams_ids"]:
                self.by_teams_id[t] = i["pid"]
        for n, target in teams_attach.items():
            self.by_teams_name[n] = target["pid"]
        self.reindex()

    def reindex(self):
        self.by_name = defaultdict(list)
        for pid, p in self.people.items():
            self.by_name[norm(p["display_name"])].append(pid)

    def org_for_domain(self, domain: str) -> str | None:
        if domain in VENDOR_DOMAINS:
            key = domain.split(".")[0]
            self.orgs.setdefault(f"o_{key}", {"org_id": f"o_{key}", "name": key.title(), "kind": "vendor", "domains": [domain]})
            return f"o_{key}"
        m = re.match(r"([a-z]+)law\.example$", domain)
        if m:
            key = m.group(1)
            self.orgs.setdefault(f"o_{key}", {"org_id": f"o_{key}", "name": key.title(), "kind": "client", "domains": [domain]})
            return f"o_{key}"
        if domain == WORK_DOMAIN:
            return "o_harbourline"
        return None

    @staticmethod
    def kind_for_email(email: str) -> str:
        dom = domain_of(email)
        if dom in VENDOR_DOMAINS:
            return "vendor"
        if re.match(r"[a-z]+law\.example$", dom):
            return "client"
        return "unknown"

    def email(self, email: str) -> str:
        return self.by_email[email.lower()]

    def teams(self, name: str, teams_id: str | None = None) -> str:
        if teams_id and teams_id in self.by_teams_id:
            return self.by_teams_id[teams_id]
        return self.by_teams_name[norm(name)]

    def merge(self, src: str, dst: str, reason: str) -> None:
        s, d = self.people.pop(src), self.people[dst]
        d["emails"] = sorted(set(d["emails"]) | set(s["emails"]))
        d["teams_ids"] = sorted(set(d["teams_ids"]) | set(s["teams_ids"]))
        d.setdefault("merged_ids", []).append(src)
        d["merge_reason"] = reason
        for e in s["emails"]:
            self.by_email[e] = dst
        for t in s["teams_ids"]:
            self.by_teams_id[t] = dst
        for n, pid in list(self.by_teams_name.items()):
            if pid == src:
                self.by_teams_name[n] = dst
        self.reindex()

    def first_name(self, pid: str) -> str:
        return norm(self.people[pid]["display_name"]).split(" ")[0]

    def name(self, pid: str | None) -> str | None:
        return self.people[pid]["display_name"] if pid in self.people else None

    def eligible(self) -> list[str]:
        return sorted(pid for pid, p in self.people.items() if p["kind"] not in NOT_SUBJECT)

    def is_exported_staff(self, pid: str | None) -> bool:
        return bool(pid) and pid in self.people and self.people[pid]["kind"] == "staff" and self.people[pid].get("exported", False)


# --------------------------------------------------------------------------- step 1: ingest


def load_directory() -> list[dict]:
    return json.loads((DATA / "_shared/directory.json").read_text(encoding="utf-8"))["value"]


def iter_raw():
    """Yield (source, folder, path, line, record) over every raw file, deterministic order."""
    folders = sorted(d["export_folder"] for d in load_directory() if d.get("exported"))
    for folder in folders:
        for source, (relpath, _) in PERSON_SOURCES.items():
            path = DATA / folder / relpath
            if path.exists():
                for line, r in read_jsonl(path):
                    yield source, folder, path, line, r
    for line, r in read_jsonl(DATA / CHANNEL_FILE):
        yield "teams_channel", "_shared", DATA / CHANNEL_FILE, line, r


def collect_headers() -> tuple[Counter, dict]:
    pairs: Counter = Counter()
    teams: dict[str, set] = defaultdict(set)
    for source, _, _, _, r in iter_raw():
        if source == "mail":
            for x in [r["from"], r["sender"], *r.get("toRecipients", []), *r.get("ccRecipients", []), *r.get("bccRecipients", [])]:
                pairs[addr(x)] += 1
        elif source == "calendar":
            for x in [r["organizer"], *r.get("attendees", [])]:
                pairs[addr(x)] += 1
        elif source in ("teams_chat", "teams_channel"):
            u = r["from"]["user"]
            teams[u["displayName"]].add(u.get("id")) if u.get("id") else teams[u["displayName"]]
            for m in r.get("_members", []):
                teams[m]
    return pairs, {k: {t for t in v if t} for k, v in teams.items()}


def new_event(eid, source, folder, t, actor, recipients, title, text, thread_key, raw_ref, meta) -> dict:
    return {
        "event_id": eid, "source": source, "mailbox": folder, "seen_in": [folder],
        "time_utc": to_iso_z(t), "time_local": to_local(t), "actor_id": actor, "recipients": recipients,
        "title": title, "text": text, "category": None, "noise_reason": None, "activity": None, "process": None,
        "subject_person_id": None, "resolution": None, "fields": {}, "thread_key": thread_key,
        "raw_ref": raw_ref, "meta": meta,
    }


def sessionize(frames: list[tuple], folder: str, owner: str) -> list[dict]:
    """Merge frames with the same mailbox + window title when the gap to the previous frame of that title is
    <= 10 min, even if other windows' frames are in between. Idle frames (> 300 s) never merge with active ones."""
    out = []
    open_by_key: dict = {}
    for path, line, r, t in frames:
        idle = (r.get("idle_seconds") or 0) > IDLE_LIMIT
        key = (r.get("window_title"), idle)
        cur = open_by_key.get(key)
        if cur and t - cur["last"] <= SESSION_GAP:  # other windows' frames may sit in between
            cur["frames"].append((path, line, r, t))
            cur["last"] = t
            continue
        cur = {"key": key, "frames": [(path, line, r, t)], "last": t}
        open_by_key[key] = cur
        out.append(cur)
    events = []
    for s in out:
        path, line, r, t0 = s["frames"][0]
        t1 = s["frames"][-1][3]
        urls = sorted({f[2].get("url") for f in s["frames"] if f[2].get("url")})
        apps = Counter(f[2].get("app") for f in s["frames"])
        meta = {
            "url": r.get("url"), "apps": dict(sorted(apps.items())),
            "idle_seconds": max(f[2].get("idle_seconds") or 0 for f in s["frames"]),
            "all_idle": s["key"][1],
        }
        if len(s["frames"]) > 1:  # all frames are in the same file as raw_ref
            meta["raw_lines"] = [f[1] for f in s["frames"]]
        if len(urls) > 1:
            meta["urls"] = urls
        ev = new_event(f"screen:{folder}:{line}", "screen", folder, t0, owner, [], r.get("window_title"), "", None, {"file": rel(path), "line": line}, meta)
        ev["session"] = {"start_local": to_local(t0), "end_local": to_local(t1), "start_utc": to_iso_z(t0), "end_utc": to_iso_z(t1), "frame_count": len(s["frames"]), "minutes": round((t1 - t0).total_seconds() / 60, 1)}
        events.append(ev)
    return events


def step1_ingest() -> dict:
    directory = load_directory()
    pairs, teams_names = collect_headers()
    reg = Registry(directory, pairs, teams_names)
    folder_owner = {d["export_folder"]: reg.email(d["mail"]) for d in directory if d.get("exported")}

    events: dict[str, dict] = {}
    raw_counts: Counter = Counter()
    frames: dict[str, list] = defaultdict(list)
    for source, folder, path, line, r in iter_raw():
        raw_counts[source] += 1
        t, _, _ = record_time(source, r)
        if source == "screen":
            frames[folder].append((path, line, r, t))
            continue
        meta: dict = {}
        recipients: list[str] = []
        thread_key = None
        title = None
        if source == "mail":
            native = r["internetMessageId"].strip("<>")
            faddr = addr(r["from"])[1]
            actor = reg.email(faddr)
            to = [reg.email(addr(x)[1]) for x in r.get("toRecipients", [])]
            cc = [reg.email(addr(x)[1]) for x in r.get("ccRecipients", []) + r.get("bccRecipients", [])]
            recipients = to + [c for c in cc if c not in to]
            title = r.get("subject")
            body = r.get("body") or {}
            text = body.get("content", "") if body.get("contentType") == "text" else strip_html(body.get("content", ""))
            text = text.replace("\r\n", "\n").strip()
            thread_key = f'mail:{r["conversationId"]}'
            meta = {"from_address": faddr, "to_ids": to}
        elif source == "calendar":
            native = r["iCalUId"]
            oaddr = addr(r["organizer"])[1]
            actor = reg.email(oaddr)
            recipients = [reg.email(addr(a)[1]) for a in r.get("attendees", [])]
            title = r.get("subject")
            text = strip_html((r.get("body") or {}).get("content", ""))
            end = parse_calendar(r["end"])
            meta = {"from_address": oaddr, "is_all_day": r.get("isAllDay", False), "end_local": to_local(end), "to_ids": recipients}
        elif source == "teams_chat":
            native = f'{r["chatId"]}:{r["id"]}'
            u = r["from"]["user"]
            actor = reg.teams(u["displayName"], u.get("id"))
            members = [reg.teams(n) for n in r.get("_members", [])]
            recipients = [m for m in members if m != actor]
            text = strip_html(r["body"]["content"])
            thread_key = f'chat:{r["chatId"]}'
            meta = {"chat_members": members}
        else:  # teams_channel
            native = r["id"]
            u = r["from"]["user"]
            actor = reg.teams(u["displayName"], u.get("id"))
            text = strip_html(r["body"]["content"])
            thread_key = f'channel:{r.get("replyToId") or r["id"]}'
            meta = {"channel": r["channelIdentity"].get("_channelName"), "reply_to": r.get("replyToId")}

        eid = f"{source}:{native}"
        if eid in events:  # duplicate copy in another mailbox
            if folder not in events[eid]["seen_in"]:
                events[eid]["seen_in"].append(folder)
            continue
        events[eid] = new_event(eid, source, folder, t, actor, recipients, title, text, thread_key, {"file": rel(path), "line": line}, meta)

    screen_frames = sum(len(v) for v in frames.values())
    for folder in sorted(frames):
        for ev in sessionize(sorted(frames[folder], key=lambda f: (f[3], f[1])), folder, folder_owner[folder]):
            events[ev["event_id"]] = ev

    ordered = sorted(events.values(), key=lambda e: (e["time_utc"], e["event_id"]))
    write_events(OUT / "1_events.jsonl", [e for e in ordered if e["source"] != "screen"])
    return {"events": ordered, "registry": reg, "raw_counts": dict(raw_counts), "dedup_counts": dict(Counter(e["source"] for e in ordered)), "screen_frames": screen_frames}


def write_events(path: Path, events: list[dict]) -> None:
    """Write events with text truncated to TEXT_LIMIT chars (full record lives in data/, see raw_ref).
    Keys whose value is null / empty are omitted (absent = null)."""
    OUT.mkdir(exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for ev in events:
            out = {k: v for k, v in ev.items() if v not in (None, "", [], {})}
            if len(ev["text"] or "") > TEXT_LIMIT:
                out["text"] = ev["text"][:TEXT_LIMIT] + "…"
                out["text_truncated"] = True
            fh.write(json.dumps(out, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n")


# --------------------------------------------------------------------------- step 2: clean (classify + resolve)

HIGH_METHODS = {"email", "full_name", "thread", "sender", "chat_member"}
METHOD_RANK = {"email": 0, "sender": 0, "chat_member": 0, "thread": 0, "full_name": 1, "chat_pair": 2, "initial": 2, "first_name_unique": 3, "fuzzy": 4, "context": 5, "needs_context": 6, "ambiguous": 8, "unresolved": 9, "staff_name": 9}
CONFIDENCE = {"email": "high", "sender": "high", "chat_member": "high", "thread": "high", "full_name": "high", "chat_pair": "medium", "initial": "medium", "first_name_unique": "medium", "fuzzy": "medium", "context": "medium"}
CONTEXT_WINDOW = timedelta(days=30)
LAPTOP_TRACK = {"laptop_ordered", "laptop_shipped", "laptop_confirmed_by_starter"}
OOS_WITH_SUBJECT = {"oos_channel_replacement"}


def rule_matches(rule: R.Rule, ev: dict, reg: Registry) -> dict | None:
    if ev["source"] not in rule.sources:
        return None
    meta = ev["meta"]
    if rule.reply is not None and ev["source"] == "teams_channel":
        if bool(meta.get("reply_to")) != rule.reply:
            return None
    if rule.direction:
        if (rule.direction == "out") != reg.is_exported_staff(ev["actor_id"]):
            return None
    if rule.sender_domain and not re.search(rule.sender_domain, meta.get("from_address") or "", re.I):
        return None
    groups: dict = {}
    for key, value in (("subject", ev["title"]), ("text", ev["text"]), ("title", ev["title"]), ("url", meta.get("url"))):
        rx = rule.rx(key)
        if rx is None:
            continue
        m = rx.search(value or "")
        if not m:
            return None
        for k, v in m.groupdict().items():
            if v is not None:
                groups.setdefault(k, v.strip())
    return groups


IDLE_RULE = R.Rule("noise_screen_idle", "noise", ("screen",), reason="idle > 300s")


def classify(ev: dict, reg: Registry) -> tuple[R.Rule | None, dict]:
    if ev["source"] == "screen" and ev["meta"].get("all_idle"):
        return IDLE_RULE, {}
    if ev["source"] == "teams_channel" and ev["meta"].get("channel") == "General":
        return next(r for r in R.RULES if r.id == "noise_channel_general"), {}
    for rule in R.RULES:
        if rule.id == "noise_channel_general":
            continue
        g = rule_matches(rule, ev, reg)
        if g is not None:
            return rule, g
    return None, {}


def build_fields(groups: dict, ev: dict, reg: Registry) -> dict:
    f: dict = {}
    warnings = []
    if "dates" in groups:
        f["dates"] = parse_range(groups["dates"])
        warnings += f["dates"].pop("warnings", [])
        if "dates2" in groups and groups["dates2"] != groups["dates"]:
            warnings.append(f'dates differ: subject {groups["dates"]!r} vs body {groups["dates2"]!r}')
    if "type" in groups:
        f["leave_type"] = {"annual leave": "annual", "sick leave": "sick", "a personal day": "personal"}[groups["type"].lower()]
    for k in ("last_day", "first_day", "needed_by"):
        if k in groups:
            f[k], w = parse_day(groups[k])
            if w:
                warnings.append(w)
    for k in ("vendor", "model", "consignment", "order_no", "tracking"):
        if k in groups:
            f[k] = groups[k]
    if "amount" in groups:
        f["amount_aud"] = int(groups["amount"])
    if "client" in groups:
        f["client_raw"] = groups["client"]
    if "name" in groups:
        f["name_raw"] = groups["name"]
    if "sname" in groups:
        f["name_raw_subject"] = groups["sname"]
    org = None
    if "client" in groups:
        key = norm(groups["client"]).split(" ")[0]
        org = f"o_{key}" if f"o_{key}" in reg.orgs else None
        if org and len(groups["client"]) > len(reg.orgs[org]["name"]):
            reg.orgs[org]["name"] = groups["client"]  # learn the full firm name
    if not org:
        for pid in [ev["actor_id"], *ev["recipients"]]:
            p = reg.people.get(pid)
            if p and p["kind"] == "client" and p["org"]:
                org = p["org"]
                break
    if org:
        f["client"] = org
    owner = ev["actor_id"] if reg.is_exported_staff(ev["actor_id"]) else next((r for r in ev["recipients"] if reg.is_exported_staff(r)), None)
    if not owner and ev["source"] in ("screen", "mail"):
        owner = reg.email(next(p["emails"][0] for p in reg.people.values() if p.get("export_folder") == ev["mailbox"])) if ev["mailbox"] != "_shared" else None
    if owner:
        f["owner_staff_id"] = owner
    if ev["activity"] == "day_one_reply":
        f["reports_issue"] = bool(R.DAY_ONE_ISSUE.search(ev["text"]))
    if warnings:
        f["warnings"] = warnings
    return f


# ---- identity merge (personal + work address) ------------------------------------------


def merge_identities(events: list[dict], reg: Registry) -> dict:
    """Merge a personal and a work address with the same full name ONLY when both appear in the same
    onboarding case: personal address first, same client on both sides. Otherwise keep them apart and
    mark both possible_same_person."""
    involved: dict[str, list[dict]] = defaultdict(list)  # pid -> events where pid is actor or direct recipient
    for ev in events:
        for pid in {ev["actor_id"], *ev["meta"].get("to_ids", []), *([] if ev["source"] != "teams_chat" else [ev["actor_id"]])}:
            if pid:
                involved[pid].append(ev)
    decisions = []
    mapping: dict[str, str] = {}
    for n, pids in sorted(reg.by_name.items()):
        if len(pids) < 2:
            continue
        work = [p for p in pids if any(domain_of(e) == WORK_DOMAIN for e in reg.people[p]["emails"]) and reg.people[p]["kind"] not in NOT_SUBJECT]
        personal = [p for p in pids if any(domain_of(e) in PERSONAL_DOMAINS for e in reg.people[p]["emails"])]
        if len(work) != 1 or not personal:
            if len(pids) > 1:
                decisions.append({"name": reg.name(pids[0]), "ids": sorted(pids), "merged": False, "reason": "same full name, no work+personal pair to test"})
            continue
        w = work[0]
        for p in sorted(personal):
            pe = [e for e in involved[p]]
            we = [e for e in involved[w]]
            p_on = [e for e in pe if e["process"] == "onboarding"]
            w_on = [e for e in we if e["process"] == "onboarding"]
            # "personal address first" is judged inside the onboarding case
            p_first = min((e["time_utc"] for e in p_on), default=None)
            w_first = min((e["time_utc"] for e in w_on), default=None)
            w_before = sorted((e for e in we if e["process"] != "onboarding" and p_first and e["time_utc"] < p_first), key=lambda e: e["time_utc"])
            p_clients = {e["fields"].get("client") for e in p_on if e["fields"].get("client")}
            w_clients = {e["fields"].get("client") for e in w_on if e["fields"].get("client")}
            why = []
            if not p_on:
                why.append("personal address has no onboarding events")
            if not w_on:
                why.append("work address has no onboarding events")
            if p_first and w_first and p_first > w_first:
                first_w = min(w_on, key=lambda e: e["time_utc"])
                why.append(f"work address used first in onboarding ({first_w['time_local'][:10]}: {first_w['title'] or first_w['text'][:40]!r})")
            if p_clients and w_clients and not (p_clients & w_clients):
                why.append(f"different clients ({sorted(p_clients)} vs {sorted(w_clients)})")
            if not p_clients or not w_clients:
                why.append("client not known on both sides")
            if why:
                decisions.append({"name": reg.name(w), "ids": [w, p], "merged": False, "reason": "; ".join(why)})
                for a, b in ((w, p), (p, w)):
                    reg.people[a].setdefault("possible_same_person", []).append({"person_id": b, "reason": "; ".join(why)})
            else:
                client = reg.orgs[sorted(p_clients & w_clients)[0]]["name"]
                reason = f"personal address used first in onboarding ({p_first[:10]}), work address from {w_first[:10]}; same client {client}"
                if w_before:
                    reason += f"; NOTE work address already sent {len(w_before)} non-onboarding mail(s) before onboarding (first: {w_before[0]['time_local'][:10]} {w_before[0]['title']!r})"
                decisions.append({"name": reg.name(w), "ids": [w, p], "merged": True, "reason": reason})
                reg.merge(p, w, reason)
                mapping[p] = w
    if mapping:
        for ev in events:
            ev["actor_id"] = mapping.get(ev["actor_id"], ev["actor_id"])
            ev["recipients"] = list(dict.fromkeys(mapping.get(r, r) for r in ev["recipients"]))
            for k in ("to_ids", "chat_members"):
                if k in ev["meta"]:
                    ev["meta"][k] = list(dict.fromkeys(mapping.get(r, r) for r in ev["meta"][k]))
            if "owner_staff_id" in ev["fields"]:
                ev["fields"]["owner_staff_id"] = mapping.get(ev["fields"]["owner_staff_id"], ev["fields"]["owner_staff_id"])
    return {"decisions": decisions, "mapping": mapping}


# ---- name resolution -----------------------------------------------------------------------

PROCESS_NOUN = {"leave": "leave", "offboarding": "offboarding", "onboarding": "onboarding"}


class Resolver:
    def __init__(self, reg: Registry):
        self.reg = reg
        self.pool = reg.eligible()
        self.staff_names = {norm(p["display_name"]) for p in reg.people.values() if p["kind"] in ("staff", "it")}
        self.anchors: dict[str, list[dict]] = defaultdict(list)

    def by_name(self, raw: str) -> dict:
        n = norm(raw).rstrip(".")
        toks = n.split(" ")
        names = {pid: norm(self.reg.people[pid]["display_name"]) for pid in self.pool}
        nm = self.reg.name
        exact = sorted(pid for pid, full in names.items() if full == n)
        if len(exact) == 1:
            return {"method": "full_name", "person": exact[0], "candidates": exact, "reason": f"Full name {raw!r} written in the text"}
        if exact:
            return {"method": "needs_context", "person": None, "candidates": exact, "reason": f"{len(exact)} identities named {raw!r} (not merged)"}
        if n in self.staff_names:
            return {"method": "staff_name", "person": None, "candidates": [], "reason": f"{raw!r} is a staff member; staff are never case subjects"}
        first = toks[0]
        if len(toks) == 2 and len(toks[1].rstrip(".")) == 1:  # "Otto V."
            ini = toks[1][0]
            c = sorted(pid for pid, full in names.items() if full.split(" ")[0] == first and full.split(" ")[-1].startswith(ini))
            if len(c) == 1:
                return {"method": "initial", "person": c[0], "candidates": c, "reason": f"Only {nm(c[0])} matches {raw!r} (first name + initial)"}
            if c:
                return {"method": "needs_context", "person": None, "candidates": c}
            toks = [first]
        if len(toks) == 1:
            c = sorted(pid for pid, full in names.items() if full.split(" ")[0] == first)
            if len(c) == 1:
                return {"method": "first_name_unique", "person": c[0], "candidates": c, "reason": f"Only non-staff person named {raw.title()!r} is {nm(c[0])}"}
            if c:
                return {"method": "needs_context", "person": None, "candidates": c}
            dist = {pid: osa_distance(full.split(" ")[0], first) for pid, full in names.items()}
            c = closest(dist) if len(first) >= 4 else []
            if len(c) == 1:
                return {"method": "fuzzy", "person": c[0], "candidates": c, "typo": True, "reason": f"{raw!r} is {dist[c[0]]} edit(s) from {nm(c[0]).split(' ')[0]!r}; no closer name"}
            if c:
                return {"method": "needs_context", "person": None, "candidates": c, "typo": True}
            return {"method": "unresolved", "person": None, "candidates": [], "reason": f"No person matches {raw!r}"}
        dist = {pid: osa_distance(full, n) for pid, full in names.items()}
        c = closest(dist)
        if len(c) == 1:
            return {"method": "fuzzy", "person": c[0], "candidates": c, "typo": True, "reason": f"{raw!r} is {dist[c[0]]} edit(s) from {nm(c[0])!r}; no closer name"}
        if c:
            return {"method": "needs_context", "person": None, "candidates": c, "typo": True}
        return {"method": "unresolved", "person": None, "candidates": [], "reason": f"No person matches {raw!r}"}

    def by_context(self, cands: list[str], ev: dict, raw: str) -> dict:
        """Pick from candidates with an open case of the same process near that date."""
        t = ts(ev["time_utc"])
        f = ev["fields"]
        nm = self.reg.name
        orgs = self.reg.orgs

        def anchors_for(pid):
            return [(a, ts(a["time_utc"])) for a in self.anchors.get(pid, []) if a["event_id"] != ev["event_id"] and a["process"] == ev["process"] and abs(ts(a["time_utc"]) - t) <= CONTEXT_WINDOW]

        def date_match(a):
            af = a["fields"]
            if f.get("dates") and af.get("dates"):
                return (af["dates"]["start"], af["dates"]["end"]) == (f["dates"]["start"], f["dates"]["end"])
            for k in ("last_day", "first_day"):
                if f.get(k) and af.get(k):
                    return af[k] == f[k]
            return False

        def date_desc():
            if f.get("dates"):
                return f'dates {f["dates"]["raw"]} match'
            if f.get("last_day"):
                return f"last day {nice_day(f['last_day'])} matches"
            if f.get("first_day"):
                return f"first day {nice_day(f['first_day'])} matches"
            return "dates match"

        filters = [
            ("before", lambda a, at: at <= t, lambda pid: "case was already open"),
            ("dates", lambda a, at: date_match(a), lambda pid: date_desc()),
            ("client", lambda a, at: bool(f.get("client")) and a["fields"].get("client") == f.get("client"), lambda pid: f"client {orgs[f['client']]['name']} matches"),
            ("owner", lambda a, at: bool(f.get("owner_staff_id")) and a["fields"].get("owner_staff_id") == f.get("owner_staff_id"), lambda pid: f"case is handled by the same staff member ({nm(f['owner_staff_id'])})"),
        ]
        proc = PROCESS_NOUN[ev["process"]]
        art = "an" if proc[0] in "aeiou" else "a"
        pool = {pid: anchors_for(pid) for pid in cands}
        pool = {pid: a for pid, a in pool.items() if a}
        applied = ["process_near"]
        if not pool:
            return {"method": "ambiguous", "person": None, "candidates": sorted(cands), "filters": applied, "reason": f"{len(cands)} candidates for {raw!r}; none has a {proc} case within 30 days"}
        decided_by = "process_near" if len(pool) == 1 else None
        for key, pred, _ in filters:
            if len(pool) == 1:
                break
            narrowed = {pid: [x for x in a if pred(*x)] for pid, a in pool.items()}
            narrowed = {pid: a for pid, a in narrowed.items() if a}
            if narrowed:
                n_before = len(pool)
                pool = narrowed
                applied.append(key)
                if len(pool) == 1:
                    decided_by = (key, n_before)
        if len(pool) != 1:
            return {"method": "ambiguous", "person": None, "candidates": sorted(pool), "filters": applied, "reason": f"{len(pool)} candidates for {raw!r} still fit after: {', '.join(applied)}"}
        pid = next(iter(pool))
        label = self.reg.first_name(pid).title()
        if decided_by == "process_near":
            reason = f"Only {label} with {art} {proc} case near this date"
            extra = [desc(pid) for key, pred, desc in filters[1:3] if any(pred(*x) for x in pool[pid])]
            if extra:
                reason += "; " + "; ".join(extra)
        else:
            key, n_before = decided_by
            desc = next(d for k, _, d in filters if k == key)
            reason = f"{n_before} {label}s have {art} {proc} case near this date; only {nm(pid)}'s {desc(pid)}"
        return {"method": "context", "person": pid, "candidates": sorted(cands), "filters": applied, "decided_by": decided_by if isinstance(decided_by, str) else decided_by[0], "reason": reason, "evidence_event_ids": sorted(a["event_id"] for a, _ in pool[pid])[:5]}


def finish_resolution(res: dict, raw: str | None) -> dict:
    out = {"method": res["method"], "confidence": CONFIDENCE.get(res["method"]), "candidates": res.get("candidates", [])}
    if raw is not None:
        out["raw_name"] = raw
    for k in ("typo", "filters", "decided_by", "reason", "evidence_event_ids"):
        if k in res:
            out[k] = res[k]
    return out


def step2_clean(ingest: dict) -> dict:
    events, reg = ingest["events"], ingest["registry"]
    rule_by_event: dict[str, R.Rule] = {}

    # ---- 2a classify
    for ev in events:
        rule, groups = classify(ev, reg)
        if rule is None:
            ev["category"], ev["noise_reason"] = "context", "no rule matched"
            continue
        rule_by_event[ev["event_id"]] = rule
        ev["category"] = rule.category
        ev["fields"]["rule_id"] = rule.id
        if rule.category in ("noise", "out_of_scope", "context"):
            ev["noise_reason"] = rule.reason
        if rule.id in OOS_WITH_SUBJECT:  # out of scope, but who it is about matters for cross-process checks
            ev["fields"].update(build_fields(groups, ev, reg))
        if rule.category == "process":
            ev["activity"], ev["process"] = rule.activity, rule.process
            ev["fields"].update(build_fields(groups, ev, reg))
            if rule.likely:
                ev["fields"]["likely"] = True
            if ev["fields"].get("order_no"):
                ev["thread_key"] = f'order:{ev["fields"]["order_no"]}'  # confirmation + shipping mails share an order number

    roots = {ev["event_id"].split(":", 1)[1]: ev for ev in events if ev["source"] == "teams_channel" and not ev["meta"].get("reply_to")}
    for ev in events:
        if ev["source"] == "teams_channel" and ev["meta"].get("reply_to"):
            root = roots.get(ev["meta"]["reply_to"])
            if root and root["category"] == "out_of_scope":
                ev.update(category="out_of_scope", noise_reason=root["noise_reason"], activity=None, process=None)
                ev["fields"] = {"rule_id": "inherit_thread_root"}
                rule_by_event.pop(ev["event_id"], None)
            elif root and root["category"] == "process":
                for k in ("client", "needed_by", "owner_staff_id"):
                    if k in root["fields"] and k not in ev["fields"]:
                        ev["fields"][k] = root["fields"][k]

    # ---- 2b identity merge, then resolution
    merges = merge_identities(events, reg)
    res = Resolver(reg)
    proc = [ev for ev in events if ev["category"] == "process"]
    for ev in events:
        if ev["fields"].get("rule_id") in OOS_WITH_SUBJECT and ev["fields"].get("name_raw"):
            r = res.by_name(ev["fields"]["name_raw"])
            ev["resolution"] = finish_resolution(r if r["method"] != "needs_context" else {**r, "method": "ambiguous", "reason": f"{len(r['candidates'])} candidates; out of scope, so no case context used"}, ev["fields"]["name_raw"])
            ev["subject_person_id"] = r.get("person")

    def direct(ev, rule):
        meta = ev["meta"]
        for how in rule.who:
            if how == "sender" and ev["actor_id"] in res.pool:
                m = "email" if ev["source"] == "mail" else "sender"
                return {"method": m, "person": ev["actor_id"], "candidates": [ev["actor_id"]], "reason": "Sent by the person" + (" (their address)" if m == "email" else " (Teams account)")}, None
            if how == "recipient" and "to_ids" in meta:
                for pid in meta["to_ids"]:
                    if pid in res.pool:
                        who = "attendee" if ev["source"] == "calendar" else "recipient"
                        return {"method": "email", "person": pid, "candidates": [pid], "reason": f"{who.title()} address {reg.people[pid]['emails'][0] if reg.people[pid]['emails'] else ''}".strip()}, None
            if how == "chat_other":
                others = [p for p in ev["recipients"] if p in res.pool]
                if len(others) == 1:
                    return {"method": "chat_member", "person": others[0], "candidates": others, "reason": "Other member of the 1:1 chat"}, None
            if how == "text":
                raws = [ev["fields"].get(k) for k in ("name_raw_subject", "name_raw") if ev["fields"].get(k)]
                best = None
                for raw in raws:
                    r = res.by_name(raw)
                    if best is None or METHOD_RANK.get(r["method"], 7) < METHOD_RANK.get(best[0]["method"], 7):
                        best = (r, raw)
                if best:
                    if len(raws) == 2 and raws[0] != raws[1]:
                        best[0]["alt_name"] = [x for x in raws if x != best[1]][0]
                    return best
        return None, None

    first_pass: dict[str, tuple] = {}
    for ev in proc:
        r, raw = direct(ev, rule_by_event[ev["event_id"]])
        first_pass[ev["event_id"]] = (r, raw)
        if r and r.get("person") and r["method"] in HIGH_METHODS:
            res.anchors[r["person"]].append(ev)

    thread_subject: dict[str, str] = {}
    open_it: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for ev in proc:
        rule = rule_by_event[ev["event_id"]]
        final, raw = None, None
        for how in rule.who:
            if how == "none":
                final = {"method": "unresolved", "person": None, "candidates": [], "reason": "No name in the record; linked by time in step 3"}
                break
            if how == "thread" and ev["thread_key"] in thread_subject and ev["source"] in ("mail", "teams_channel"):
                pid = thread_subject[ev["thread_key"]]
                kind = "order number" if ev["thread_key"].startswith("order:") else "thread"
                final = {"method": "thread", "person": pid, "candidates": [pid], "reason": f"Same {kind} as an earlier message about {reg.name(pid)}"}
                break
            if how == "chat_pair":
                stack = open_it.get(ev["thread_key"], [])
                raw_name = ev["fields"].get("name_raw")
                if raw_name:
                    hit = [x for x in stack if reg.first_name(x[0]) == norm(raw_name).split(" ")[0]]
                    if hit:
                        final = {"method": "thread", "person": hit[-1][0], "candidates": [hit[-1][0]], "reason": f"Matches the open IT request for {reg.name(hit[-1][0])} in the same chat", "linked_event_id": hit[-1][1]}
                        raw = raw_name
                        stack.remove(hit[-1])
                        break
                    continue
                if stack:
                    pid, linked = stack.pop()
                    final = {"method": "chat_pair", "person": pid, "candidates": [pid], "reason": f"No name; the latest open IT request in this chat was for {reg.name(pid)}", "linked_event_id": linked}
                    break
                final = {"method": "unresolved", "person": None, "candidates": [], "reason": "No name and no open IT request in this chat"}
                break
            if how in ("sender", "recipient", "chat_other", "text"):
                r, rr = first_pass[ev["event_id"]]
                if r is None:
                    continue
                if r["method"] == "needs_context":
                    r = {**res.by_context(r["candidates"], ev, rr), **({"typo": True} if r.get("typo") else {})}
                final, raw = r, rr
                if final.get("person"):
                    break
        if final is None:
            final = {"method": "unresolved", "person": None, "candidates": [], "reason": "No usable name"}
        if "linked_event_id" in final:
            ev["fields"]["linked_event_id"] = final.pop("linked_event_id")
        if final.get("alt_name"):
            ev["fields"]["name_variant"] = final["alt_name"]
        ev["resolution"] = finish_resolution(final, raw)
        ev["subject_person_id"] = final.get("person")
        if ev["subject_person_id"] and ev["thread_key"] and ev["thread_key"] not in thread_subject and ev["source"] in ("mail", "teams_channel"):
            thread_subject[ev["thread_key"]] = ev["subject_person_id"]
        if ev["activity"] == "it_requested" and ev["subject_person_id"]:
            open_it[ev["thread_key"]].append((ev["subject_person_id"], ev["event_id"]))

    # ---- 2c laptop track: new starters only, replacements are out of scope
    starters = {ev["subject_person_id"] for ev in proc if ev["process"] == "onboarding" and ev["activity"] not in LAPTOP_TRACK and ev["subject_person_id"]}
    for ev in proc:
        if ev["activity"] in LAPTOP_TRACK and ev["subject_person_id"] not in starters:
            ev.update(category="out_of_scope", noise_reason="laptop replacement (seen, not modelled)", process=None)
            ev["fields"]["was_activity"] = ev.pop("activity")
            ev["activity"] = None

    # ---- 2d screen sessions without a name stay context until step 3 links them by time
    for ev in events:
        if ev["source"] == "screen" and ev["category"] == "process" and not ev["subject_person_id"]:
            ev["category"] = "context"
            ev["noise_reason"] = "screen session with no name; becomes a case step only if step 3 links it by time"

    # ---- 2e finalise person kinds
    proc = [ev for ev in events if ev["category"] == "process"]
    onboarding_subjects = {ev["subject_person_id"] for ev in proc if ev["process"] == "onboarding" and ev["subject_person_id"]}
    recruit_people = set()
    for ev in events:
        if ev["category"] == "out_of_scope" and "recruitment" in (ev["noise_reason"] or ""):
            recruit_people.update([ev["actor_id"], *ev["recipients"]])
    for pid, p in reg.people.items():
        if p["kind"] != "unknown":
            continue
        has_work = any(domain_of(e) == WORK_DOMAIN for e in p["emails"]) or bool(p["teams_ids"])
        if pid in onboarding_subjects:
            p["kind"] = "new_starter"
        elif has_work:
            p["kind"] = "worker"
        elif pid in recruit_people:
            p["kind"] = "candidate"

    write_clean_outputs(events)
    write_json(OUT / "2_people.json", {
        "step": "2_people",
        "coverage": "Data from 6 of 12 staff.",
        "identity_merges": merges["decisions"],
        "people": [reg.people[k] for k in sorted(reg.people)],
        "orgs": [reg.orgs[k] for k in sorted(reg.orgs)],
    })
    return {"events": events, "registry": reg, "merges": merges, "rules": rule_by_event}


def write_clean_outputs(events: list[dict]) -> None:
    """2_events_clean.jsonl: every non-screen event + process-related screen sessions (those with an activity).
    Context / noise / out-of-scope screen sessions -> compact summary in 2_screen_summary.json."""
    keep, summary = [], {}
    for ev in events:
        if ev["source"] != "screen" or ev["activity"]:
            keep.append(ev)
            continue
        k = (ev["mailbox"], ev["title"] or "", ev["time_local"][:10], ev["category"], ev["noise_reason"] or "")
        row = summary.setdefault(k, {"mailbox": k[0], "title": k[1], "day": k[2], "category": k[3], "reason": k[4], "sessions": 0, "frames": 0, "minutes": 0.0})
        row["sessions"] += 1
        row["frames"] += ev["session"]["frame_count"]
        row["minutes"] = round(row["minutes"] + ev["session"]["minutes"], 1)
    write_events(OUT / "2_events_clean.jsonl", keep)
    rows = [summary[k] for k in sorted(summary)]
    write_json(OUT / "2_screen_summary.json", compact=True, obj={
        "step": "2_screen_summary",
        "note": "Screen sessions that are context, noise or out of scope, summarised per mailbox, title and day. Full frames: data/<mailbox>/screens/screen_log.jsonl",
        "totals": {c: {"sessions": sum(r["sessions"] for r in rows if r["category"] == c), "frames": sum(r["frames"] for r in rows if r["category"] == c)} for c in sorted({r["category"] for r in rows})},
        "reason_by_title": {r["title"]: r["reason"] for r in rows},
        "rows": [[r["mailbox"], r["day"], r["category"], r["title"], r["sessions"], r["frames"], r["minutes"]] for r in rows],
        "columns": ["mailbox", "day", "category", "title", "sessions", "frames", "minutes"],
    })


# --------------------------------------------------------------------------- step 3: cases

WINDOW_START = datetime(2026, 3, 2, tzinfo=TZ_LOCAL)
WINDOW_END = datetime(2026, 3, 29, 23, 59, 59, tzinfo=TZ_LOCAL)
TRIGGERS = {"leave": {"leave_requested"}, "offboarding": {"resignation_received", "client_ended_engagement"}, "onboarding": {"contract_sent"}}
# Expected order used ONLY to report steps out of order in Phase 2 (Phase 3 discovers the real order).
EXPECTED_TRACKS = {
    "leave": [["leave_requested", "peoplehub_opened", "client_check_sent", "client_approved", "worker_approved"],
              ["leave_requested", "client_check_sent", "client_declined", "worker_asked_other_dates"],
              ["leave_requested", "client_notified_sick", "worker_approved"]],
    "offboarding": [["resignation_received", "offboarding_acknowledged", "access_disable_requested", "laptop_return_arranged", "courier_delivered", "laptop_received", "offboarding_completed"],
                    ["client_ended_engagement", "offboarding_acknowledged", "access_disable_requested", "laptop_return_arranged", "courier_delivered", "laptop_received", "offboarding_completed"]],
    "onboarding": [["contract_sent", "contract_reminder", "contract_signed", "training_enrolled", "induction_meeting", "induction_completed", "kickoff_meeting", "day_one_checkin", "day_one_reply", "onboarded_confirmed"],
                   ["laptop_requested", "laptop_quote", "laptop_approved", "laptop_ordered", "laptop_shipped", "laptop_delivered"],
                   ["it_requested", "it_ready"]],
}


def step_confidence(ev: dict, link: str) -> str:
    if ev["source"] == "screen" or link == "time":
        return "low"
    m = (ev.get("resolution") or {}).get("method")
    if m in ("fuzzy", "context", "chat_pair", "initial", "first_name_unique") or ev["source"] == "calendar":
        return "medium"
    return "high"


def make_step(ev: dict, link: str, link_reason: str, reg: Registry) -> dict:
    return {
        "activity": ev["activity"], "label": R.ACTIVITY_LABELS.get(ev["activity"], ev["activity"]), "event_id": ev["event_id"],
        "time_local": ev["time_local"], "time_utc": ev["time_utc"], "actor_id": ev["actor_id"], "actor_name": reg.name(ev["actor_id"]),
        "source": ev["source"], "confidence": step_confidence(ev, link), "likely": ev["source"] == "screen" or bool(ev["fields"].get("likely")),
        "link": link, "link_reason": link_reason, "raw_ref": ev["raw_ref"],
        **({"session": ev["session"]} if ev.get("session") else {}),
    }


class CaseBook:
    def __init__(self, reg: Registry):
        self.reg = reg
        self.cases: dict[str, dict] = {}
        self.unlinked: list[dict] = []

    def new(self, process: str, pid: str, key: str, keyinfo: dict) -> dict:
        cid = f"{process}:{pid[2:]}" + (f":{key}" if key else "")
        c = {"case_id": cid, "process": process, "subject_person_id": pid, "subject_name": self.reg.name(pid), "key": keyinfo, "steps": [], "flags": []}
        self.cases[cid] = c
        return c

    def add(self, case: dict, ev: dict, link: str, reason: str) -> None:
        case["steps"].append(make_step(ev, link, reason, self.reg))
        ev.setdefault("_cases", []).append(case["case_id"])


def build_leave(book: CaseBook, evs: list[dict]) -> None:
    reg = book.reg
    thread_case: dict[str, str] = {}
    by_person: dict[str, list[dict]] = defaultdict(list)
    later = []
    for ev in evs:
        pid, d = ev["subject_person_id"], ev["fields"].get("dates")
        if ev["source"] == "mail" and ev["thread_key"] in thread_case:
            case = book.cases[thread_case[ev["thread_key"]]]
            book.add(case, ev, "thread", "Same mail thread")
        elif d:
            cid = f"leave:{pid[2:]}:{d['start']}_{d['end']}"
            case = book.cases.get(cid) or book.new("leave", pid, f"{d['start']}_{d['end']}", {"dates": {"start": d["start"], "end": d["end"], "raw": d["raw"]}, "leave_type": ev["fields"].get("leave_type")})
            if case not in by_person[pid]:
                by_person[pid].append(case)
            book.add(case, ev, "dates", f"Same person and dates ({d['raw']})")
        else:
            later.append(ev)
            continue
        if ev["source"] == "mail":
            thread_case.setdefault(ev["thread_key"], case["case_id"])
        if ev["fields"].get("leave_type") and not case["key"].get("leave_type"):
            case["key"]["leave_type"] = ev["fields"]["leave_type"]
    # no dates (PeopleHub session, Teams "choose other dates"): time order within the person's cases
    for ev in later:
        t = ts(ev["time_utc"])
        cands = []
        for c in by_person.get(ev["subject_person_id"], []):
            first = min(ts(s["time_utc"]) for s in c["steps"])
            last = max(ts(s["time_utc"]) for s in c["steps"])
            if first - timedelta(hours=6) <= t <= last + timedelta(days=3):
                cands.append((abs((t - first).total_seconds()), first, c))
        open_before = [x for x in cands if x[1] <= t]
        pick = sorted(open_before or cands, key=lambda x: (x[0], x[2]["case_id"]))
        if pick:
            c = sorted(open_before, key=lambda x: x[1])[-1][2] if open_before else pick[0][2]
            book.add(c, ev, "time", "No dates in the record; nearest open leave case of the same person")
        else:
            book.unlinked.append({"event_id": ev["event_id"], "activity": ev["activity"], "reason": "no leave case of this person near this time"})


def build_by_person(book: CaseBook, evs: list[dict], process: str) -> None:
    for ev in evs:
        pid = ev["subject_person_id"]
        cid = f"{process}:{pid[2:]}"
        case = book.cases.get(cid) or book.new(process, pid, "", {})
        book.add(case, ev, "person", "Same person (one case per person)")


def link_screens(book: CaseBook, events: list[dict]) -> dict:
    """Nameless screen sessions + courier mails -> cases, by time only (confidence low)."""
    reg = book.reg
    stats = Counter()
    sessions = [e for e in events if e["source"] == "screen" and e["activity"] and not e["subject_person_id"]]

    def steps_of(process, acts):
        for c in book.cases.values():
            if c["process"] == process:
                for s in c["steps"]:
                    if s["activity"] in acts:
                        yield c, s

    for ev in sessions:
        t = ts(ev["time_utc"])
        owner = ev["actor_id"]
        best = None
        if ev["activity"] == "tracker_updated":  # within 30 min AFTER a PeopleHub or approval step by the same staff member
            for c, s in steps_of("leave", {"peoplehub_opened", "worker_approved"}):
                st = ts(s["session"]["end_utc"]) if s.get("session") else ts(s["time_utc"])
                if s["actor_id"] == owner and timedelta(0) <= t - st <= timedelta(minutes=30):
                    if best is None or st > best[2]:
                        best = (c, s, st)
            reason = lambda c, s, st: f"Leave tracker opened {round((t - st).total_seconds() / 60)} min after {s['label'].lower()} for {c['subject_name']} by the same staff member"  # noqa: E731
        elif ev["activity"] == "courier_booked":  # within 60 min of 'laptop return arranged' by the same staff member
            for c, s in steps_of("offboarding", {"laptop_return_arranged"}):
                st = ts(s["time_utc"])
                if s["actor_id"] == owner and abs(t - st) <= timedelta(minutes=60):
                    if best is None or abs(t - st) < abs(t - best[2]):
                        best = (c, s, st)
            reason = lambda c, s, st: f"SwiftParcel booking page open {round(abs((t - st).total_seconds()) / 60)} min {'after' if t >= st else 'before'} the laptop return mail to {c['subject_name']}"  # noqa: E731
        elif ev["activity"] == "training_enrolled":  # within 30 min of the training mail by the same staff member
            for c, s in steps_of("onboarding", {"training_enrolled"}):
                if s["source"] != "mail":
                    continue
                st = ts(s["time_utc"])
                if s["actor_id"] == owner and abs(t - st) <= timedelta(minutes=30):
                    if best is None or abs(t - st) < abs(t - best[2]):
                        best = (c, s, st)
            reason = lambda c, s, st: f"Academy learners page open {round(abs((t - st).total_seconds()) / 60)} min {'after' if t >= st else 'before'} the training mail to {c['subject_name']}"  # noqa: E731
        else:
            continue
        if best:
            c, s, st = best
            book.add(c, ev, "time", reason(c, s, st))
            ev["_linked_case"] = c["case_id"]
            stats[f"{ev['activity']}:linked"] += 1
        else:
            stats[f"{ev['activity']}:unlinked"] += 1

    # SwiftParcel 'Delivered' mail has no name: the open return case whose return was arranged before it
    # and whose laptop came back after it (same staff mailbox). Fallback: arranged before, nothing back yet.
    deliveries = sorted((e for e in events if e["activity"] == "courier_delivered"), key=lambda e: e["time_utc"])
    for ev in deliveries:
        t = ts(ev["time_utc"])
        strict, loose = [], []
        for c in book.cases.values():
            if c["process"] != "offboarding" or any(s["activity"] == "courier_delivered" for s in c["steps"]):
                continue
            arr = [ts(s["time_utc"]) for s in c["steps"] if s["activity"] == "laptop_return_arranged" and s["actor_id"] == ev["fields"].get("owner_staff_id")]
            rec = [ts(s["time_utc"]) for s in c["steps"] if s["activity"] == "laptop_received"]
            if not arr or min(arr) > t:
                continue
            if rec and min(rec) >= t:
                strict.append((min(rec), c))
            elif not rec:
                loose.append((min(arr), c))
        if strict:
            rec_t, c = sorted(strict, key=lambda x: x[0])[0]
            why = f"No name; {c['subject_name']}'s return was arranged before this delivery and the laptop came back {round((rec_t - t).total_seconds() / 60)} min later"
        elif len(loose) == 1:
            c = loose[0][1]
            why = f"No name; the only open return case of this staff member ({c['subject_name']}) with no laptop back yet"
        else:
            book.unlinked.append({"event_id": ev["event_id"], "activity": ev["activity"], "reason": f"{len(loose)} open return cases fit; not guessing"})
            stats["courier_delivered:unlinked"] += 1
            continue
        book.add(c, ev, "time", why)
        stats["courier_delivered:linked"] += 1
    return dict(stats)


def finish_case(c: dict, reg: Registry, last_days: dict) -> None:
    c["steps"].sort(key=lambda s: (s["time_utc"], s["event_id"]))
    acts = [s["activity"] for s in c["steps"]]
    c["start"] = c["steps"][0]["time_local"]
    c["end"] = c["steps"][-1]["time_local"]
    staff = [s["actor_id"] for s in c["steps"] if reg.is_exported_staff(s["actor_id"])]
    people_ops = [p for p in staff if reg.people[p].get("job_title") == "People Operations"]
    c["staff_involved"] = list(dict.fromkeys(people_ops or staff))
    c["owner_staff_id"] = Counter(people_ops or staff).most_common(1)[0][0] if staff else None
    c["handoff"] = len(c["staff_involved"]) > 1
    c["client"] = None
    clients = Counter()
    for s in c["steps"]:
        cl = s.pop("_client", None)
        if cl:
            clients[cl] += 1
    trig = TRIGGERS[c["process"]] & set(acts)
    before, after = [], []
    if not trig:
        before.append("trigger not in the data (likely before 2 Mar, or sent to a mailbox that was not exported)")
    p = c["process"]
    completed = False
    if p == "leave":
        if "cancel_requested" in acts:
            status = "cancelled"
        elif "worker_approved" in acts:
            status, completed = "complete", True
        elif {"client_declined", "worker_asked_other_dates"} & set(acts):
            status = "declined"
        else:
            status = "in_progress"
        c["key"].setdefault("dates", None)
    elif p == "offboarding":
        completed = "offboarding_completed" in acts
        status = "complete" if completed else "in_progress"
        ld = last_days.get(c["subject_person_id"], {}).get("last_day")
        c["key"]["last_day"] = ld
        if not completed and ld and date.fromisoformat(ld) > WINDOW_END.date():
            after.append(f"last day {nice_day(ld)} is after 29 Mar")
    else:
        completed = "onboarded_confirmed" in acts
        status = "complete" if completed else "in_progress"
        fd = sorted({s.get("_first_day") for s in c["steps"] if s.get("_first_day")})
        c["key"]["first_day"] = fd[0] if fd else None
        if not completed and fd and date.fromisoformat(fd[0]) > WINDOW_END.date():
            after.append(f"first day {nice_day(fd[0])} is after 29 Mar")
    c["status"] = status  # outcome only: complete | in_progress | declined | cancelled
    c["started_before_window"] = bool(before)
    c["ends_after_window"] = bool(after)
    c["window_notes"] = before + after
    for s in c["steps"]:
        s.pop("_first_day", None)
    c["last_activity"] = c["end"]


def summarise(c: dict, reg: Registry) -> str:
    who = c["subject_name"]
    owner = reg.name(c["owner_staff_id"]) or "unknown owner"
    client = reg.orgs.get(c["client"], {}).get("name") if c["client"] else None
    if c["process"] == "leave":
        d = c["key"].get("dates") or {}
        lt = c["key"].get("leave_type") or "leave"
        what = f"{lt} leave {d.get('raw', '')}".replace("personal leave", "personal day")
    elif c["process"] == "offboarding":
        what = "offboarding" + (f", last day {nice_day(c['key'].get('last_day'))}" if c["key"].get("last_day") else "")
    else:
        what = "onboarding" + (f", first day {nice_day(c['key'].get('first_day'))}" if c["key"].get("first_day") else "")
    status = c["status"].replace("_", " ")
    return f"{who}: {what}{' at ' + client if client else ''}. Handled by {owner}{' (hand-off: ' + ' → '.join(reg.name(x) for x in c['staff_involved']) + ')' if c['handoff'] else ''}. {len(c['steps'])} steps, {status}."


def out_of_order(c: dict) -> list[dict]:
    issues = []
    for track in EXPECTED_TRACKS[c["process"]]:
        rank = {a: i for i, a in enumerate(track)}
        firsts = {}
        for s in c["steps"]:
            if s["activity"] in rank and s["activity"] not in firsts:
                firsts[s["activity"]] = s
        seq = sorted(firsts.values(), key=lambda s: s["time_utc"])
        for i, a in enumerate(seq):
            for b in seq[i + 1:]:
                if rank[b["activity"]] < rank[a["activity"]]:
                    issues.append({"earlier": a["activity"], "earlier_time": a["time_local"][:16], "later": b["activity"], "later_time": b["time_local"][:16], "expected": f"{b['activity']} before {a['activity']}"})
    seen = set()
    uniq = []
    for x in issues:
        k = (x["earlier"], x["later"])
        if k not in seen:
            seen.add(k)
            uniq.append(x)
    return uniq


def step3_cases(clean: dict) -> dict:
    events, reg = clean["events"], clean["registry"]
    book = CaseBook(reg)
    proc = sorted((e for e in events if e["category"] == "process" and e["subject_person_id"]), key=lambda e: (e["time_utc"], e["event_id"]))
    build_leave(book, [e for e in proc if e["process"] == "leave"])
    build_by_person(book, [e for e in proc if e["process"] == "offboarding"], "offboarding")
    build_by_person(book, [e for e in proc if e["process"] == "onboarding"], "onboarding")

    # cross-process data: last day per person (Phase 3 flags activity after it)
    last_days: dict[str, dict] = {}
    for e in proc:
        if e["process"] != "offboarding":
            continue
        rec = last_days.setdefault(e["subject_person_id"], {"person_id": e["subject_person_id"], "name": reg.name(e["subject_person_id"]), "last_day": None, "last_day_sources": [], "offboarding_completed_local": None})
        if e["fields"].get("last_day") and e["activity"] in ("resignation_received", "client_ended_engagement", "access_disable_requested"):
            rec["last_day_sources"].append({"event_id": e["event_id"], "activity": e["activity"], "last_day": e["fields"]["last_day"]})
        if e["activity"] == "offboarding_completed":
            rec["offboarding_completed_local"] = e["time_local"]
    for rec in last_days.values():
        days = sorted({s["last_day"] for s in rec["last_day_sources"]})
        rec["last_day"] = days[0] if days else None
        if len(days) > 1:
            rec["conflict"] = f"different last days stated: {days}"
        rec["effective_end"] = rec["last_day"] or (rec["offboarding_completed_local"] or "")[:10] or None

    link_stats = link_screens(book, events)

    by_id = {e["event_id"]: e for e in events}
    for c in book.cases.values():
        for s in c["steps"]:
            ev = by_id[s["event_id"]]
            if ev["fields"].get("client"):
                s["_client"] = ev["fields"]["client"]
            if ev["fields"].get("first_day"):
                s["_first_day"] = ev["fields"]["first_day"]
        clients = Counter(by_id[s["event_id"]]["fields"].get("client") for s in c["steps"] if by_id[s["event_id"]]["fields"].get("client"))
        finish_case(c, reg, last_days)
        c["client"] = clients.most_common(1)[0][0] if clients else None
        c["summary"] = summarise(c, reg)
        c["out_of_order"] = out_of_order(c)

    unlinked = list(book.unlinked)
    for e in events:
        if e["category"] == "process" and not e.get("_cases"):
            unlinked.append({"event_id": e["event_id"], "activity": e["activity"], "reason": (e.get("resolution") or {}).get("reason") or "no subject"})
    cases = sorted(book.cases.values(), key=lambda c: (c["process"], c["subject_name"], c["start"]))
    doc = {
        "step": "3_cases",
        "statuses": "complete | in_progress | declined | cancelled (window badges: started_before_window, ends_after_window)",
        "cases": cases,
        "person_last_days": [last_days[k] for k in sorted(last_days)],
        "screen_link_stats": link_stats,
        "unlinked_process_events": sorted(unlinked, key=lambda x: x["event_id"]),
    }
    write_json(OUT / "3_cases.json", doc, compact=True)
    for e in events:
        e.pop("_cases", None)
        e.pop("_linked_case", None)
    return {"cases": cases, "doc": doc, "events": events, "registry": reg}


# --------------------------------------------------------------------------- step 4: process discovery

from statistics import median as _median

SUPPORT_CORE = 50.0  # % of cases; below this an activity is "optional"


def hours(a: str, b: str) -> float:
    return round((ts(b) - ts(a)).total_seconds() / 3600, 1)


def trace(c: dict, explicit_only: bool = False) -> list[str]:
    """Activities in time order, consecutive repeats collapsed. explicit_only drops screen-based steps."""
    out = []
    for s in c["steps"]:
        if explicit_only and s["source"] == "screen":
            continue
        if not out or out[-1] != s["activity"]:
            out.append(s["activity"])
    return out


def first_order(c: dict, explicit_only: bool = True) -> tuple[str, ...]:
    seen = []
    for a in trace(c, explicit_only):
        if a not in seen:
            seen.append(a)
    return tuple(seen)


def first_time(c: dict, act: str) -> str | None:
    return next((s["time_utc"] for s in c["steps"] if s["activity"] == act), None)


def discover(process: str, cases: list[dict]) -> dict:
    n = len(cases)
    full = [c for c in cases if c["status"] == "complete" and not c["started_before_window"]]
    acts = sorted({s["activity"] for c in cases for s in c["steps"]})
    support = {a: round(100 * sum(1 for c in cases if any(s["activity"] == a for s in c["steps"])) / n, 1) for a in acts}

    # variants over explicit (non-screen) steps, first-occurrence order
    var = defaultdict(list)
    for c in cases:
        var[first_order(c)].append(c)
    variants = [{"path": list(p), "count": len(cs), "case_ids": sorted(x["case_id"] for x in cs), "statuses": dict(Counter(x["status"] for x in cs))} for p, cs in sorted(var.items(), key=lambda kv: (-len(kv[1]), kv[0]))]

    # main path: most common variant among full traces; if every full trace is unique, a consensus order
    full_var = Counter(first_order(c) for c in full)
    ranked = sorted(full_var.items(), key=lambda kv: (-kv[1], kv[0]))
    alternatives = []
    if ranked and ranked[0][1] >= 2:
        path, cnt = list(ranked[0][0]), ranked[0][1]
        alternatives = [{"path": list(p), "count": k} for p, k in ranked[1:] if k == cnt]
        method = f"most common variant among the {len(full)} complete cases that start inside the window ({cnt} of {len(full)})" + (f"; tied with {len(alternatives)} other variant(s)" if alternatives else "")
    else:
        # no variant repeats: consensus order of the common activities (support >= 50% over all cases),
        # ordered by pairwise precedence (how often A comes before B), robust to cases cut by the window
        core = [a for a in acts if support[a] >= SUPPORT_CORE and not all(s["source"] == "screen" for c in cases for s in c["steps"] if s["activity"] == a)]
        wins = Counter()
        for a in core:
            for b in core:
                if a != b:
                    before = sum(1 for c in cases if first_time(c, a) and first_time(c, b) and first_time(c, a) < first_time(c, b))
                    after = sum(1 for c in cases if first_time(c, a) and first_time(c, b) and first_time(c, a) > first_time(c, b))
                    wins[a] += before > after
        path = sorted(core, key=lambda a: (-wins[a], a))
        method = f"no variant repeats among the {len(full)} complete in-window cases; consensus path: activities in >= {SUPPORT_CORE:.0f}% of all {n} cases, ordered by how often each comes before the others"
        cnt = sum(1 for c in cases if tuple(a for a in first_order(c) if a in path) == tuple(path))

    # directly-follows graph (all steps, repeats collapsed)
    dfg = Counter()
    for c in cases:
        t = trace(c)
        dfg.update(zip(t, t[1:]))

    # median time between consecutive main-path steps
    to_next = {}
    for a, b in zip(path, path[1:]):
        gaps = [hours(first_time(c, a), first_time(c, b)) for c in cases if first_time(c, a) and first_time(c, b) and first_time(c, b) >= first_time(c, a)]
        to_next[a] = {"to": b, "median_h": round(_median(gaps), 1) if gaps else None, "n": len(gaps)}

    steps = []
    for a in sorted(acts, key=lambda a: (path.index(a) if a in path else 99, -support[a], a)):
        conf = Counter(s["confidence"] for c in cases for s in c["steps"] if s["activity"] == a)
        offs = [hours(c["steps"][0]["time_utc"], first_time(c, a)) for c in cases if first_time(c, a)]
        steps.append({
            "activity": a, "label": R.ACTIVITY_LABELS.get(a, a), "support_pct": support[a],
            "case_count": sum(1 for c in cases if first_time(c, a)), "confidence_mix": dict(sorted(conf.items())),
            "on_main_path": a in path, "optional": support[a] < SUPPORT_CORE,
            "median_from_case_start_h": round(_median(offs), 1) if offs else None,
            "median_to_next_h": to_next.get(a, {}).get("median_h"), "next_on_main_path": to_next.get(a, {}).get("to"),
            "screen_only": all(s["source"] == "screen" for c in cases for s in c["steps"] if s["activity"] == a),
        })
    return {
        "process": process, "case_count": n, "full_trace_cases": len(full),
        "status_counts": dict(sorted(Counter(c["status"] for c in cases).items())),
        "window_badges": {"started_before_window": sum(c["started_before_window"] for c in cases), "ends_after_window": sum(c["ends_after_window"] for c in cases)},
        "main_path": {"activities": path, "labels": [R.ACTIVITY_LABELS.get(a, a) for a in path], "method": method, "cases_following_exactly": cnt, "tied_alternatives": alternatives},
        "steps": steps,
        "dfg": [{"from": a, "to": b, "count": k} for (a, b), k in sorted(dfg.items(), key=lambda kv: (-kv[1], kv[0]))],
        "variants": variants,
    }


# --------------------------------------------------------------------------- step 5: flags


def step5_flags(cases: list[dict], events: list[dict], reg: Registry, last_days: list[dict]) -> list[dict]:
    flags = []
    by_case = {c["case_id"]: c for c in cases}
    nm = reg.name

    def add(rule, case_id, message, evidence, severity="warning", scope="case", process=None):
        c = by_case.get(case_id)
        flags.append({"flag_id": f"{rule}:{case_id or process}", "rule": rule, "scope": scope, "severity": severity,
                      "case_id": case_id, "process": process or (c["process"] if c else None),
                      "person_id": c["subject_person_id"] if c else None, "person_name": c["subject_name"] if c else None,
                      "message": message, "evidence_event_ids": sorted(set(evidence))})

    # a. any activity for a person after their last day
    for rec in last_days:
        end = rec["last_day"] or rec["effective_end"]
        if not end:
            continue
        what_end = f"last day {nice_day(rec['last_day'])}" if rec["last_day"] else f"offboarding completed {nice_day(end)}"
        off_case = next((c["case_id"] for c in cases if c["process"] == "offboarding" and c["subject_person_id"] == rec["person_id"]), None)
        end_ev = [s["event_id"] for s in by_case[off_case]["steps"] if s["activity"] in ("resignation_received", "client_ended_engagement", "offboarding_completed", "access_disable_requested")] if off_case else []
        for c in cases:
            if c["subject_person_id"] != rec["person_id"] or c["process"] == "offboarding":
                continue
            msgs, ev = [], []
            d = (c["key"].get("dates") or {})
            if c["process"] == "leave" and d.get("start") and d["start"] >= end:
                approved = any(s["activity"] in ("worker_approved", "client_approved") for s in c["steps"])
                msgs.append(f"leave for {d['raw']} was {'approved' if approved else 'requested'}, but that is on or after the {what_end}")
                ev += [s["event_id"] for s in c["steps"] if s["activity"] in ("leave_requested", "worker_approved", "client_approved")]
            late = [s for s in c["steps"] if s["time_local"][:10] > end]
            if late:
                msgs.append(f"{len(late)} step(s) happened after the {what_end} (first: {late[0]['label'].lower()} on {nice_day(late[0]['time_local'][:10])})")
                ev += [s["event_id"] for s in late]
            if msgs:
                add("activity_after_last_day", c["case_id"], f"{c['subject_name']}: " + "; ".join(msgs) + ".", ev + end_ev)
        # out-of-scope laptop activity (replacement requests / orders) about the same person
        oos = [e for e in events if e["subject_person_id"] == rec["person_id"] and e["category"] == "out_of_scope" and ("laptop" in (e["noise_reason"] or ""))]
        hits = [e for e in oos if e["time_local"][:10] >= end or (e["fields"].get("needed_by") or "") > end]
        if hits and off_case:
            parts = []
            for e in hits:
                if e["fields"].get("needed_by"):
                    parts.append(f"replacement laptop requested on {nice_day(e['time_local'][:10])}, needed by {nice_day(e['fields']['needed_by'])}")
                else:
                    parts.append(f"{(e['fields'].get('was_activity') or 'laptop activity').replace('_', ' ')} on {nice_day(e['time_local'][:10])}")
            add("activity_after_last_day", off_case, f"{rec['name']}: " + "; ".join(parts) + f" — on or after the {what_end}.", [e["event_id"] for e in hits] + end_ev)

    # b-d. onboarding checks
    for c in cases:
        if c["process"] != "onboarding":
            continue
        st = {a: [s for s in c["steps"] if s["activity"] == a] for a in {s["activity"] for s in c["steps"]}}
        onb = (st.get("onboarded_confirmed") or [None])[0]
        delivered = sorted(st.get("laptop_delivered", []) + st.get("laptop_confirmed_by_starter", []), key=lambda s: s["time_utc"])
        if onb:
            if delivered and delivered[0]["time_utc"] > onb["time_utc"]:
                add("onboarded_before_laptop", c["case_id"], f"{c['subject_name']} was confirmed onboarded on {nice_day(onb['time_local'][:10])}; the laptop arrived {round(hours(onb['time_utc'], delivered[0]['time_utc']) / 24, 1)} days later ({nice_day(delivered[0]['time_local'][:10])}).", [onb["event_id"], delivered[0]["event_id"]])
            elif not delivered:
                req = st.get("laptop_requested", [])
                tail = f"the laptop was only requested on {nice_day(req[0]['time_local'][:10])}" if req and req[0]["time_utc"] > onb["time_utc"] else ("a laptop was requested but no delivery is in the data" if req else "no laptop request or delivery is in the data")
                add("onboarded_before_laptop", c["case_id"], f"{c['subject_name']} was confirmed onboarded on {nice_day(onb['time_local'][:10])}; {tail}.", [onb["event_id"]] + [s["event_id"] for s in req[:1]], severity="check")
        for req in st.get("laptop_requested", []):
            ev = next(e for e in events if e["event_id"] == req["event_id"])
            nb, fd, day = ev["fields"].get("needed_by"), c["key"].get("first_day"), req["time_local"][:10]
            msgs = []
            if nb and day > nb:
                msgs.append(f"needed by {nice_day(nb)}{' (the start date)' if nb == fd else ''}, so {(date.fromisoformat(day) - date.fromisoformat(nb)).days} day(s) late")
            if fd and day > fd and fd != nb:
                msgs.append(f"also after the start date {nice_day(fd)}")
            if msgs:
                add("laptop_requested_late", c["case_id"], f"Laptop for {c['subject_name']} requested on {nice_day(day)}: " + ", ".join(msgs) + ".", [req["event_id"]] + [s["event_id"] for s in st.get("welcome_sent", [])[:1]])
        issues = [s for s in st.get("day_one_reply", []) if next(e for e in events if e["event_id"] == s["event_id"])["fields"].get("reports_issue")]
        if issues and onb:
            iss_ev = next(e for e in events if e["event_id"] == issues[0]["event_id"])
            quote = iss_ev["text"].split("\n")
            quote = next((q.strip() for q in quote if R.DAY_ONE_ISSUE.search(q)), iss_ev["text"][:80])
            add("onboarded_with_open_issue", c["case_id"], f"{c['subject_name']} replied on {nice_day(issues[0]['time_local'][:10])}: \"{quote}\". Confirmed onboarded on {nice_day(onb['time_local'][:10])} with no fix in the data.", [issues[0]["event_id"], onb["event_id"]])

    # e. cancel requested with no later action
    for c in cases:
        cancels = [s for s in c["steps"] if s["activity"] == "cancel_requested"]
        if cancels:
            later = [s for s in c["steps"] if s["time_utc"] > cancels[-1]["time_utc"]]
            if not later:
                add("cancel_no_followup", c["case_id"], f"{c['subject_name']} asked on {nice_day(cancels[-1]['time_local'][:10])} to cancel leave for {(c['key'].get('dates') or {}).get('raw')}; no reply, client update or tracker change follows in the data.", [s["event_id"] for s in c["steps"] if s["activity"] in ("cancel_requested", "client_approved", "worker_approved")])

    # f. sick leave handled two ways (process level)
    sick = [c for c in cases if c["process"] == "leave" and c["key"].get("leave_type") == "sick"]
    ask = [c for c in sick if any(s["activity"] == "client_check_sent" for s in c["steps"])]
    notify = [c for c in sick if any(s["activity"] == "client_notified_sick" for s in c["steps"])]
    if ask and notify:
        def who(cs):
            return ", ".join(f"{nm(k)} {v}" for k, v in sorted(Counter(c["owner_staff_id"] for c in cs).items(), key=lambda kv: nm(kv[0])))
        ev = [next(s["event_id"] for s in c["steps"] if s["activity"] in ("client_check_sent", "client_notified_sick")) for c in ask + notify]
        add("sick_leave_two_ways", None, f"Sick leave is handled two ways: in {len(ask)} of {len(sick)} sick-leave cases the client was asked for approval ({who(ask)}); in {len(notify)} the client was only told ({who(notify)}). Please confirm which rule applies.", ev, severity="question", scope="process", process="leave")

    flags.sort(key=lambda f: (f["rule"], f["case_id"] or "", f["flag_id"]))
    for f in flags:
        if f["case_id"]:
            by_case[f["case_id"]]["flags"].append(f["flag_id"])
    return flags


# --------------------------------------------------------------------------- open questions (validation)


def open_questions(models: dict, cases: list[dict], flags: list[dict], events: list[dict]) -> dict:
    q = defaultdict(list)
    by = defaultdict(list)
    for c in cases:
        by[c["process"]].append(c)
    has = lambda c, a: any(s["activity"] == a for s in c["steps"])  # noqa: E731
    fr = Counter(f["rule"] for f in flags)

    L = by["leave"]
    tr = sum(has(c, "tracker_updated") for c in L)
    q["leave"].append({"question": "Do you update the Leave tracker after each request, or in batches?", "why": f"The tracker was open within 30 min of a PeopleHub or approval step in only {tr} of {len(L)} leave cases; it is open for long stretches at other times.", "evidence": {"cases_with_tracker_step": tr, "leave_cases": len(L)}})
    sick = [c for c in L if c["key"].get("leave_type") == "sick"]
    asked = sum(has(c, "client_check_sent") for c in sick)
    q["leave"].append({"question": "Is sick leave a notice to the client, or a request the client must approve?", "why": f"Of {len(sick)} sick-leave cases, {asked} asked the client and {len(sick) - asked} only told the client.", "evidence": {"asked": asked, "notified": len(sick) - asked}})
    ph = [c for c in L if has(c, "peoplehub_opened") and has(c, "client_check_sent")]
    ph_before = sum(first_time(c, "peoplehub_opened") <= first_time(c, "client_check_sent") for c in ph)
    q["leave"].append({"question": "Do you check the person in PeopleHub before you ask the client, every time?", "why": f"PeopleHub was seen open before the client check in {ph_before} of {len(ph)} cases where both appear, but PeopleHub shows up in only {sum(has(c, 'peoplehub_opened') for c in L)} of {len(L)} leave cases.", "evidence": {"before": ph_before, "both": len(ph)}})
    dec = [c for c in L if c["status"] == "declined"]
    q["leave"].append({"question": "When a client declines, who follows up: do you wait for the worker to send new dates?", "why": f"{len(dec)} cases were declined and the worker asked for other dates; a new request for the same person appears afterwards in {sum(any(o['subject_person_id'] == c['subject_person_id'] and o['start'] > c['end'] for o in L) for c in dec)} of them.", "evidence": {"declined": len(dec)}})
    q["leave"].append({"question": "When a worker cancels leave, do you tell the client and update PeopleHub and the tracker?", "why": f"{fr['cancel_no_followup']} cancel request(s) have no later action in the data.", "evidence": {"cancel_no_followup": fr["cancel_no_followup"]}})

    O = by["offboarding"]
    no_trig = sum(c["started_before_window"] for c in O)
    q["offboarding"].append({"question": "Where does a resignation or end-of-engagement notice arrive first: with you, or with the Account Manager?", "why": f"{no_trig} of {len(O)} offboarding cases have no trigger in the data; Account Manager mailboxes were not exported.", "evidence": {"no_trigger": no_trig}})
    gaps = []
    for c in O:
        ld = c["key"].get("last_day")
        acc = first_time(c, "access_disable_requested")
        if ld and acc:
            gaps.append((date.fromisoformat(ld) - date.fromisoformat(to_local(ts(acc))[:10])).days)
    if gaps:
        q["offboarding"].append({"question": "How far ahead of the last day do you ask IT to disable access?", "why": f"Requests went out between {min(gaps)} and {max(gaps)} days before the last day (median {_median(gaps)}).", "evidence": {"days_before_last_day": sorted(gaps)}})
    comp = [c for c in O if has(c, "offboarding_completed")]
    after_wipe = sum(has(c, "laptop_received") and first_time(c, "laptop_received") <= first_time(c, "offboarding_completed") for c in comp)
    q["offboarding"].append({"question": "Do you send 'Offboarding complete' only after IT confirms the laptop is back and wiped?", "why": f"In {after_wipe} of {len(comp)} completed cases IT's 'laptop back' message came first; the others have no such message in the data.", "evidence": {"after_laptop_back": after_wipe, "completed": len(comp)}})
    q["offboarding"].append({"question": "Should anything else stop once someone leaves (leave approvals, replacement laptops)?", "why": f"{fr['activity_after_last_day']} flag(s) show leave or laptop activity on or after a person's last day.", "evidence": {"activity_after_last_day": fr["activity_after_last_day"]}})

    N = by["onboarding"]
    ko = [c for c in N if has(c, "kickoff_meeting") and (has(c, "day_one_checkin") or c["key"].get("first_day"))]
    ko_after = sum(1 for c in ko if c["key"].get("first_day") and to_local(ts(first_time(c, "kickoff_meeting")))[:10] > c["key"]["first_day"])
    ko_known = sum(1 for c in ko if c["key"].get("first_day"))
    q["onboarding"].append({"question": "Is the client kick-off before or after the starter's first day?", "why": f"The kick-off was after the first day in {ko_after} of {ko_known} cases with both dates.", "evidence": {"after_first_day": ko_after, "cases": ko_known}})
    q["onboarding"].append({"question": "Should a starter be confirmed 'onboarded' before the laptop has arrived?", "why": f"{fr['onboarded_before_laptop']} onboarded starter(s) had no laptop yet, or got it later.", "evidence": {"onboarded_before_laptop": fr["onboarded_before_laptop"]}})
    q["onboarding"].append({"question": "When should the laptop request go to Procurement?", "why": f"{fr['laptop_requested_late']} request(s) were posted after their own needed-by date.", "evidence": {"laptop_requested_late": fr["laptop_requested_late"]}})
    replies = [e for e in events if e["activity"] == "day_one_reply"]
    dms = [e for e in replies if e["fields"].get("reports_issue")]
    q["onboarding"].append({"question": "Who owns client system access (for example the client DMS), and who chases it after day one?", "why": f"{len(dms)} of {len(replies)} starters who answered the day-one check-in were still waiting on DMS access.", "evidence": {"dms_issue": len(dms), "replies": len(replies)}})
    hand = sum(c["handoff"] for c in N)
    q["onboarding"].append({"question": "How is an onboarding handed over between Hana and Lerato?", "why": f"{hand} of {len(N)} onboarding cases moved between the two of you mid-way.", "evidence": {"handoffs": hand}})
    for p in q:
        q[p] = q[p][:5]
    return dict(q)


def insights(cases: list[dict], events: list[dict]) -> dict:
    replies = [e for e in events if e["activity"] == "day_one_reply"]
    dms = [e for e in replies if e["fields"].get("reports_issue")]
    return {"onboarding": [{"insight": "day_one_dms_issue", "message": f"{len(dms)} of {len(replies)} starters who replied to the day-one check-in reported they were still waiting on DMS access.", "evidence_event_ids": sorted(e["event_id"] for e in dms)}]}


def run_phase3(cases_out: dict) -> dict:
    cases, events, reg = cases_out["cases"], cases_out["events"], cases_out["registry"]
    flags = step5_flags(cases, events, reg, cases_out["doc"]["person_last_days"])
    write_json(OUT / "3_cases.json", cases_out["doc"], compact=True)  # cases now carry their flag ids
    models = {p: discover(p, [c for c in cases if c["process"] == p]) for p in ("leave", "offboarding", "onboarding")}
    qs = open_questions(models, cases, flags, events)
    ins = insights(cases, events)
    for p, m in models.items():
        m["open_questions"] = qs.get(p, [])
        m["insights"] = ins.get(p, [])
        m["process_flags"] = [f["flag_id"] for f in flags if f["scope"] == "process" and f["process"] == p]
    write_json(OUT / "4_processes.json", {"step": "4_processes", "processes": [models[p] for p in ("leave", "offboarding", "onboarding")], "seen_not_modelled": ["recruitment (HireTrack, Recruitment tracker)", "laptop replacements", "birthday gifts", "payslip / timesheet / invoice queries"]})
    write_json(OUT / "5_flags.json", {"step": "5_flags", "counts": dict(sorted(Counter(f["rule"] for f in flags).items())), "flags": flags})
    return {"models": models, "flags": flags}


# --------------------------------------------------------------------------- reports


def skeleton(s: str) -> str:
    s = re.sub(r"\b[A-Z][\w'’\-]+\b", "X", s)
    s = re.sub(r"\d+", "9", s)
    s = re.sub(r"(X[ ,.]*)+", "X ", s)
    return re.sub(r"\s+", " ", s).strip()


def phase1_report(ingest: dict, clean: dict) -> dict:
    events, reg = clean["events"], clean["registry"]
    name = reg.name
    by_src_cat: dict = defaultdict(Counter)
    for ev in events:
        by_src_cat[ev["source"]][ev["category"]] += 1
    act: dict = defaultdict(Counter)
    for ev in events:
        if ev["category"] == "process":
            act[ev["process"]][ev["activity"]] += 1
    screen_acts = Counter((ev["activity"], ev["category"]) for ev in events if ev["source"] == "screen" and ev["activity"])
    allday = [{"subject": ev["title"], "date": ev["time_local"][:10], "mailbox": ev["mailbox"], "category": ev["category"], "reason": ev["noise_reason"] or ev["activity"]} for ev in events if ev["source"] == "calendar" and ev["meta"].get("is_all_day")]
    soft = []
    for ev in events:
        r = ev.get("resolution") or {}
        if r.get("method") in ("fuzzy", "context", "ambiguous", "chat_pair", "initial", "first_name_unique") or (r.get("method") == "unresolved" and r.get("raw_name")):
            soft.append({"event_id": ev["event_id"], "time_local": ev["time_local"][:16], "activity": ev["activity"], "process": ev["process"], "raw_name": r.get("raw_name"), "method": r["method"], "chosen": name(ev["subject_person_id"]), "candidates": [name(c) for c in r.get("candidates", [])], "reason": r.get("reason")})
    groups: dict = defaultdict(list)
    for ev in events:
        if ev["source"] in ("mail", "teams_chat", "teams_channel") and ev["noise_reason"] == "no rule matched":
            txt = " ".join(ev["text"].split())
            groups[(ev["source"], skeleton(f'{ev["title"] or ""} | {txt}' if ev["source"] == "mail" else txt))].append(ev)
    unmatched = [{"source": s, "count": len(v), "example": (f'{v[0]["title"]} | ' if v[0]["title"] else "") + " ".join(v[0]["text"].split())[:140]} for (s, _), v in sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0]))]
    stages = {
        "raw": sum(ingest["raw_counts"].values()),
        "screen_frames": ingest["screen_frames"],
        "after_dedup_and_sessions": len(events),
        **{c: sum(1 for e in events if e["category"] == c) for c in ("noise", "out_of_scope", "context", "process")},
    }
    possible_same = [{"name": d["name"], "ids": d["ids"], "reason": d["reason"]} for d in clean["merges"]["decisions"] if not d["merged"]]
    merged = [{"name": d["name"], "ids": d["ids"], "reason": d["reason"]} for d in clean["merges"]["decisions"] if d["merged"]]
    return {
        "stages": stages,
        "raw_by_source": ingest["raw_counts"],
        "events_by_source": ingest["dedup_counts"],
        "category_by_source": {s: dict(sorted(c.items())) for s, c in sorted(by_src_cat.items())},
        "activity_by_process": {p: dict(sorted(c.items(), key=lambda x: -x[1])) for p, c in sorted(act.items())},
        "screen_session_activities": {f"{a}/{c}": n for (a, c), n in sorted(screen_acts.items())},
        "all_day_calendar": allday,
        "soft_resolutions": soft,
        "identity_merged": merged,
        "possible_same_person": possible_same,
        "unmatched_text": unmatched,
        "people_by_kind": dict(sorted(Counter(p["kind"] for p in reg.people.values()).items())),
    }


def phase2_report(cases_out: dict) -> dict:
    cases = cases_out["cases"]
    per = defaultdict(Counter)
    for c in cases:
        per[c["process"]][c["status"]] += 1
    return {
        "cases_by_process_status": {p: dict(sorted(v.items())) for p, v in sorted(per.items())},
        "case_count": len(cases),
        "step_count": sum(len(c["steps"]) for c in cases),
        "screen_link_stats": cases_out["doc"]["screen_link_stats"],
        "unlinked_process_events": cases_out["doc"]["unlinked_process_events"],
        "out_of_order": [{"case_id": c["case_id"], "issues": c["out_of_order"]} for c in cases if c["out_of_order"]],
    }


def run_all() -> dict:
    ingest = step1_ingest()
    clean = step2_clean(ingest)
    p1 = phase1_report(ingest, clean)
    cases = step3_cases(clean)
    p2 = phase2_report(cases)
    p3 = run_phase3(cases)
    stage_counts = {"1_events (non-screen)": sum(1 for e in clean["events"] if e["source"] != "screen"), "screen_frames": ingest["screen_frames"], "screen_sessions": sum(1 for e in clean["events"] if e["source"] == "screen"), **p1["stages"], "cases": len(cases["cases"]), "case_steps": p2["step_count"], "flags": len(p3["flags"])}
    report = {"stage_counts": stage_counts, "phase1": p1, "phase2": p2, "phase3": {
        "main_paths": {p: m["main_path"] for p, m in p3["models"].items()},
        "top_variants": {p: m["variants"][:3] for p, m in p3["models"].items()},
        "flag_counts": dict(sorted(Counter(f["rule"] for f in p3["flags"]).items())),
    }}
    write_json(OUT / "pipeline_report.json", report)
    return {"phase1": p1, "phase2": p2, "phase3": p3, "clean": clean, "cases": cases}


# --------------------------------------------------------------------------- CLI

STEPS = {"profile": step0_profile, "run": run_all}


def print_profile_table(p: dict) -> None:
    srcs = list(PERSON_SOURCES)
    print(f'{"person":<10}' + "".join(f"{s:>12}" for s in srcs) + f'{"total":>9}')
    for folder, info in p["per_person"].items():
        row = [info["sources"][s]["records"] for s in srcs]
        print(f"{folder:<10}" + "".join(f"{n:>12}" for n in row) + f"{sum(row):>9}")
    print(f'channel: {p["shared"]["teams_channel"]["records"]}   raw total: {p["totals"]["raw_records"]}')


def main(argv: list[str]) -> int:
    wanted = argv[1:] or list(STEPS)
    for name in wanted:
        if name not in STEPS:
            print(f"unknown step {name!r}; choose from {list(STEPS)}", file=sys.stderr)
            return 2
        result = STEPS[name]()
        if name == "profile":
            print_profile_table(result)
        else:
            print(json.dumps(result["phase1"]["stages"]))
            print(json.dumps(result["phase2"]["cases_by_process_status"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
