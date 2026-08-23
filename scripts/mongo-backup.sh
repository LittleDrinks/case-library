#!/bin/sh
set -eu

project_dir="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
backup_dir="${1:-$project_dir/backups}"
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
bundle="$backup_dir/case-library-$timestamp-$$.bundle.tar.gz.age"
partial="$bundle.part"
app_running=false

compose() {
  docker compose --project-directory "$project_dir" "$@"
}

cleanup() {
  resume_app || true
  rm -f -- "$partial"
}

resume_app() {
  if [ "$app_running" = true ]; then
    compose start --wait app >/dev/null
    app_running=false
  fi
}

git_sha() {
  compose --profile ops run --rm --no-deps -T \
    -v "$project_dir/.git:/source.git:ro" git-tools --git-dir=/source.git rev-parse HEAD
}

git_dirty() {
  if git -C "$project_dir" status --porcelain | grep -q .; then
    printf true
  else
    printf false
  fi
}

app_image_id() {
  compose images -q app | head -n 1
}

umask 077
mkdir -p -- "$backup_dir"
trap cleanup EXIT INT TERM
compose --profile ops --profile restore build backup-tools restore-tools >&2
compose up -d --wait mongo-init minio
sha="$(git_sha)"
dirty="$(git_dirty)"
image_id="$(app_image_id)"
if [ -n "$(compose ps --status running -q app)" ]; then
  app_running=true
  compose stop app >/dev/null
fi
compose --profile ops run --rm --no-deps -T -e BUNDLE_GIT_SHA="$sha" \
  -e BUNDLE_GIT_DIRTY="$dirty" -e BUNDLE_APP_IMAGE_ID="$image_id" \
  backup-tools create >"$partial"
test -s "$partial"
compose --profile restore run --rm --no-deps -T \
  -v "$partial:/bundle:ro" restore-tools verify /bundle >/dev/null
resume_app
mv -- "$partial" "$bundle"
trap - EXIT INT TERM
printf '%s\n' "$bundle"
