"""Writes out/samples/<name>.sample.json: a small, pretty-printed sample of every pipeline output in out/.

JSONL files: the first 5 records. JSON files: the same structure, with every list of records (objects or rows)
cut to its first 5 items and every large mapping (over 20 keys) cut to its first 5 keys, also inside nested
objects. Lists of plain values (ids, column names) are kept whole. A "_sample" note gives the full sizes.
Re-run after `make pipeline` so the samples stay in sync:  .venv/bin/python scripts/make_samples.py
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "out"
SAMPLES = OUT / "samples"
N = 5
BIG_MAPPING = 20


def cut(obj: Any, path: str, notes: dict[str, int]) -> Any:
    """Copy of obj with record lists and large mappings shortened; notes[path] = largest full size seen there."""
    if isinstance(obj, list):
        records = any(isinstance(x, (dict, list)) for x in obj)
        if records and len(obj) > N:
            notes[path or "."] = max(notes.get(path or ".", 0), len(obj))
            obj = obj[:N]
        return [cut(x, f"{path}[]", notes) for x in obj]
    if isinstance(obj, dict):
        items = list(obj.items())
        if len(items) > BIG_MAPPING:
            notes[f"{path} (keys)"] = max(notes.get(f"{path} (keys)", 0), len(items))
            items = items[:N]
        return {k: cut(v, f"{path}.{k}" if path else k, notes) for k, v in items}
    return obj


def sample(src: Path) -> dict[str, Any]:
    """The sample document for one out/ file."""
    if src.suffix == ".jsonl":
        with src.open(encoding="utf-8") as fh:
            lines = fh.readlines()
        return {
            "_sample": f"first {N} of {len(lines)} records in out/{src.name} (one JSON object per line there)",
            "records": [json.loads(line) for line in lines[:N]],
        }
    notes: dict[str, int] = {}
    body = cut(json.loads(src.read_text(encoding="utf-8")), "", notes)
    lists = ", ".join(f"{k} ({v})" for k, v in notes.items()) or "none"
    return {"_sample": f"out/{src.name}, lists of records and large mappings cut to {N} entries; full sizes (largest): {lists}", **body}


def main() -> None:
    SAMPLES.mkdir(exist_ok=True)
    for src in sorted(OUT.glob("*.json*")):
        if src.name == "feedback.jsonl":  # runtime file, not a pipeline output
            continue
        dest = SAMPLES / f"{src.name.split('.')[0]}.sample.json"
        dest.write_text(json.dumps(sample(src), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"wrote {dest.relative_to(ROOT)} ({dest.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
