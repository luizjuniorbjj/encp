#!/bin/bash
# ENCP Services - Database Backup Script
# Usage: ./scripts/backup_db.sh
# Cron: 0 3 * * * cd /app && ./scripts/backup_db.sh
#
# Environment variables:
#   DATABASE_URL - PostgreSQL connection URL
#   BACKUP_DIR  - Where to store backups (default: ./backups)
#   KEEP_DAYS   - How many days to keep backups (default: 7)

set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-./backups}"
KEEP_DAYS="${KEEP_DAYS:-7}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/encp_backup_${TIMESTAMP}.sql.gz"

# Parse DATABASE_URL
if [ -z "${DATABASE_URL:-}" ]; then
    echo "[ERROR] DATABASE_URL not set"
    exit 1
fi

# Create backup directory
mkdir -p "$BACKUP_DIR"

echo "[BACKUP] Starting backup at $(date)"
echo "[BACKUP] Target: $BACKUP_FILE"

# Run pg_dump and compress
pg_dump "$DATABASE_URL" --no-owner --no-acl | gzip > "$BACKUP_FILE"

# Check if backup was created
if [ -f "$BACKUP_FILE" ]; then
    SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
    echo "[BACKUP] Success: $BACKUP_FILE ($SIZE)"
else
    echo "[ERROR] Backup file not created"
    exit 1
fi

# Clean up old backups
if [ "$KEEP_DAYS" -gt 0 ]; then
    DELETED=$(find "$BACKUP_DIR" -name "encp_backup_*.sql.gz" -mtime +$KEEP_DAYS -delete -print | wc -l)
    if [ "$DELETED" -gt 0 ]; then
        echo "[BACKUP] Cleaned up $DELETED old backup(s)"
    fi
fi

echo "[BACKUP] Done at $(date)"
