# refer-backend — Fly.io image (plan.md M7).
# Includes LibreOffice (+ Korean l10n) for the experimental HWPX->HWP fallback.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy

# System deps: LibreOffice headless + Korean locale data, build tools for lxml.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libreoffice-core libreoffice-writer libreoffice-l10n-ko \
        build-essential libxml2-dev libxslt1-dev \
        git curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Dependency layer (cache-friendly).
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --extra format --extra agents --extra queue --no-install-project

# App source (+ vendored hwpx-skill submodule if present in the build context).
COPY backend/ ./

RUN uv sync --frozen --extra format --extra agents --extra queue

EXPOSE 8080
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
