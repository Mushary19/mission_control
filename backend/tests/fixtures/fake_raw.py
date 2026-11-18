"""A tiny FAKE raw export (invented people, test.example domains) for the raw-record endpoint.

fixtures/data/ mirrors the real export layout with one made-up record per source (screen: two frames of one
session). build_out() copies the committed out/ files to a temp folder and appends one clean event per fake
record, so /api/events/{id}/raw can be tested without the real data/.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
FAKE_DATA = HERE / "data"
ROOT = HERE.parents[2]

# event_id -> (source, raw file under data/, raw lines)
FAKE_EVENTS: dict[str, tuple[str, str, list[int]]] = {
    "mail:fake-0001@test.example": ("mail", "data/test/outlook/messages.jsonl", [1]),
    "calendar:FAKE-ICAL-0001": ("calendar", "data/test/outlook/calendar.jsonl", [1]),
    "teams_chat:19:fake-sam_fake-it@unq.gbl.spaces:1000000000001": ("teams_chat", "data/test/teams/messages.jsonl", [1]),
    "teams_channel:1000000000002": ("teams_channel", "data/_shared/teams_channel/messages.jsonl", [1]),
    "screen:test:1": ("screen", "data/test/screens/screen_log.jsonl", [1, 2]),
}


def build_out(tmp: Path) -> Path:
    """out/ copy + the fake events; returns the new out dir."""
    out = tmp / "out"
    out.mkdir(parents=True, exist_ok=True)
    for f in (ROOT / "out").iterdir():
        if f.suffix in (".json", ".jsonl") and f.name != "feedback.jsonl":
            shutil.copy(f, out / f.name)
    with (out / "2_events_clean.jsonl").open("a", encoding="utf-8") as fh:
        for eid, (source, file, lines) in FAKE_EVENTS.items():
            ev = {"event_id": eid, "source": source, "mailbox": "test", "time_utc": "2026-03-10T04:30:00Z",
                  "time_local": "2026-03-10T10:00:00+05:30", "category": "context", "raw_ref": {"file": file, "line": lines[0]},
                  "meta": {"raw_lines": lines} if len(lines) > 1 else {}}
            fh.write(json.dumps(ev) + "\n")
    return out
