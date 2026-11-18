"""/api/files/{name}: the pipeline output files in out/, read-only, allow-list only."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from app.store import Store, get_store

router = APIRouter(prefix="/api", tags=["files"])

# Only the committed pipeline outputs. Feedback has its own export; nothing else in out/ is served.
ALLOWED: dict[str, str] = {
    "0_profile.json": "application/json",
    "1_events.jsonl": "application/x-ndjson",
    "2_events_clean.jsonl": "application/x-ndjson",
    "2_people.json": "application/json",
    "2_screen_summary.json": "application/json",
    "3_cases.json": "application/json",
    "4_processes.json": "application/json",
    "5_flags.json": "application/json",
    "6_insights.json": "application/json",
    "pipeline_report.json": "application/json",
}


@router.get("/files/{name}", summary="One pipeline output file from out/ (allow-list only)", response_class=FileResponse)
def out_file(name: str, store: Annotated[Store, Depends(get_store)]) -> FileResponse:
    if name not in ALLOWED:
        raise HTTPException(404, f"not an out/ file: {name!r}. Allowed: {', '.join(sorted(ALLOWED))}")
    path = store.out_dir / name
    if not path.is_file():
        raise HTTPException(404, f"out/{name} has not been generated; run make pipeline")
    # inline so a browser shows it; the name is from the allow-list, so the header is safe
    return FileResponse(path, media_type=ALLOWED[name], headers={"Content-Disposition": f'inline; filename="{name}"'})
