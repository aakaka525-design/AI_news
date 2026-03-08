#!/bin/bash
# PostgreSQL backup script for AI News
# Usage: ./scripts/backup.sh
# Add to crontab: 0 3 * * * /path/to/scripts/backup.sh

set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-./backups}"
RETENTION_DAYS="${RETENTION_DAYS:-7}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/ainews_${TIMESTAMP}.sql.gz"

mkdir -p "$BACKUP_DIR"

echo "[$(date)] Starting backup..."

docker exec ainews_postgres pg_dump -U ainews ainews | gzip > "$BACKUP_FILE"

echo "[$(date)] Backup saved to: $BACKUP_FILE ($(du -h "$BACKUP_FILE" | cut -f1))"

# Clean old backups
find "$BACKUP_DIR" -name "ainews_*.sql.gz" -mtime +"$RETENTION_DAYS" -delete
echo "[$(date)] Cleaned backups older than $RETENTION_DAYS days"
