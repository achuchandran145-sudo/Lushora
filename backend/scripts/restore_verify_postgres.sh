#!/usr/bin/env bash
set -euo pipefail
: "${LUSHORA_RESTORE_DATABASE_URL:?Set LUSHORA_RESTORE_DATABASE_URL to an isolated restore-test database}"
: "${BACKUP_FILE:?Set BACKUP_FILE to the backup dump to validate}"
if [ ! -f "$BACKUP_FILE" ]; then echo "Backup file not found: $BACKUP_FILE" >&2; exit 2; fi
pg_restore --list "$BACKUP_FILE" >/dev/null
pg_restore --clean --if-exists --no-owner --no-acl --dbname "$LUSHORA_RESTORE_DATABASE_URL" "$BACKUP_FILE"
psql "$LUSHORA_RESTORE_DATABASE_URL" -v ON_ERROR_STOP=1 -c "SELECT count(*) FROM alembic_version;"
echo "Restore verification completed. Confirm application queries and critical row counts separately."
