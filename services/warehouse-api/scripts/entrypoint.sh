#!/bin/sh
set -eu

python scripts/wait_for_db.py
alembic upgrade head

if [ "${SEED_ON_START:-false}" = "true" ]; then
    python scripts/seed.py
fi

exec uvicorn main:app --host 0.0.0.0 --port 8000
