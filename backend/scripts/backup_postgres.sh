#!/usr/bin/env bash
set -euo pipefail
: "${LUSHORA_DATABASE_URL:?Set LUSHORA_DATABASE_URL}"
: "${LUSHORA_BACKUP_DIR:?Set LUSHORA_BACKUP_DIR to a private backup location}"
: "${LUSHORA_BACKUP_RETENTION_DAYS:?Set LUSHORA_BACKUP_RETENTION_DAYS (minimum 7)}"
if ! [[ "$LUSHORA_BACKUP_RETENTION_DAYS" =~ ^[0-9]+$ ]] || [ "$LUSHORA_BACKUP_RETENTION_DAYS" -lt 7 ]; then
  echo "Backup retention must be at least 7 days." >&2; exit 2
fi
mkdir -p "$LUSHORA_BACKUP_DIR"
chmod 700 "$LUSHORA_BACKUP_DIR"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
file="$LUSHORA_BACKUP_DIR/lushora-$stamp.dump"
pg_url="${LUSHORA_DATABASE_URL/postgresql+psycopg:/postgresql:}"
pg_dump --format=custom --no-owner --no-acl "$pg_url" > "$file"
chmod 600 "$file"
sha256sum "$file" > "$file.sha256"
find "$LUSHORA_BACKUP_DIR" -type f -name 'lushora-*.dump' -mtime +"$LUSHORA_BACKUP_RETENTION_DAYS" -delete
find "$LUSHORA_BACKUP_DIR" -type f -name 'lushora-*.dump.sha256' -mtime +"$LUSHORA_BACKUP_RETENTION_DAYS" -delete
echo "Backup created: $file"
