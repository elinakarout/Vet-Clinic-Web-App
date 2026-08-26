#!/bin/sh
# Container entrypoint for the api service. (Phase 9)
#
# Phase 9's QA pass found the compose stack came up healthy on /health and then
# 500'd every real request with "no such table: users". The cause was never a
# code bug: /app/data is a named volume (api-data), so the database inside the
# container is a different file from api/data/dev.db on the host, and nothing
# had ever run a migration against it. `docker compose up` looked like it
# worked, which is what made it cost an afternoon.
#
# Migrations run on every start because `alembic upgrade head` is a no-op when
# the database is already current -- cheap insurance against the same silence.
set -e

echo "[start] applying database migrations..."
alembic upgrade head

# Seeding is deliberately opt-in: demo accounts with published passwords must
# never appear in a deployment just because someone set SEED_ON_START.
if [ "${SEED_ON_START:-0}" = "1" ]; then
  echo "[start] seeding demo data (SEED_ON_START=1)..."
  python scripts/seed.py
fi

echo "[start] launching uvicorn on :8000"
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
