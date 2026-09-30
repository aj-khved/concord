FROM python:3.11-slim

# Official uv static binaries -- no pip bootstrap needed.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /app

# Dependencies first, in their own layer: this only re-runs when
# pyproject.toml/uv.lock change, not on every source-code edit.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --locked --no-dev --no-install-project

COPY src/ src/
COPY migrations/ migrations/
COPY alembic.ini ./
RUN uv sync --locked --no-dev

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000

# Migrations run at container start, not at build time -- the database
# isn't reachable during `docker build`, and this also means a rolled-back
# image doesn't need a separate migration step.
CMD ["sh", "-c", "alembic upgrade head && uvicorn concord.api.app:app --host 0.0.0.0 --port 8000"]
