#!/bin/sh
set -eu

project_dir="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
project="${FAILOVER_PROJECT_NAME:-case-library-v2-failover}"
default_project=case-library-v2
before=""

test "$project" != "$default_project"
export COMPOSE_PROJECT_NAME="$project"
export COMPOSE_FILE="$project_dir/docker-compose.yml:$project_dir/deploy/failover.compose.yml"
export COMPOSE_ENV_FILES="$project_dir/.env.example"
export COMPOSE_DISABLE_ENV_FILE=1
export MONGODB_DB_NAME=case_library_failover
export OBJECT_STORE_BUCKET=case-library-failover

compose() {
  docker compose --project-directory "$project_dir" "$@"
}

default_container() {
  docker ps --filter "label=com.docker.compose.project=$default_project" \
    --filter "label=com.docker.compose.service=$1" --format '{{.ID}}' | head -n 1
}

default_health() {
  app="$(default_container app)"
  test -n "$app" || { printf absent; return; }
  docker exec "$app" python -c \
    "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8001/health/ready', timeout=3).status)"
}

default_data_hash() {
  mongo="$(default_container mongo1)"
  test -n "$mongo" || { printf absent; return; }
  docker exec "$mongo" mongosh --quiet --eval '
    const d = db.getSiblingDB("case_library_v3");
    const transient = new Set([
      "sessions", "ai_usage", "search_outbox", "search_revocations",
      "search_catalog_state", "search_control", "search_catalog_generation",
      "search_worker_state",
    ]);
    const names = d.getCollectionNames().filter(name => !transient.has(name)).sort();
    print(d.runCommand({dbHash: 1, collections: names}).md5);
  ' | tail -n 1
}

default_snapshot() {
  printf '%s:%s\n' "$(default_health)" "$(default_data_hash)"
}

require_default_stack() {
  health="$(default_health)"
  hash="$(default_data_hash)"
  test "$health" = 200
  echo "$hash" | grep -Eq '^[0-9a-f]{32}$'
}

verify_failover_resources_absent() {
  containers="$(docker ps -aq --filter "label=com.docker.compose.project=$project")" || return $?
  volumes="$(docker volume ls -q --filter "label=com.docker.compose.project=$project")" || return $?
  networks="$(docker network ls -q --filter "label=com.docker.compose.project=$project")" || return $?
  test -z "$containers$volumes$networks"
}

cleanup_resources() {
  cleanup_status=0
  compose --profile ops --profile restore down --volumes --remove-orphans >/dev/null 2>&1 || cleanup_status=1
  verify_failover_resources_absent || cleanup_status=1
  return "$cleanup_status"
}

cleanup() {
  original_status=$?
  trap - EXIT INT TERM
  cleanup_status=0
  cleanup_resources || cleanup_status=$?
  test "$original_status" -eq 0 || exit "$original_status"
  exit "$cleanup_status"
}

run_drill() {
  require_default_stack
  before="$(default_snapshot)"
  trap cleanup EXIT
  trap 'exit 130' INT
  trap 'exit 143' TERM
  compose up --build -d --wait mongo-init minio app
  sh "$project_dir/tests/failover/mongo-election.sh"
  sh "$project_dir/tests/failover/backup-restore.sh"
  cleanup_resources
  trap - EXIT INT TERM
  after="$(default_snapshot)"
  test "$after" = "$before"
  printf 'default_stack=%s failover_project=%s\n' "$after" "$project"
}

case "${1:-run}" in
  config) compose --profile ops --profile restore config ;;
  run) run_drill ;;
  *) echo "Usage: $0 [run|config]" >&2; exit 2 ;;
esac
