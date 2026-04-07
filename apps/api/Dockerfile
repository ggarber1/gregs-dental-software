# ── Builder ───────────────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

# Install uv
COPY --from=ghcr.io/astral-sh/uv:0.5.18 /uv /usr/local/bin/uv

WORKDIR /app

# Copy dependency manifests first for layer caching
COPY pyproject.toml .
COPY uv.lock* .

# Install dependencies into a virtual environment
# --frozen: fail if lockfile is out of sync (ensures reproducibility)
RUN uv sync --frozen --no-dev --no-install-project

# ── Runtime ───────────────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

# Non-root user for security
RUN groupadd -r app && useradd -r -g app app

WORKDIR /app

# Copy venv from builder
COPY --from=builder /app/.venv /app/.venv

# Copy application source and migration files
COPY app/ app/
COPY alembic/ alembic/
COPY alembic.ini .

# Set PATH so venv binaries take precedence
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

USER app

EXPOSE 8000

# Crash-only: uvicorn will restart via ECS on failure; no entrypoint wrapper
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
