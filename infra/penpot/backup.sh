#!/usr/bin/env bash
set -euo pipefail
umask 077
cd "$(dirname "$0")"

backup_dir=".local/backups/$(date +%Y%m%d-%H%M%S)"
mkdir -p "$backup_dir"
compose=(docker compose --env-file .env -f compose.yaml)

# 暂停写入，使数据库和附件属于同一备份时间点。
trap '"${compose[@]}" up -d' EXIT
"${compose[@]}" stop penpot-frontend penpot-backend penpot-admin-console penpot-exporter
"${compose[@]}" exec -T penpot-postgres pg_dump -U penpot -d penpot -Fc > "$backup_dir/database.dump"
"${compose[@]}" run --rm --no-deps -T --entrypoint tar penpot-backend -C /opt/data/assets -czf - . > "$backup_dir/assets.tar.gz"
cp .env compose.yaml "$backup_dir/"
"${compose[@]}" exec -T penpot-postgres pg_restore --list < "$backup_dir/database.dump" > "$backup_dir/database-contents.txt"
tar -tzf "$backup_dir/assets.tar.gz" > "$backup_dir/assets-contents.txt"
printf '备份完成：%s/%s\n' "$PWD" "$backup_dir"
