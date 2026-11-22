#!/usr/bin/env bash
set -euo pipefail
: "${LUSHORA_DATABASE_URL:?Set LUSHORA_DATABASE_URL}"
: "${LUSHORA_BACKUP_DIR:?Set LUSHORA_BACKUP_DIR to a private backup location}"
mkdir -p "$LUSHORA_BACKUP_DIR"
chmod 700 "$LUSHORA_BACKUP_DIR"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
file="$LUSHORA_BACKUP_DIR/lushora-$stamp.dump"
pg_dump --format=custom --no-owner --no-acl "$LUSHORA_DATABASE_URL" > "$file"
chmod 600 "$file"
sha256sum "$file" > "$file.sha256"
echo "Backup created: $file"
