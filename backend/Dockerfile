# syntax=docker/dockerfile:1.7
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

# System deps: libpq for psycopg, build-essential only at build time.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first (better Docker layer cache).
COPY pyproject.toml ./
RUN apt-get update && apt-get install -y --no-install-recommends gcc libpq-dev \
    && pip install --upgrade pip \
    && pip install -e ".[dev]" \
    && apt-get purge -y gcc libpq-dev \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

# Source is bind-mounted in docker-compose for dev hot-reload.
# For a real prod image, COPY ./ /app/ here and switch to a non-root user.

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
