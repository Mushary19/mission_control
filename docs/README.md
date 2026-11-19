# Documentation

Where each deliverable of the brief lives.

| # | deliverable | where | what you will find |
|---|---|---|---|
| 1 | **Prototype** | [README → Quick start](../README.md#quick-start) | Run it with `make install start`, `docker compose up` or `make dev`; open http://localhost:8000. Findings, design decisions and limits are in the [README](../README.md). |
| 2 | **Architecture** | [architecture.md](architecture.md) | Five diagrams (system, pipeline, runtime, feedback loop, data model), one message followed from raw line to feedback row, design decisions, tech stack. |
| 3 | **Schemas & outputs** | [schemas.md](schemas.md) · [`out/`](../out/) · [`out/samples/`](../out/samples/) | For every pipeline step: input, output file, fields, a real example and the rules; ID conventions. `out/` holds the full outputs, `out/samples/` the first 5 records of each, pretty-printed. |

Also here:

* [demo-script.md](demo-script.md): interview walkthrough (5 minutes).
* [screenshots/](screenshots/): every screen at 1440px, and at 1024px in [screenshots/1024/](screenshots/1024/).
* API reference: `/docs` (OpenAPI) when the app runs.

Generated files (re-run after `make pipeline`):

| file | made by |
|---|---|
| `docs/schemas.md` | `.venv/bin/python scripts/gen_schemas.py` |
| `out/samples/*.sample.json` | `.venv/bin/python scripts/make_samples.py` |
| `docs/screenshots/*.png` | `make screenshots` (needs `make dev` running) |
