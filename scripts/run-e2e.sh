#!/bin/sh
set -eu

project_dir="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
# Every E2E run owns an isolated Compose project (deploy/e2e.compose.yml):
# its own mongodb replica set, minio, meilisearch, auto-allocated networks
# and image tags. The project name is the checkout directory plus a short
# hash of the checkout path, so two checkouts never collide and two runs from
# the same checkout are serialized by an exclusive lock instead of tearing
# down each other's resources. The demo stack keeps the name case-library-v2
# from docker-compose.yml and is never touched.
dir_slug="$(printf '%s' "$(basename "$project_dir")" | sed 's/^[.]//' | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9_-]/-/g')"
test -n "$dir_slug" || dir_slug="checkout"
dir_hash="$(printf '%s' "$(CDPATH= cd -- "$project_dir" && pwd -P)" | sha256sum | cut -c1-8)"
compose_project="case-library-e2e-${dir_slug}-${dir_hash}"
export COMPOSE_PROJECT_NAME="$compose_project"
export IMAGE_PREFIX="$compose_project"
export COMPOSE_FILE="${COMPOSE_FILE:-$project_dir/docker-compose.yml}:$project_dir/deploy/e2e.compose.yml"
lock_file="/tmp/case-library-e2e-${dir_slug}-${dir_hash}.lock"
database="case_library_e2e"
e2e_services="e2e backend-e2e e2e-frontend e2e-app e2e-ai-provider e2e-search-worker e2e-search-init e2e-meilisearch agent-e2e agent-e2e-app agent-e2e-loser agent-e2e-frontend agent-e2e-gateway agent-tracer agent-tracer-app agent-tracer-frontend agent-tracer-gateway"
cd "$project_dir"
. "$project_dir/scripts/test-database.sh"

suite=browser
if test "${1:-}" = "--backend"; then
  suite=backend
  shift
fi
test "$#" -le 1 || {
  echo "Usage: scripts/run-e2e.sh [--backend | frontend/tests/e2e/<name>.spec.js]" >&2
  exit 2
}
requested_spec="${1:-}"
test "$suite" = browser || test -z "$requested_spec" || exit 2
artifact_dir="${E2E_ARTIFACT_DIR:-$project_dir/test-results/e2e}"
mkdir -p "$artifact_dir"

resolve_spec() {
  case "$1" in
    frontend/tests/e2e/*.spec.js) spec="${1#frontend/}" ;;
    tests/e2e/*.spec.js) spec="$1" ;;
    *.spec.js) spec="tests/e2e/$1" ;;
    *) echo "E2E spec must be a Playwright .spec.js file" >&2
       return 2 ;;
  esac
  test -f "$project_dir/frontend/$spec" || {
    echo "E2E spec not found: $1" >&2
    return 2
  }
  printf '%s\n' "$spec"
}

browser_spec=""
test -z "$requested_spec" || browser_spec="$(resolve_spec "$requested_spec")"
browser_ensure_services="e2e-app e2e-frontend backend-e2e e2e-ai-provider e2e-meilisearch e2e mongo-init production-config-check"
backend_ensure_services="e2e-app backend-e2e e2e-ai-provider e2e-meilisearch mongo-init production-config-check"
case "$suite" in
  backend) ensure_services="$backend_ensure_services" ;;
  browser) ensure_services="$browser_ensure_services" ;;
esac

compose() {
  docker compose --project-name "$compose_project" \
    --env-file "$project_dir/.env.example" "$@"
}

clear_e2e_bucket() {
  compose --profile e2e run --rm --no-deps backend-e2e python tests/clear_e2e_bucket.py
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

# One destructive pass: compose down --volumes --remove-orphans removes every
# container, network and labeled volume owned by this project (the overlay's
# e2e_mongo*/e2e_minio/e2e_meili volumes included).
teardown_e2e_resources() {
  compose --profile e2e down --volumes --remove-orphans --timeout 1 >/dev/null
}

verify_e2e_resources_absent() {
  containers="$(docker ps -aq --filter "label=com.docker.compose.project=$compose_project")" || return 1
  volumes="$(docker volume ls -q --filter "label=com.docker.compose.project=$compose_project")" || return 1
  networks="$(docker network ls -q --filter "label=com.docker.compose.project=$compose_project")" || return 1
  test -z "$containers$volumes$networks"
}

preclean_e2e_resources() {
  teardown_e2e_resources || true
  verify_e2e_resources_absent
}

start_agent_app() {
  compose --profile e2e up -d --force-recreate --no-deps --wait agent-e2e-app agent-e2e-loser agent-tracer-app
}

run_browser_tests() {
  if test "$browser_spec" = "tests/e2e/agent-sidebar.spec.js"; then run_sidebar_browser_tests; return; fi
  set -- compose --profile e2e run --rm --no-deps \
    -v "$artifact_dir:/app/test-results" e2e
  test -z "$browser_spec" || set -- "$@" npm run test:e2e -- "$browser_spec"
  if test "$browser_spec" = "tests/e2e/agent-chat.spec.js" ||
     test "$browser_spec" = "tests/e2e/agent-threads.spec.js" ||
     test "$browser_spec" = "tests/e2e/agent-source-proof.spec.js"; then
    set -- compose --profile e2e run --rm \
      -v "$artifact_dir:/app/test-results" agent-e2e
    test -z "$browser_spec" || set -- "$@" npm run test:e2e -- "$browser_spec"
  fi
  if test "$browser_spec" = "tests/e2e/agent-tracer.spec.js" ||
     test "$browser_spec" = "tests/e2e/agent-annotation-rounds.spec.js"; then
    set -- compose --profile e2e run --rm -v "$artifact_dir:/app/test-results" agent-tracer
    test -z "$browser_spec" || set -- "$@" npm run test:e2e -- "$browser_spec"
  fi
  "$@"
}

run_bdd_browser_tests() {
  mkdir -p "$artifact_dir/bdd"
  compose --profile e2e run --rm --no-deps \
    -v "$artifact_dir/bdd:/app/test-results" e2e npm run test:e2e:bdd
}

run_agent_browser_tests() {
  set -- compose --profile e2e run --rm \
    -v "$artifact_dir:/app/test-results" agent-e2e
  test -z "$browser_spec" || set -- "$@" npm run test:e2e -- "$browser_spec"
  "$@"
}

run_sidebar_browser_tests() {
  compose --profile e2e run --rm -v "$artifact_dir:/app/test-results" \
    agent-e2e npm run test:e2e -- --project=sidebar
  compose --profile e2e run --rm -v "$artifact_dir:/app/test-results" \
    agent-tracer npm run test:e2e -- --project=sidebar-tracer
}

run_tracer_browser_tests() {
  compose --profile e2e run --rm \
    -v "$artifact_dir:/app/test-results" agent-tracer
}

run_backend_suite() {
  compose --profile e2e up -d --wait e2e-app
  start_agent_app
  clear_e2e_bucket
  compose --profile e2e run --rm --no-deps backend-e2e
}

run_browser_suite() {
  compose --profile e2e up -d --wait e2e-frontend
  start_agent_app
  clear_e2e_bucket
  run_browser_tests
  test -n "$browser_spec" || run_bdd_browser_tests
  test -n "$browser_spec" || run_agent_browser_tests
  test -n "$browser_spec" || run_tracer_browser_tests
}

# Teardown is ownership-only: compose down --volumes removes the isolated
# MinIO volume together with the bucket data, so cleanup never spawns a
# backend-e2e container (which would pull images or create resources after
# a failure).
cleanup() {
  original_status=$?
  trap - EXIT INT TERM
  cleanup_status=0
  teardown_e2e_resources || cleanup_status=1
  verify_e2e_resources_absent || cleanup_status=1
  test "$original_status" -ne 0 && exit "$original_status"
  exit "$cleanup_status"
}

trap 'exit 130' INT
trap 'exit 143' TERM
trap 'exit 129' HUP
: > "$lock_file"
exec 9>"$lock_file"
if ! flock -n 9; then
  echo "Another E2E run owns $compose_project (lock: $lock_file); waiting is not supported." >&2
  exit 2
fi
# Destructive cleanup is registered only after the lock is owned: a rejected
# second invocation must never touch the owner's resources.
trap cleanup EXIT
preclean_e2e_resources
scripts/ci-images.sh ensure mongo-init production-config-check
compose up -d mongo1 mongo2 mongo3
scripts/ci-images.sh ensure $ensure_services
compose up -d --wait mongo-init
drop_and_verify_database
case "$suite" in
  backend) run_backend_suite ;;
  browser) run_browser_suite ;;
esac
