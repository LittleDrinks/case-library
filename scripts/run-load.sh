#!/bin/sh
set -eu

project_dir="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
compose_project="case-library-v2"
load_meili_volume="${compose_project}_load_meili_data"
profile="${1:-smoke}"
database="case_library_load"
mongo_uri="mongodb://mongo1:27017,mongo2:27017,mongo3:27017/$database?replicaSet=rs0"
results_dir="$project_dir/test-results"
resource_pid=""
load_services="load load-frontend load-app load-search-worker load-search-init load-meilisearch"
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

remove_load_volume() {
  if docker volume inspect "$load_meili_volume" >/dev/null 2>&1; then
    docker volume rm "$load_meili_volume" >/dev/null
  fi
}

database_exists() {
  target="$1"
  validate_test_database "$target"
  query="print(db.getMongo().getDBNames().includes('$target'))"
  compose exec -T mongo1 mongosh \
    'mongodb://mongo1:27017,mongo2:27017,mongo3:27017/?replicaSet=rs0' \
    --quiet --eval "$query"
}

verify_load_cleanup() {
  remaining="$(compose --profile load ps -aq $load_services)"
  test -z "$remaining" || { echo "Load containers remain: $remaining" >&2; return 1; }
  ! docker volume inspect "$load_meili_volume" >/dev/null 2>&1 || {
    echo "Load Meilisearch volume remains" >&2; return 1;
  }
  test "$(database_exists "$database")" = "false" || {
    echo "Load database remains: $database" >&2; return 1;
  }
}

case "$profile" in
  smoke|peak|resilience|rate|steady) ;;
  reset-all)
    mkdir -p "$results_dir"
    reset_all_load_artifacts
    exit 0
    ;;
  *) echo "Unknown load profile: $profile" >&2; exit 2 ;;
esac

mkdir -p "$results_dir"
reset_load_artifacts

cleanup() {
  original_status=$?
  trap - EXIT INT TERM
  cleanup_status=0
  stop_resource_sampler || cleanup_status=$?
  compose --profile load rm -sf load load-frontend load-app load-search-worker load-search-init load-meilisearch >/dev/null 2>&1 || cleanup_status=$?
  remove_load_volume || cleanup_status=$?
  drop_test_database "$database" || cleanup_status=$?
  verify_load_cleanup || cleanup_status=$?
  test "$original_status" -eq 0 || exit "$original_status"
  exit "$cleanup_status"
}

trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
compose --profile load rm -sf load load-frontend load-app load-search-worker load-search-init load-meilisearch >/dev/null 2>&1
remove_load_volume
compose up -d --wait mongo-init
drop_test_database "$database"
verify_load_cleanup
if [ "${SKIP_BUILD:-false}" != "true" ]; then
  compose build load-app load-frontend load-meilisearch
  docker build -f deploy/k6.Dockerfile -t case-library-v2-load:latest .
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
