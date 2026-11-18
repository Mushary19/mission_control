"""Original export lines from data/, found through an event's raw_ref. Lines are returned unchanged."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import HTTPException

from app.config import ROOT
from app.schemas.event import RawLine, RawResponse
from app.store import Store


def resolve_raw_path(data_dir: Path, rel_file: str) -> Path:
    """Absolute path of a raw_ref file; 400 if it is outside data_dir, 503 if the export is missing."""
    if rel_file.startswith("data/"):
        path = (data_dir / rel_file[len("data/"):]).resolve()
    elif Path(rel_file).is_absolute():
        path = Path(rel_file)
    else:
        path = (ROOT / rel_file).resolve()
    if data_dir.resolve() not in path.parents:
        raise HTTPException(400, "raw_ref outside data/")
    if not path.exists():
        raise HTTPException(503, f"raw export not available on this server ({rel_file}); put the export in data/")
    return path


def read_raw(store: Store, event_id: str) -> RawResponse:
    """Every raw line behind one event (screen sessions: every frame)."""
    event = store.get_event(event_id)
    ref = event["raw_ref"]
    line_numbers = event.get("meta", {}).get("raw_lines") or [ref["line"]]
    content = resolve_raw_path(store.data_dir, ref["file"]).read_text(encoding="utf-8").split("\n")
    lines = [RawLine(file=ref["file"], line=n, raw=content[n - 1], record=json.loads(content[n - 1])) for n in line_numbers]
    return RawResponse(event_id=event_id, source=event["source"], line_count=len(lines), lines=lines)
