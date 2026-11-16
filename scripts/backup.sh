#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p backups
stamp=$(date -u +%Y%m%dT%H%M%SZ)
docker compose exec -T db pg_dump -U estateai estateai | gzip > "backups/estateai-${stamp}.sql.gz"
find backups -type f -name 'estateai-*.sql.gz' -mtime +14 -delete
