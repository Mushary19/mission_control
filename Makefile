# Mission Control. Needs Python 3.10+ and Node 20+. The raw export goes in data/ (not committed).
PY      ?= .venv/bin/python
API_PORT ?= 8000
WEB_PORT ?= 5173

.PHONY: install pipeline dev build test lint start screenshots clean up down docker-pipeline

install:            ## Python venv + backend/test deps, frontend deps
	python3 -m venv .venv
	$(PY) -m pip install -q --upgrade pip
	$(PY) -m pip install -q -r requirements-dev.txt
	cd frontend && npm ci --no-audit --no-fund

pipeline:           ## data/ -> out/ (steps 0-6). Deterministic: same input, same output
	$(PY) pipeline/pipeline.py

dev:                ## API on :$(API_PORT) (reload) + Vite on :$(WEB_PORT) (proxies /api). Ctrl+C stops both
	@trap 'kill 0' INT TERM EXIT; \
	$(PY) -m uvicorn app.main:app --app-dir backend --reload --port $(API_PORT) & \
	cd frontend && MC_API=http://127.0.0.1:$(API_PORT) npx vite --port $(WEB_PORT) & \
	wait

build:              ## frontend/dist (type-checked)
	cd frontend && npm run build

test:               ## pipeline + API tests, lint
	$(PY) -m pytest -q
	$(PY) -m ruff check pipeline backend

lint:
	$(PY) -m ruff check pipeline backend

start: build        ## production: FastAPI serves the built UI at / and the API at /api
	$(PY) -m uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port $(API_PORT)

up:                 ## Docker: build + start the app on http://localhost:8000 (data/ mounted read-only)
	mkdir -p data
	docker compose up -d --build
	@echo "Mission Control: http://localhost:8000"

down:               ## Docker: stop (feedback volume kept; add -v to drop it)
	docker compose down

docker-pipeline:    ## Docker: rebuild out/ from data/ inside the image
	mkdir -p data
	docker compose --profile pipeline run --rm pipeline

screenshots:        ## needs `make dev` running and Chrome at /usr/bin/google-chrome
	cd frontend && BASE=http://localhost:$(WEB_PORT) npm run screenshots

clean:
	rm -rf frontend/dist .pytest_cache .ruff_cache
