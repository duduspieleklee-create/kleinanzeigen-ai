#!/usr/bin/env bash
# Dumps the production Postgres database to a gzip-compressed, timestamped
# file and prunes backups older than $RETENTION_DAYS. Intended to run from
# cron on the VPS — see "Automated backups" in docs/vps-deployment.md.
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP_DIR="${BACKUP_DIR:-$PROJECT_DIR/backups}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"
COMPOSE_FILE="$PROJECT_DIR/docker-compose.prod.yml"

# shellcheck disable=SC1090
source "$PROJECT_DIR/.env"

mkdir -p "$BACKUP_DIR"

timestamp="$(date +%F_%H%M%S)"
dest="$BACKUP_DIR/${POSTGRES_DB:-kleinanzeigen_ai}-$timestamp.sql.gz"
tmp="$dest.tmp"
trap 'rm -f "$tmp"' EXIT

docker compose -f "$COMPOSE_FILE" exec -T db \
  pg_dump -U "${POSTGRES_USER:-kleinanzeigen}" "${POSTGRES_DB:-kleinanzeigen_ai}" \
  | gzip > "$tmp"
mv "$tmp" "$dest"

find "$BACKUP_DIR" -name '*.sql.gz' -mtime "+$RETENTION_DAYS" -delete

echo "Backup written to $dest"
