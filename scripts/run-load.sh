#!/bin/sh
set -eu

project_dir="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
dir_slug="$(printf '%s' "$(basename "$project_dir")" | sed 's/^[.]//' | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9_-]/-/g')"
test -n "$dir_slug" || dir_slug="checkout"
dir_hash="$(printf '%s' "$(CDPATH= cd -- "$project_dir" && pwd -P)" | sha256sum | cut -c1-8)"
compose_project="case-library-load-${dir_slug}-${dir_hash}"
export COMPOSE_PROJECT_NAME="$compose_project"
export IMAGE_PREFIX="$compose_project"
export COMPOSE_FILE="$project_dir/docker-compose.yml:$project_dir/deploy/load.compose.yml"
lock_file="/tmp/case-library-load-${dir_slug}-${dir_hash}.lock"
profile="${1:-smoke}"
database="case_library_load"
mongo_uri="mongodb://mongo1:27017,mongo2:27017,mongo3:27017/$database?replicaSet=rs0"
results_dir="$project_dir/test-results"
resource_pid=""
cd "$project_dir"
. "$project_dir/scripts/test-database.sh"

compose() {
  docker compose --project-name "$compose_project" \
    --env-file "$project_dir/.env.example" "$@"
}

seed_load_materials() {
  compose exec -T mongo1 mongosh "$mongo_uri" --quiet < tests/load/seed-materials.js
}

assert_load_dataset() {
  evidence="$results_dir/load-$profile-dataset.txt"
  query='const pending=db.search_outbox.countDocuments({$expr:{$gt:["$sequence","$appliedSequence"]}}); const control=db.search_control.findOne({_id:"catalog"}); print(db.materials.countDocuments({}), db.materials.countDocuments({status:"active"}), db.search_outbox.countDocuments({}), pending, control ? control.sequence : -1)'
  counts="$(compose exec -T mongo1 mongosh "$mongo_uri" --quiet --eval "$query")"
  set -- $counts
  printf 'database=%s total_materials=%s active_materials=%s outbox_entries=%s pending_outbox=%s catalog_sequence=%s\n' \
    "$database" "$1" "$2" "$3" "$4" "$5" >"$evidence"
  cat "$evidence"
  test "$1" -eq 12480 && test "$2" -eq 12480
  test "$3" -eq 0 && test "$4" -eq 0
}

reset_load_artifacts() {
  prefix="$results_dir/load-$profile"
  rm -f "$prefix.txt" "$prefix-summary.json" "$prefix-resources.tsv"
  rm -f "$prefix-nginx.txt" "$prefix-nginx-errors.txt" "$prefix-dataset.txt"
  rm -f "$prefix-catalog.txt"
}

reset_all_load_artifacts() {
  for target in smoke peak resilience rate steady; do
    profile="$target"
    reset_load_artifacts
  done
}

run_catalog_gate() {
  gate_phase="$1"
  evidence="$results_dir/load-$profile-catalog.txt"
  token="$profile-$gate_phase-$(date +%s)-$$"
  target="$(catalog_target)"
  set -- $target
  printf 'phase=%s\n' "$gate_phase" >>"$evidence"
  if compose --profile load run --rm --no-deps --env CATALOG_GATE_TOKEN="$token" \
    --env CATALOG_INDEX_UID="$1" --env CATALOG_GENERATION="$2" \
    --env CATALOG_INDEX_EPOCH="$3" \
    load run /tests/catalog-gate.js >>"$evidence" 2>&1; then status=0; else status=$?; fi
  cat "$evidence"
  return "$status"
}

catalog_target() {
  query='const row=db.search_catalog_generation.findOne({_id:"catalog"}); if (!row || !row.indexUid || !row.generation || !row.indexEpoch) quit(1); print(row.indexUid, row.generation, row.indexEpoch)'
  compose exec -T mongo1 mongosh "$mongo_uri" --quiet --eval "$query"
}

assert_load_worker() {
  workers="$(compose --profile load ps --status running -q load-search-worker)"
  test "$(printf '%s\n' "$workers" | sed '/^$/d' | wc -l | tr -d ' ')" -eq 1 || {
    echo "Load search worker is not running" >&2
    return 1
  }
}

run_k6() {
  script="/tests/high-frequency.js"
  test "$profile" = "steady" && script="/tests/preauthenticated.js"
  result_log="$results_dir/load-$profile.txt"
  result_json="/results/load-$profile-summary.json"
  if compose --profile load run --rm --no-deps \
    --user "$(id -u):$(id -g)" -v "$results_dir:/results" \
    load run --summary-mode=full --summary-export "$result_json" "$script" \
    >"$result_log" 2>&1; then status=0; else status=$?; fi
  cat "$result_log"
  return "$status"
}

sample_resources() {
  trap 'exit 0' TERM
  while :; do
    date -Ins
    names="$(compose --profile load ps --format '{{.Name}}' load-app load-frontend load-search-worker load-meilisearch mongo1 mongo2 mongo3)"
    if [ -n "$names" ]; then
      docker stats --no-stream --format '{{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.PIDs}}' $names
    fi
    sleep 8
  done
}

stop_resource_sampler() {
  test -n "$resource_pid" || return 0
  kill "$resource_pid" 2>/dev/null || true
  if wait "$resource_pid" 2>/dev/null; then status=0; else status=$?; fi
  resource_pid=""
  test "$status" -eq 0 || echo "Resource sampler stopped unexpectedly" >&2
  return "$status"
}

capture_nginx() {
  evidence="$results_dir/load-$profile-nginx.txt"
  runtime_errors="$results_dir/load-$profile-nginx-errors.txt"
  if sh tests/load/upstream-balance.sh >"$evidence" 2>&1; then status=0; else status=$?; fi
  compose --profile load logs --no-color --timestamps load-frontend |
    awk '/recv\(\) failed|temporarily disabled|no live upstreams/' >"$runtime_errors"
  cat "$runtime_errors" >>"$evidence"
  test ! -s "$runtime_errors" || status=1
  cat "$evidence"
  return "$status"
}

verify_load_cleanup() {
  containers="$(docker ps -aq --filter "label=com.docker.compose.project=$compose_project")" || return 1
  volumes="$(docker volume ls -q --filter "label=com.docker.compose.project=$compose_project")" || return 1
  networks="$(docker network ls -q --filter "label=com.docker.compose.project=$compose_project")" || return 1
  test -z "$containers$volumes$networks"
}

case "$profile" in
  smoke|peak|resilience|rate|steady) ;;
  reset-all) ;;
  *) echo "Unknown load profile: $profile" >&2; exit 2 ;;
esac

cleanup() {
  original_status=$?
  trap - EXIT
  trap '' INT TERM HUP
  cleanup_status=0
  stop_resource_sampler || cleanup_status=$?
  compose --profile load down --volumes --remove-orphans --timeout 1 >/dev/null 2>&1 || cleanup_status=$?
  verify_load_cleanup || cleanup_status=$?
  test "$original_status" -eq 0 || exit "$original_status"
  exit "$cleanup_status"
}

# Serialize same-checkout load runs before any destructive step; a rejected
# second invocation must never tear down the owner's resources.
: > "$lock_file"
exec 9>"$lock_file"
if ! flock -n 9; then
  echo "Another load run owns $compose_project (lock: $lock_file)" >&2
  exit 2
fi
mkdir -p "$results_dir"
if test "$profile" = reset-all; then
  reset_all_load_artifacts
  exit 0
fi
reset_load_artifacts
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
trap 'exit 129' HUP
compose --profile load down --volumes --remove-orphans --timeout 1 >/dev/null
verify_load_cleanup
compose up -d --wait mongo-init
if [ "${SKIP_BUILD:-false}" != "true" ]; then
  compose build load-app load-frontend load-meilisearch load
fi
compose --profile load up -d --wait load-meilisearch
compose --profile load run --rm --no-deps --env ENABLE_DEMO_SEED=true load-search-init python -m app.cli.bootstrap
seed_load_materials
sample_resources >"$results_dir/load-$profile-resources.tsv" 2>&1 &
resource_pid=$!
compose --profile load run --rm --no-deps --env ENABLE_DEMO_SEED=false load-search-init
compose --profile load up -d --wait load-frontend
assert_load_dataset
run_catalog_gate pre-load
sh tests/load/backend-distribution.sh
sh tests/load/upstream-keepalive.sh
export LOAD_PROFILE="$profile"
if run_k6; then
  load_status=0
else
  load_status=$?
fi
if assert_load_worker && run_catalog_gate post-load; then
  catalog_status=0
else
  catalog_status=$?
fi
if stop_resource_sampler; then
  sampler_status=0
else
  sampler_status=$?
fi
if capture_nginx; then
  balance_status=0
else
  balance_status=$?
fi
if [ "$balance_status" -ne 0 ]; then
  compose --profile load ps load-app load-frontend
  compose --profile load logs --tail=40 load-frontend
fi
test "$balance_status" -eq 0 || exit "$balance_status"
test "$sampler_status" -eq 0 || exit "$sampler_status"
test "$catalog_status" -eq 0 || exit "$catalog_status"
exit "$load_status"
