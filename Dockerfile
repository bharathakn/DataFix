# DataFix: API + built UI in one container (also fine as API-only behind a Vercel frontend).
#   docker build -t datafix . && docker run -p 8000:8000 --env-file .env datafix
# Stage 1: build the UI so the container can serve it too (VITE_API_URL empty = same origin).
FROM node:22-slim AS ui
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# Stage 2: Python API (uv, locked dependencies, no dev tools).
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.9 /uv /usr/local/bin/uv
ENV PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH" \
    DATAFIX_PUBLIC=1 DATAFIX_SESSION_DIR=/tmp/datafix-sessions DATAFIX_SESSION_TTL_H=24 DATAFIX_MAX_UPLOAD_MB=50
WORKDIR /app/backend
COPY backend/pyproject.toml backend/uv.lock backend/README.md ./
COPY backend/src ./src
RUN uv sync --frozen --no-dev
COPY backend/ ./
COPY data/demo_small/customers_dirty.csv data/demo_small/orders.csv /app/data/demo_small/
COPY data/reference/pincodes.csv /app/data/reference/
COPY --from=ui /app/frontend/dist /app/frontend/dist
RUN useradd --create-home datafix && mkdir -p /tmp/datafix-sessions && chown datafix /tmp/datafix-sessions
USER datafix
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s CMD python -c "import urllib.request,os;urllib.request.urlopen(f'http://127.0.0.1:{os.getenv(\"PORT\",\"8000\")}/api/health')"
# ONE worker on purpose: sessions live in this process's memory (plus pickles on disk).
CMD ["sh", "-c", "uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1 --timeout-keep-alive 75"]
