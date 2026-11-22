#!/usr/bin/env bash
set -euo pipefail
: "${LUSHORA_RESTORE_DATABASE_URL:?Set LUSHORA_RESTORE_DATABASE_URL to an isolated restore-test database}"
: "${BACKUP_FILE:?Set BACKUP_FILE to the backup dump to validate}"
if [ ! -f "$BACKUP_FILE" ]; then echo "Backup file not found: $BACKUP_FILE" >&2; exit 2; fi
pg_restore --list "$BACKUP_FILE" >/dev/null
restore_url="${LUSHORA_RESTORE_DATABASE_URL/postgresql+psycopg:/postgresql:}"
pg_restore --clean --if-exists --no-owner --no-acl --dbname "$restore_url" "$BACKUP_FILE"
psql "$restore_url" -v ON_ERROR_STOP=1 -c "SELECT version_num FROM alembic_version;"
for table in users providers bookings payments business_verifications; do
  psql "$restore_url" -v ON_ERROR_STOP=1 -c "SELECT '$table' AS table_name, count(*) AS row_count FROM $table;"
done
echo "Restore verification completed. Perform application smoke tests and compare row counts with the source database."
