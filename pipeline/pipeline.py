"""Mission Control pipeline.

Run:  python pipeline/pipeline.py            (all implemented steps)
      python pipeline/pipeline.py profile    (one step)

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


# --------------------------------------------------------------------------- CLI

STEPS = {"profile": step0_profile}


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
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
