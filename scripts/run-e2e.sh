#!/bin/sh
set -eu

project_dir="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
compose_project="case-library-v2"
e2e_meili_volume="${compose_project}_e2e_meili_data"
e2e_network="${compose_project}_e2e_test"
database="case_library_e2e"
e2e_services="e2e backend-e2e e2e-frontend e2e-app e2e-ai-provider e2e-search-worker e2e-search-init e2e-meilisearch"
cd "$project_dir"
. "$project_dir/scripts/test-database.sh"

test "$#" -le 1 || {
  echo "Usage: scripts/run-e2e.sh [frontend/tests/e2e/<name>.spec.js]" >&2
  exit 2
}
requested_spec="${1:-}"
artifact_dir="${E2E_ARTIFACT_DIR:-$project_dir/test-results/e2e}"
mkdir -p "$artifact_dir"

resolve_spec() {
  case "$1" in
    frontend/tests/e2e/*.spec.js) spec="${1#frontend/}" ;;
    tests/e2e/*.spec.js) spec="$1" ;;
    *.spec.js) spec="tests/e2e/$1" ;;
    *) echo "E2E spec must be a Playwright .spec.js file" >&2; return 2 ;;
  esac
  test -f "$project_dir/frontend/$spec" || {
    echo "E2E spec not found: $1" >&2
    return 2
  }
  printf '%s\n' "$spec"
}

browser_spec=""
test -z "$requested_spec" || browser_spec="$(resolve_spec "$requested_spec")"

compose() {
  docker compose --project-name "$compose_project" \
    --env-file "$project_dir/.env.example" "$@"
}

clear_e2e_bucket() {
  compose --profile e2e run --rm --no-deps backend-e2e python tests/clear_e2e_bucket.py
}

rebuild_search() {
  compose --profile e2e run --rm --no-deps e2e-search-init
}

verify_test_database_absent() {
  validate_test_database "$database"
  query="print(db.getMongo().getDBNames().includes('$database'))"
  uri='mongodb://mongo1:27017,mongo2:27017,mongo3:27017/?replicaSet=rs0'
  exists="$(compose exec -T mongo1 mongosh "$uri" --quiet --eval "$query")"
  test "$exists" = "false"
}

drop_and_verify_database() {
  drop_test_database "$database"
  verify_test_database_absent
}

stop_e2e_runtime() {
  compose --profile e2e stop e2e-frontend e2e-app e2e-search-worker
}

remove_e2e_services() {
  compose --profile e2e rm -sf $e2e_services >/dev/null
}

remove_e2e_volume() {
  volumes="$(docker volume ls -q --filter "name=^${e2e_meili_volume}$")" || return 1
  test -z "$volumes" && return 0
  docker volume rm "$e2e_meili_volume" >/dev/null
}

remove_e2e_network() {
  networks="$(docker network ls -q --filter "name=^${e2e_network}$")" || return 1
  test -z "$networks" && return 0
  docker network rm "$e2e_network" >/dev/null
}

verify_e2e_resources_absent() {
  containers="$(compose --profile e2e ps -aq $e2e_services)" || return 1
  volumes="$(docker volume ls -q --filter "name=^${e2e_meili_volume}$")" || return 1
  networks="$(docker network ls -q --filter "name=^${e2e_network}$")" || return 1
  test -z "$containers$volumes$networks"
}

preclean_e2e_resources() {
  remove_e2e_services
  remove_e2e_volume
  remove_e2e_network
  verify_e2e_resources_absent
}

reset_browser_state() {
  compose --profile e2e stop e2e-frontend e2e-app e2e-search-worker
  clear_e2e_bucket
  drop_test_database "$database"
  rebuild_search
  compose --profile e2e up -d --force-recreate --no-deps e2e-search-worker
  compose --profile e2e up -d --force-recreate --no-deps --wait e2e-app
  compose --profile e2e up -d --force-recreate --no-deps --wait e2e-frontend
}

run_browser_tests() {
  set -- compose --profile e2e run --rm --no-deps \
    -v "$artifact_dir:/app/test-results" e2e
  test -z "$browser_spec" || set -- "$@" npm run test:e2e -- "$browser_spec"
  "$@"
}

cleanup() {
  original_status=$?
  trap - EXIT INT TERM
  cleanup_status=0
  stop_e2e_runtime || cleanup_status=1
  clear_e2e_bucket || cleanup_status=1
  drop_and_verify_database || cleanup_status=1
  remove_e2e_services || cleanup_status=1
  remove_e2e_volume || cleanup_status=1
  remove_e2e_network || cleanup_status=1
  verify_e2e_resources_absent || cleanup_status=1
  test "$original_status" -ne 0 && exit "$original_status"
  exit "$cleanup_status"
}

trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
preclean_e2e_resources
compose up -d --wait mongo-init
drop_and_verify_database
compose build e2e-app e2e-frontend backend-e2e e2e-ai-provider e2e-meilisearch
docker build -f deploy/e2e.Dockerfile -t case-library-v2-e2e:latest .
compose --profile e2e up -d --wait e2e-frontend
clear_e2e_bucket
test -n "$browser_spec" || compose --profile e2e run --rm --no-deps backend-e2e
reset_browser_state
run_browser_tests
