#!/bin/bash
set -e

echo "==> Running database migrations..."
python -m alembic upgrade head

echo "==> Starting API server..."
exec python run.py api
