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
