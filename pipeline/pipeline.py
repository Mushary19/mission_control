"""Mission Control pipeline.

Run:  python pipeline/pipeline.py            (all implemented steps)
      python pipeline/pipeline.py profile    (one step: profile | clean)

Steps (each writes to out/):
  0 profile   -> out/0_profile.json
  1 ingest    -> out/1_events.jsonl                       (Phase 1)
  2 clean     -> out/2_events_clean.jsonl, 2_people.json  (Phase 1)
  3 cases     -> out/3_cases.json                         (Phase 2)
  4 discover  -> out/4_processes.json                     (Phase 3)
  5 flags     -> out/5_flags.json, pipeline_report.json   (Phase 3)

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


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


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
# kinds that can never be the subject of a worker case (spec 6.5: staff are never case subjects)
NOT_SUBJECT = {"staff", "it", "client", "vendor"}


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


# --------------------------------------------------------------------------- person registry


class Registry:
    """People seen in headers (mail from/to/cc, calendar organizer/attendees, Teams senders/members)."""

    def __init__(self, directory: list[dict]):
        self.people: dict[str, dict] = {}
        self.by_email: dict[str, str] = {}
        self.by_name: dict[str, str] = {}
        self.by_teams_id: dict[str, str] = {}
        self.orgs: dict[str, dict] = {"o_harbourline": {"org_id": "o_harbourline", "name": "Harbourline Talent", "kind": "employer", "domains": [WORK_DOMAIN]}}
        for d in directory:
            kind = "it" if d["jobTitle"] in STAFF_TITLES_IT else "staff"
            pid = self.add(d["displayName"], d["mail"], kind=kind)
            p = self.people[pid]
            p.update(exported=bool(d.get("exported")), job_title=d["jobTitle"], export_folder=d.get("export_folder"))
            self.by_teams_id[d["id"]] = pid
            p["teams_ids"].append(d["id"])

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

    def kind_for_email(self, email: str) -> str:
        dom = email.split("@")[-1].lower()
        if dom in VENDOR_DOMAINS:
            return "vendor"
        if re.match(r"[a-z]+law\.example$", dom):
            return "client"
        return "unknown"

    def add(self, name: str, email: str | None = None, kind: str | None = None, teams_id: str | None = None) -> str:
        email = (email or "").lower() or None
        if email and email in self.by_email:
            pid = self.by_email[email]
        elif name and norm(name) in self.by_name:
            pid = self.by_name[norm(name)]  # merge personal + work address with the same full name
        else:
            pid = "p_" + slug(name or email)
            self.people[pid] = {
                "person_id": pid,
                "display_name": name or email,
                "emails": [],
                "teams_ids": [],
                "kind": kind or (self.kind_for_email(email) if email else "unknown"),
                "org": None,
                "exported": False,
            }
            if name:
                self.by_name[norm(name)] = pid
        p = self.people[pid]
        if email and email not in p["emails"]:
            p["emails"].append(email)
            self.by_email[email] = pid
            org = self.org_for_domain(email.split("@")[1])
            if org and not p["org"]:
                p["org"] = org
        if teams_id and teams_id not in p["teams_ids"]:
            p["teams_ids"].append(teams_id)
            self.by_teams_id[teams_id] = pid
        return pid

    def first_name(self, pid: str) -> str:
        return norm(self.people[pid]["display_name"]).split(" ")[0]

    def eligible(self) -> list[str]:
        return sorted(pid for pid, p in self.people.items() if p["kind"] not in NOT_SUBJECT)

    def is_exported_staff(self, pid: str | None) -> bool:
        return bool(pid) and self.people[pid]["kind"] in ("staff",) and self.people[pid].get("exported", False)


def addr(x: dict) -> tuple[str, str]:
    e = x.get("emailAddress", x)
    return e.get("name") or "", (e.get("address") or "").lower()


# --------------------------------------------------------------------------- step 1: ingest


def iter_raw():
    """Yield (source, folder, path, line, record) over every raw file, deterministic order."""
    directory = json.loads((DATA / "_shared/directory.json").read_text(encoding="utf-8"))["value"]
    folders = sorted(d["export_folder"] for d in directory if d.get("exported"))
    for folder in folders:
        for source, (relpath, _) in PERSON_SOURCES.items():
            path = DATA / folder / relpath
            if path.exists():
                for line, r in read_jsonl(path):
                    yield source, folder, path, line, r
    for line, r in read_jsonl(DATA / CHANNEL_FILE):
        yield "teams_channel", "_shared", DATA / CHANNEL_FILE, line, r


def step1_ingest() -> dict:
    directory = json.loads((DATA / "_shared/directory.json").read_text(encoding="utf-8"))["value"]
    reg = Registry(directory)
    folder_owner = {d["export_folder"]: reg.by_email[d["mail"].lower()] for d in directory if d.get("exported")}

    events: dict[str, dict] = {}
    raw_counts: Counter = Counter()
    for source, folder, path, line, r in iter_raw():
        raw_counts[source] += 1
        t, _, _ = record_time(source, r)
        meta: dict = {}
        recipients: list[str] = []
        thread_key = None
        title = None
        if source == "mail":
            native = r["internetMessageId"].strip("<>")
            fname, faddr = addr(r["from"])
            actor = reg.add(fname, faddr)
            to = [reg.add(*addr(x)) for x in r.get("toRecipients", [])]
            cc = [reg.add(*addr(x)) for x in r.get("ccRecipients", []) + r.get("bccRecipients", [])]
            recipients = to + [c for c in cc if c not in to]
            title = r.get("subject")
            body = r.get("body") or {}
            text = body.get("content", "") if body.get("contentType") == "text" else strip_html(body.get("content", ""))
            text = text.replace("\r\n", "\n").strip()
            thread_key = f'mail:{r["conversationId"]}'
            meta = {"from_address": faddr, "to": [addr(x)[1] for x in r.get("toRecipients", [])], "cc": [addr(x)[1] for x in r.get("ccRecipients", [])], "to_ids": to}
        elif source == "calendar":
            native = r["iCalUId"]
            oname, oaddr = addr(r["organizer"])
            actor = reg.add(oname, oaddr)
            recipients = [reg.add(*addr(a)) for a in r.get("attendees", [])]
            title = r.get("subject")
            text = strip_html((r.get("body") or {}).get("content", ""))
            end = parse_calendar(r["end"])
            meta = {"from_address": oaddr, "is_all_day": r.get("isAllDay", False), "end_utc": to_iso_z(end), "end_local": to_local(end), "to": [addr(a)[1] for a in r.get("attendees", [])], "to_ids": recipients}
        elif source == "teams_chat":
            native = f'{r["chatId"]}:{r["id"]}'
            u = r["from"]["user"]
            actor = reg.add(u["displayName"], teams_id=u.get("id"))
            members = [reg.add(n) for n in r.get("_members", [])]
            recipients = [m for m in members if m != actor]
            text = strip_html(r["body"]["content"])
            thread_key = f'chat:{r["chatId"]}'
            meta = {"chat_members": members}
        elif source == "teams_channel":
            native = r["id"]
            u = r["from"]["user"]
            actor = reg.add(u["displayName"], teams_id=u.get("id"))
            text = strip_html(r["body"]["content"])
            root = r.get("replyToId") or r["id"]
            thread_key = f"channel:{root}"
            meta = {"channel": r["channelIdentity"].get("_channelName"), "reply_to": r.get("replyToId")}
        else:  # screen
            native = f"{folder}:{line}"
            actor = folder_owner[folder]
            title = r.get("window_title")
            text = ""
            meta = {"url": r.get("url"), "app": r.get("app"), "idle_seconds": r.get("idle_seconds"), "screenshot": r.get("file")}

        eid = f"{source}:{native}"
        if eid in events:  # duplicate copy in another mailbox
            ev = events[eid]
            if folder not in ev["seen_in"]:
                ev["seen_in"].append(folder)
            continue
        events[eid] = {
            "event_id": eid,
            "source": source,
            "mailbox": folder,
            "seen_in": [folder],
            "time_utc": to_iso_z(t),
            "time_local": to_local(t),
            "actor_id": actor,
            "recipients": recipients,
            "title": title,
            "text": text,
            "category": None,
            "noise_reason": None,
            "activity": None,
            "process": None,
            "subject_person_id": None,
            "resolution": None,
            "fields": {},
            "thread_key": thread_key,
            "raw_ref": {"file": rel(path), "line": line},
            "meta": meta,
        }

    ordered = sorted(events.values(), key=lambda e: (e["time_utc"], e["event_id"]))
    OUT.mkdir(exist_ok=True)
    with (OUT / "1_events.jsonl").open("w", encoding="utf-8") as fh:
        for ev in ordered:
            fh.write(json.dumps(ev, sort_keys=True, ensure_ascii=False) + "\n")
    dedup_counts = Counter(e["source"] for e in ordered)
    return {"events": ordered, "registry": reg, "raw_counts": dict(raw_counts), "dedup_counts": dict(dedup_counts)}


# --------------------------------------------------------------------------- step 2: clean (classify + resolve)

HIGH_METHODS = {"email", "full_name", "thread", "sender", "recipient", "chat_member"}
METHOD_RANK = {"email": 0, "sender": 0, "recipient": 0, "chat_member": 0, "thread": 0, "full_name": 1, "chat_pair": 2, "initial": 2, "first_name_unique": 3, "fuzzy": 4, "context": 5, "ambiguous": 8, "unresolved": 9, "staff_name": 9}
CONFIDENCE = {"email": "high", "sender": "high", "recipient": "high", "chat_member": "high", "thread": "high", "full_name": "high", "chat_pair": "medium", "initial": "medium", "first_name_unique": "medium", "fuzzy": "medium", "context": "medium"}
CONTEXT_WINDOW = timedelta(days=30)


def rule_matches(rule: R.Rule, ev: dict, reg: Registry) -> dict | None:
    if ev["source"] not in rule.sources:
        return None
    meta = ev["meta"]
    if rule.reply is not None and ev["source"] == "teams_channel":
        if bool(meta.get("reply_to")) != rule.reply:
            return None
    if rule.direction:
        out = reg.is_exported_staff(ev["actor_id"])
        if (rule.direction == "out") != out:
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


def classify(ev: dict, reg: Registry) -> tuple[R.Rule | None, dict]:
    if ev["source"] == "screen" and (ev["meta"].get("idle_seconds") or 0) > 300:
        return R.Rule("noise_screen_idle", "noise", ("screen",), reason="idle > 300s"), {}
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
    for k in ("vendor", "model", "consignment"):
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
    # client org: explicit text > client contact among sender/recipients
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
    # owner = the exported staff member handling it
    owner = ev["actor_id"] if reg.is_exported_staff(ev["actor_id"]) else next((r for r in ev["recipients"] if reg.is_exported_staff(r)), None)
    if not owner and ev["source"] == "screen":
        owner = ev["actor_id"]
    if owner:
        f["owner_staff_id"] = owner
    if ev["activity"] == "day_one_reply":
        f["reports_issue"] = bool(R.DAY_ONE_ISSUE.search(ev["text"]))
    if warnings:
        f["warnings"] = warnings
    return f


def closest(dist: dict[str, int], limit: int = 2) -> list[str]:
    """Candidates at the minimum edit distance, if that distance is <= limit."""
    if not dist:
        return []
    best = min(dist.values())
    return sorted(pid for pid, d in dist.items() if d == best) if best <= limit else []


class Resolver:
    def __init__(self, reg: Registry):
        self.reg = reg
        self.pool = reg.eligible()
        self.staff_names = {norm(p["display_name"]) for p in reg.people.values() if p["kind"] in ("staff", "it")}
        self.anchors: dict[str, list[dict]] = defaultdict(list)  # person -> high-confidence process events

    # --- direct (no case context)
    def by_name(self, raw: str) -> dict:
        n = norm(raw).rstrip(".")
        toks = n.split(" ")
        names = {pid: norm(self.reg.people[pid]["display_name"]) for pid in self.pool}
        exact = [pid for pid, full in names.items() if full == n]
        if exact:
            return {"method": "full_name", "person": exact[0], "candidates": exact}
        if n in self.staff_names:
            return {"method": "staff_name", "person": None, "candidates": [], "note": "staff are never case subjects"}
        first = toks[0]
        if len(toks) == 2 and len(toks[1].rstrip(".")) == 1:  # "Otto V."
            ini = toks[1][0]
            c = [pid for pid, full in names.items() if full.split(" ")[0] == first and full.split(" ")[-1].startswith(ini)]
            if len(c) == 1:
                return {"method": "initial", "person": c[0], "candidates": c}
            if c:
                return {"method": "needs_context", "person": None, "candidates": sorted(c)}
            toks = [first]
        if len(toks) == 1:
            c = [pid for pid, full in names.items() if full.split(" ")[0] == first]
            if len(c) == 1:
                return {"method": "first_name_unique", "person": c[0], "candidates": c}
            if c:
                return {"method": "needs_context", "person": None, "candidates": sorted(c)}
            c = closest({pid: osa_distance(full.split(" ")[0], first) for pid, full in names.items()}) if len(first) >= 4 else []
            if len(c) == 1:
                return {"method": "fuzzy", "person": c[0], "candidates": c, "typo": True}
            if c:
                return {"method": "needs_context", "person": None, "candidates": c, "typo": True}
            return {"method": "unresolved", "person": None, "candidates": []}
        # full name with a typo ("Chaira Ekwueme", "Qunin Ellingham", "Jvoana Penhaligon")
        c = closest({pid: osa_distance(full, n) for pid, full in names.items()})
        if len(c) == 1:
            return {"method": "fuzzy", "person": c[0], "candidates": c, "typo": True}
        if c:
            return {"method": "needs_context", "person": None, "candidates": c, "typo": True}
        return {"method": "unresolved", "person": None, "candidates": []}

    # --- context: pick from candidates with an open case of the same process near that date
    def by_context(self, cands: list[str], ev: dict) -> dict:
        t = datetime.fromisoformat(ev["time_utc"].replace("Z", "+00:00"))
        f = ev["fields"]
        key_date = (f.get("dates") or {}).get("start"), (f.get("dates") or {}).get("end"), f.get("last_day"), f.get("first_day")

        def anchors_for(pid):
            out = []
            for a in self.anchors.get(pid, []):
                if a["event_id"] == ev["event_id"] or a["process"] != ev["process"]:
                    continue
                at = datetime.fromisoformat(a["time_utc"].replace("Z", "+00:00"))
                if abs(at - t) <= CONTEXT_WINDOW:
                    out.append((a, at))
            return out

        def date_match(a):
            af = a["fields"]
            if f.get("dates") and af.get("dates"):
                return af["dates"]["start"] == key_date[0] and af["dates"]["end"] == key_date[1]
            if f.get("last_day") and af.get("last_day"):
                return af["last_day"] == f["last_day"]
            if f.get("first_day") and af.get("first_day"):
                return af["first_day"] == f["first_day"]
            return False

        filters = [
            ("open before this event", lambda a, at: at <= t),
            ("same dates", lambda a, at: date_match(a)),
            ("same client", lambda a, at: bool(f.get("client")) and a["fields"].get("client") == f.get("client")),
            ("same staff owner", lambda a, at: bool(f.get("owner_staff_id")) and a["fields"].get("owner_staff_id") == f.get("owner_staff_id")),
        ]
        pool = {pid: anchors_for(pid) for pid in cands}
        pool = {pid: a for pid, a in pool.items() if a}
        applied = [f"has a {ev['process']} event within 30 days"]
        if not pool:
            return {"method": "ambiguous", "person": None, "candidates": sorted(cands), "filters": applied, "note": "no candidate has a nearby case of this process"}
        for name, pred in filters:
            if len(pool) == 1:
                break
            narrowed = {pid: [x for x in a if pred(*x)] for pid, a in pool.items()}
            narrowed = {pid: a for pid, a in narrowed.items() if a}
            if narrowed:
                pool = narrowed
                applied.append(name)
        if len(pool) == 1:
            pid = next(iter(pool))
            return {"method": "context", "person": pid, "candidates": sorted(cands), "filters": applied, "evidence_event_ids": sorted(a["event_id"] for a, _ in pool[pid])[:5]}
        return {"method": "ambiguous", "person": None, "candidates": sorted(pool), "filters": applied}


def finish_resolution(res: dict, raw: str | None) -> dict:
    out = {"method": res["method"], "confidence": CONFIDENCE.get(res["method"]), "candidates": res.get("candidates", [])}
    if raw is not None:
        out["raw_name"] = raw
    for k in ("typo", "filters", "note", "evidence_event_ids"):
        if k in res:
            out[k] = res[k]
    return out


def step2_clean(ingest: dict) -> dict:
    events, reg = ingest["events"], ingest["registry"]
    res = Resolver(reg)
    rule_by_event: dict[str, R.Rule] = {}

    # ---- 2a classify
    for ev in events:
        rule, groups = classify(ev, reg)
        if rule is None:
            ev["category"] = "context"
            ev["noise_reason"] = "no rule matched"
            continue
        rule_by_event[ev["event_id"]] = rule
        ev["category"] = rule.category
        ev["fields"]["rule_id"] = rule.id
        if rule.category in ("noise", "out_of_scope", "context"):
            ev["noise_reason"] = rule.reason
        if rule.category == "process":
            ev["activity"], ev["process"] = rule.activity, rule.process
            ev["fields"].update(build_fields(groups, ev, reg))
            if rule.likely:
                ev["fields"]["likely"] = True

    # channel replies follow their root (replacement thread -> out of scope)
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

    proc = [ev for ev in events if ev["category"] == "process"]

    # ---- 2b direct resolution (pass A) -> anchors
    def direct(ev, rule, allow_text=True):
        meta = ev["meta"]
        for how in rule.who:
            if how == "sender" and ev["actor_id"] in res.pool:
                return {"method": "sender" if ev["source"] != "mail" else "email", "person": ev["actor_id"], "candidates": [ev["actor_id"]]}, None
            if how == "recipient" and "to_ids" in meta:  # mail To / calendar attendees only
                for pid in meta["to_ids"]:
                    if pid in res.pool:
                        return {"method": "email", "person": pid, "candidates": [pid]}, None
            if how == "chat_other":
                others = [p for p in ev["recipients"] if p in res.pool]
                if len(others) == 1:
                    return {"method": "chat_member", "person": others[0], "candidates": others}, None
            if how == "text" and allow_text:
                raws = [ev["fields"].get(k) for k in ("name_raw_subject", "name_raw") if ev["fields"].get(k)]
                best = None
                for raw in raws:
                    r = res.by_name(raw)
                    if best is None or METHOD_RANK.get(r["method"], 7) < METHOD_RANK.get(best[0]["method"], 7):
                        best = (r, raw)
                if best:
                    return best
        return None, None

    first_pass: dict[str, tuple] = {}
    for ev in proc:
        r, raw = direct(ev, rule_by_event[ev["event_id"]])
        first_pass[ev["event_id"]] = (r, raw)
        if r and r.get("person") and r["method"] in HIGH_METHODS:
            res.anchors[r["person"]].append(ev)

    # ---- 2c final resolution in time order (thread inheritance, chat pairing, context)
    thread_subject: dict[str, str] = {}
    open_it: dict[str, list[tuple[str, str]]] = defaultdict(list)  # chatId -> [(person, event_id)]
    for ev in proc:
        rule = rule_by_event[ev["event_id"]]
        final, raw = None, None
        for how in rule.who:
            if how == "none":
                final = {"method": "unresolved", "person": None, "candidates": [], "note": "no name in record; linked by time/case in Phase 2"}
                break
            if how == "thread" and ev["thread_key"] in thread_subject and ev["source"] in ("mail", "teams_channel"):
                pid = thread_subject[ev["thread_key"]]
                final = {"method": "thread", "person": pid, "candidates": [pid]}
                break
            if how == "chat_pair":
                stack = open_it.get(ev["thread_key"], [])
                raw_name = ev["fields"].get("name_raw")
                if raw_name:
                    hit = [x for x in stack if res.reg.first_name(x[0]) == norm(raw_name).split(" ")[0]]
                    if hit:
                        final = {"method": "thread", "person": hit[-1][0], "candidates": [hit[-1][0]], "note": "matched the open IT request in the same chat", "linked_event_id": hit[-1][1]}
                        raw = raw_name
                        stack.remove(hit[-1])
                        break
                    continue
                if stack:
                    pid, linked = stack.pop()
                    final = {"method": "chat_pair", "person": pid, "candidates": [pid], "note": "no name: linked to the latest open IT request in the same chat", "linked_event_id": linked}
                    break
                final = {"method": "unresolved", "person": None, "candidates": [], "note": "no open IT request in this chat"}
                break
            if how in ("sender", "recipient", "chat_other", "text"):
                r, rr = first_pass[ev["event_id"]]
                if r is None:
                    continue
                if r["method"] == "needs_context":
                    r = {**res.by_context(r["candidates"], ev), **({"typo": True} if r.get("typo") else {})}
                final, raw = r, rr
                if final.get("person"):
                    break
        if final is None:
            final = {"method": "unresolved", "person": None, "candidates": []}
        if "linked_event_id" in final:
            ev["fields"]["linked_event_id"] = final.pop("linked_event_id")
        ev["resolution"] = finish_resolution(final, raw)
        ev["subject_person_id"] = final.get("person")
        if ev["subject_person_id"] and ev["thread_key"] and ev["thread_key"] not in thread_subject and ev["source"] in ("mail", "teams_channel"):
            thread_subject[ev["thread_key"]] = ev["subject_person_id"]
        if ev["activity"] == "it_requested" and ev["subject_person_id"]:
            open_it[ev["thread_key"]].append((ev["subject_person_id"], ev["event_id"]))

    # ---- 2d finalise person kinds
    onboarding_subjects = {ev["subject_person_id"] for ev in proc if ev["process"] == "onboarding" and ev["subject_person_id"]}
    recruit_people = set()
    for ev in events:
        if ev["category"] == "out_of_scope" and "recruitment" in (ev["noise_reason"] or ""):
            recruit_people.update([ev["actor_id"], *ev["recipients"]])
    for pid, p in reg.people.items():
        if p["kind"] != "unknown":
            continue
        has_work = any(e.endswith("@" + WORK_DOMAIN) for e in p["emails"]) or bool(p["teams_ids"])
        if pid in onboarding_subjects:
            p["kind"] = "new_starter"
        elif has_work:
            p["kind"] = "worker"
        elif pid in recruit_people:
            p["kind"] = "candidate"
    for p in reg.people.values():
        p["emails"].sort()
        p["teams_ids"].sort()

    with (OUT / "2_events_clean.jsonl").open("w", encoding="utf-8") as fh:
        for ev in events:
            fh.write(json.dumps(ev, sort_keys=True, ensure_ascii=False) + "\n")
    people_doc = {
        "step": "2_people",
        "coverage": "Data from 6 of 12 staff.",
        "people": [reg.people[k] for k in sorted(reg.people)],
        "orgs": [reg.orgs[k] for k in sorted(reg.orgs)],
    }
    write_json(OUT / "2_people.json", people_doc)
    return {"events": events, "registry": reg}


# --------------------------------------------------------------------------- phase 1 report


def skeleton(s: str) -> str:
    s = re.sub(r"\b[A-Z][\w'’\-]+\b", "X", s)
    s = re.sub(r"\d+", "9", s)
    s = re.sub(r"(X[ ,.]*)+", "X ", s)
    return re.sub(r"\s+", " ", s).strip()


def phase1_report(ingest: dict, clean: dict) -> dict:
    events, reg = clean["events"], clean["registry"]
    name = lambda pid: reg.people[pid]["display_name"] if pid else None  # noqa: E731
    by_src_cat: dict = defaultdict(Counter)
    for ev in events:
        by_src_cat[ev["source"]][ev["category"]] += 1
    act: dict = defaultdict(Counter)
    for ev in events:
        if ev["category"] == "process":
            act[ev["process"]][ev["activity"]] += 1
    allday = []
    for ev in events:
        if ev["source"] == "calendar" and ev["meta"].get("is_all_day"):
            allday.append({"subject": ev["title"], "date": ev["time_local"][:10], "mailbox": ev["mailbox"], "seen_in": ev["seen_in"], "category": ev["category"], "reason": ev["noise_reason"] or ev["activity"]})
    soft = []
    for ev in events:
        r = ev.get("resolution") or {}
        if r.get("method") in ("fuzzy", "context", "ambiguous", "chat_pair", "initial", "first_name_unique") or (r.get("method") == "unresolved" and r.get("raw_name")):
            soft.append({
                "event_id": ev["event_id"], "time_local": ev["time_local"][:16], "activity": ev["activity"], "process": ev["process"],
                "raw_name": r.get("raw_name"), "method": r["method"], "chosen": name(ev["subject_person_id"]),
                "candidates": [name(c) for c in r.get("candidates", [])], "filters": r.get("filters"), "note": r.get("note"),
                "text": (ev["title"] if ev["source"] in ("screen", "calendar") else ev["text"]).split("\n")[0][:110] if ev["source"] != "mail" else f'{ev["title"]} | {" ".join(ev["text"].split())[:80]}',
            })
    # unmatched mail / Teams / channel
    groups: dict = defaultdict(list)
    for ev in events:
        if ev["source"] in ("mail", "teams_chat", "teams_channel") and ev["noise_reason"] == "no rule matched":
            txt = " ".join(ev["text"].split())
            key = (ev["source"], skeleton(f'{ev["title"] or ""} | {txt}' if ev["source"] == "mail" else txt))
            groups[key].append(ev)
    unmatched = []
    for (src, sk), evs in sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        e = evs[0]
        unmatched.append({"source": src, "count": len(evs), "process_hint": bool(R.PROCESS_HINT.search(sk)), "example": (f'{e["title"]} | ' if e["title"] else "") + " ".join(e["text"].split())[:140], "event_ids": [x["event_id"] for x in evs][:3]})
    screen_unmatched = Counter(ev["title"] for ev in events if ev["source"] == "screen" and ev["noise_reason"] == "no rule matched")
    unresolved_named = [s for s in soft if s["method"] == "unresolved"]
    kinds = Counter(p["kind"] for p in reg.people.values())
    stages = {
        "raw": sum(ingest["raw_counts"].values()),
        "after_dedup": len(events),
        "noise": sum(1 for e in events if e["category"] == "noise"),
        "out_of_scope": sum(1 for e in events if e["category"] == "out_of_scope"),
        "context": sum(1 for e in events if e["category"] == "context"),
        "process": sum(1 for e in events if e["category"] == "process"),
    }
    report = {
        "stages": stages,
        "raw_by_source": ingest["raw_counts"],
        "dedup_by_source": ingest["dedup_counts"],
        "category_by_source": {s: dict(sorted(c.items())) for s, c in sorted(by_src_cat.items())},
        "activity_by_process": {p: dict(sorted(c.items(), key=lambda x: -x[1])) for p, c in sorted(act.items())},
        "all_day_calendar": allday,
        "soft_resolutions": soft,
        "unresolved_with_name": unresolved_named,
        "unmatched_text_top30": unmatched[:30],
        "unmatched_text_total": sum(len(v) for v in groups.values()),
        "screen_unmatched_titles": dict(screen_unmatched.most_common(15)),
        "people_by_kind": dict(sorted(kinds.items())),
        "date_warnings": [{"event_id": e["event_id"], "warnings": e["fields"]["warnings"]} for e in events if e["fields"].get("warnings")],
    }
    write_json(OUT / "pipeline_report.json", {"phase1": report})
    return report


def run_phase1() -> dict:
    ingest = step1_ingest()
    clean = step2_clean(ingest)
    return phase1_report(ingest, clean)


# --------------------------------------------------------------------------- CLI

STEPS = {"profile": step0_profile, "clean": run_phase1}


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
        elif name == "clean":
            print(json.dumps(result["stages"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
