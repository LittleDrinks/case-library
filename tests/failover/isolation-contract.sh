#!/bin/sh
set -eu

project_dir="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
runner="$project_dir/scripts/run-failover.sh"
project=case-library-v2-failover-contract
config="$(FAILOVER_PROJECT_NAME="$project" "$runner" config)"

service_config() {
  echo "$config" | awk -v service="  $1:" '
    $0 == service { selected = 1 }
    selected && $0 ~ /^  [[:alnum:]_-]+:$/ && $0 != service { exit }
    selected { print }
  '
}

echo "$config" | grep -q '^name: case-library-v2-failover-contract$'
app="$(service_config app)"
frontend="$(service_config frontend)"
backup="$(service_config backup-tools)"
meili="$(service_config failover-meilisearch)"
search_init="$(service_config failover-search-init)"
search_worker="$(service_config failover-search-worker)"
echo "$app" | grep -q 'image: case-library-v2-failover-app'
echo "$frontend" | grep -q 'image: case-library-v2-failover-frontend'
echo "$app" | grep -q '/case_library_failover?replicaSet=rs0'
echo "$app" | grep -q 'MONGODB_DB_NAME: case_library_failover'
echo "$app" | grep -q 'OBJECT_STORE_BUCKET: case-library-failover'
echo "$app" | grep -q 'SEARCH_URL: http://failover-meilisearch:7700'
echo "$app" | grep -q 'SEARCH_INDEX_UID: catalog_failover'
echo "$app" | grep -B2 -A2 'failover-search-init:' | grep -q 'service_completed_successfully'
echo "$app" | grep -B2 -A2 'failover-search-worker:' | grep -q 'service_started'
echo "$meili" | grep -q 'image: case-library-v2-failover-meilisearch'
echo "$meili" | grep -q 'source: failover_meili_data'
echo "$search_init" | grep -q 'app.modules.search.rebuild'
echo "$search_init" | grep -q 'APP_ENV: test'
echo "$search_init" | grep -q 'ENABLE_DEMO_SEED: "false"'
echo "$search_worker" | grep -q 'app.modules.search.worker'
echo "$backup" | grep -q 'MONGODB_DB_NAME: case_library_failover'
echo "$backup" | grep -q 'OBJECT_STORE_BUCKET: case-library-failover'
if echo "$config" | grep -q 'published:'; then
  echo "Failover services must not publish host ports" >&2
  exit 1
fi
for volume in minio_data mongo1_data mongo2_data mongo3_data failover_meili_data; do
  echo "$config" | grep -q "name: ${project}_${volume}"
done
for network in edge database restore_test; do
  echo "$config" | grep -q "name: ${project}_${network}"
done
for subnet in 10.254.246.0/24 10.254.247.0/24 10.254.248.0/24; do
  echo "$config" | grep -q "subnet: $subnet"
done
grep -Fqx "$(printf '\tscripts/run-failover.sh')" "$project_dir/Makefile"
if sed -n '/^failover:/,/^[^[:space:]][^:]*:/p' "$project_dir/Makefile" |
  grep -q 'docker compose'; then
  echo "Failover target must use the isolated runner" >&2
  exit 1
fi
grep -Fq 'before="$(default_snapshot)"' "$runner"
grep -Fq 'after="$(default_snapshot)"' "$runner"
grep -Fq 'require_default_stack' "$runner"
grep -Fq 'test "$health" = 200' "$runner"
grep -Fq 'test "$after" = "$before"' "$runner"
grep -Fq '"search_worker_state"' "$runner"
grep -Fq 'down --volumes --remove-orphans' "$runner"
grep -Fq 'verify_failover_resources_absent' "$runner"
grep -Fq 'original_status=$?' "$runner"
grep -Fq 'test "$original_status" -eq 0 || exit "$original_status"' "$runner"
grep -Fq 'exit "$cleanup_status"' "$runner"
grep -Fq "trap 'exit 130' INT" "$runner"
grep -Fq "trap 'exit 143' TERM" "$runner"
for resource in 'docker ps -aq' 'docker volume ls -q' 'docker network ls -q'; do
  grep -Fq "$resource" "$runner"
done
for script in scripts/mongo-backup.sh scripts/restore-drill.sh; do
  if grep -Fq -- '-f "$project_dir/docker-compose.yml"' "$project_dir/$script"; then
    echo "$script must not select the default Compose stack" >&2
    exit 1
  fi
done

election="$project_dir/tests/failover/mongo-election.sh"
grep -q '^clear_probes() {' "$election"
grep -Fq 'search_worker_state.findOne' "$election"
grep -Fq 'heartbeat.updatedAt.getTime()' "$election"
worker_wait_body="$(sed -n '/^wait_for_worker_advance() {/,/^}/p' "$election")"
echo "$worker_wait_body" | grep -Fq '[ "$current" -gt "$previous" ]'
clear_line="$(grep -n '^clear_probes "\$probe"$' "$election" | cut -d: -f1)"
write_line="$(grep -n '^write_probe "\$probe" before$' "$election" | cut -d: -f1)"
test "$clear_line" -lt "$write_line"
if sed -n "1,${write_line}p" "$election" | grep -q '^drop_test_database "\$database"$'; then
  echo "Mongo election must not drop the database before writing the probe" >&2
  exit 1
fi
if grep -Fqx 'drop_test_database "$database"' "$election"; then
  echo "Mongo election must preserve the initialized search database" >&2
  exit 1
fi
heartbeat_line="$(grep -n '^heartbeat_before="$(worker_updated_at "\$probe")"$' "$election" | cut -d: -f1)"
heartbeat_ready_line="$(grep -n '^test -n "\$heartbeat_before"$' "$election" | cut -d: -f1)"
stop_line="$(grep -n '^compose stop "\$original" >/dev/null$' "$election" | cut -d: -f1)"
replacement_line="$(grep -n '^replacement="$(wait_for_new_primary "\$probe" "\$original")"$' "$election" | cut -d: -f1)"
worker_wait_line="$(grep -n '^wait_for_worker_advance "\$probe" "\$heartbeat_before"$' "$election" | cut -d: -f1)"
ready_line="$(grep -n "health/ready', timeout=5" "$election" | cut -d: -f1)"
test "$heartbeat_line" -lt "$heartbeat_ready_line"
test "$heartbeat_ready_line" -lt "$stop_line"
test "$stop_line" -lt "$replacement_line"
test "$replacement_line" -lt "$worker_wait_line"
test "$worker_wait_line" -lt "$ready_line"

cleanup_body="$(sed -n '/^cleanup() {/,/^}/p' "$runner")"
verify_body="$(sed -n '/^verify_failover_resources_absent() {/,/^}/p' "$runner")"
assert_cleanup_status() {
  original="$1"
  cleanup_failure="$2"
  expected="$3"
  set +e
  (
    eval "$cleanup_body"
    cleanup_resources() { test -z "$cleanup_failure"; }
    (exit "$original")
    cleanup
  )
  actual=$?
  set -e
  test "$actual" -eq "$expected"
}

assert_cleanup_status 0 "" 0
assert_cleanup_status 0 cleanup 1
assert_cleanup_status 7 "" 7
assert_cleanup_status 7 cleanup 7

(
  eval "$verify_body"
  docker() { return 9; }
  ! verify_failover_resources_absent
)
