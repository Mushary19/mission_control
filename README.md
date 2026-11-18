# Mission Control

Process-intelligence prototype (work in progress; full README in Phase 6).

## Notes

- **Data is not committed.** Put the raw export in `data/` at the repo root
  (`data/_shared/...`, `data/<person>/...`). `data/` is git-ignored and never modified by the pipeline.
- Pipeline outputs in `out/` are committed.
- Python 3.10+.

```
python3 pipeline/pipeline.py
```

### API

```
pip install -r requirements.txt
uvicorn app.main:app --app-dir backend --reload     # API at http://127.0.0.1:8000/api, docs at /docs
pytest                                             # pipeline + backend tests (incl. API snapshots)
ruff check backend
```

Settings (env, with defaults): `MC_OUT_DIR` (`out/`), `MC_DATA_DIR` (`data/`), `MC_DB` (`backend/feedback.db`),
`MC_FEEDBACK_JSONL` (`out/feedback.jsonl`), `MC_CORS` (comma-separated origins). See `backend/app/config.py`.

Backend layout: `app/main.py` (app + routers), `app/routers/` (thin HTTP layer), `app/services/` (logic),
`app/schemas/` (Pydantic models), `app/store.py` (out/ loaded once at startup), `app/db.py` (SQLite feedback).
After an intended API change, refresh the snapshots with `python backend/tests/test_snapshots.py`.
