#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
: "${LUSHORA_DATABASE_URL:?Set LUSHORA_DATABASE_URL to the production PostgreSQL URL}"
case "$LUSHORA_DATABASE_URL" in
  postgresql://*|postgresql+*)
    ;;
  *)
    echo "Refusing migration: production schema migrations require PostgreSQL." >&2
    exit 2
    ;;
esac
python -m alembic -c alembic.ini upgrade head
