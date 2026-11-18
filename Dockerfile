# Mission Control: one image, FastAPI serves the built React app at / and the API at /api.
# The raw export is NEVER in the image (.dockerignore excludes data/): mount it at /app/data at runtime
# (docker-compose.yml does). Without it the app still runs and Proof says "Raw data not available on this server".

# ---- 1. frontend build
FROM node:20.18-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---- 2. python runtime
FROM python:3.11-slim AS app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8000 \
    MC_DB_PATH=/var/lib/mission-control/feedback.db \
    MC_FEEDBACK_JSONL=/var/lib/mission-control/feedback.jsonl
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
# pipeline/, backend/, out/ (committed outputs); data/ is excluded by .dockerignore.
COPY . ./
COPY --from=web /web/dist ./frontend/dist
RUN mkdir -p /var/lib/mission-control /app/data && useradd --create-home --uid 1000 app \
    && chown -R app /var/lib/mission-control /app/out
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request,os; urllib.request.urlopen(f'http://127.0.0.1:{os.environ[\"PORT\"]}/api/health')"
CMD ["sh", "-c", "uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port ${PORT}"]
