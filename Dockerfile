# Multi-arch: docker buildx build --platform linux/arm64,linux/amd64 -t job-scraper .
# Stage 1: build the dashboard (React) to static files.
FROM node:22-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

# Stage 2: the Python app, which also serves web/dist.
FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:0.13.4 /uv /bin/uv
ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PATH="/app/.venv/bin:$PATH" \
    TZ=Asia/Kolkata

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY alembic.ini ./
COPY migrations ./migrations
COPY config ./config
COPY scripts ./scripts
COPY app ./app
COPY --from=web /web/dist ./web/dist

RUN useradd --uid 1000 --create-home app && mkdir -p /app/data /app/backups \
    && chown app:app /app/data /app/backups
USER app
