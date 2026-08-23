#!/bin/sh
set -eu

project_dir="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
backup_dir="$project_dir/backups"
bundle="${1:-}"
restore_bucket="case-library-restore-$(date -u +%Y%m%d%H%M%S)-$$"
cd "$project_dir"

compose() {
  docker compose --project-directory "$project_dir" "$@"
}

latest_bundle() {
  latest=""
  for candidate in "$backup_dir"/*.bundle.tar.gz.age; do
    if [ -f "$candidate" ]; then latest="$candidate"; fi
  done
  test -n "$latest"
  printf '%s\n' "$latest"
}

cleanup() {
  compose --profile restore run --rm --no-deps -T \
    restore-tools remove-bucket "$restore_bucket" >/dev/null 2>&1 || true
  compose --profile restore rm -sfv restore-mongo >/dev/null 2>&1 || true
}

if [ -z "$bundle" ]; then bundle="$(latest_bundle)"; fi
test -f "$bundle"
compose --profile restore build restore-tools
compose up -d --wait minio
trap cleanup EXIT INT TERM
compose --profile restore up -d --wait restore-mongo
compose --profile restore run --rm --no-deps -T -e RESTORE_BUCKET="$restore_bucket" \
  -v "$bundle:/bundle:ro" restore-tools restore /bundle
