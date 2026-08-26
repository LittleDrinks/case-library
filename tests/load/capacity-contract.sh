#!/bin/sh
set -eu

project_dir="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
cd "$project_dir"

test -f tests/load/seed-materials.js
test -f tests/load/catalog-gate.js
grep -q 'const TARGET_MATERIALS = 12_480;' tests/load/seed-materials.js
grep -q 'status: "active"' tests/load/seed-materials.js
grep -q 'db.search_outbox.deleteMany({});' tests/load/seed-materials.js
grep -q 'db.search_revocations.deleteMany({});' tests/load/seed-materials.js
grep -q 'db.search_control.deleteMany({});' tests/load/seed-materials.js
! grep -q 'search_outbox.insert' tests/load/seed-materials.js
! grep -q 'appliedSequence' tests/load/seed-materials.js
grep -q 'seed_load_materials' scripts/run-load.sh
grep -q 'assert_load_dataset' scripts/run-load.sh
grep -q 'load-\$profile-dataset.txt' scripts/run-load.sh
grep -q 'outbox_entries=%s pending_outbox=%s catalog_sequence=%s' scripts/run-load.sh
grep -Fq 'test "$3" -eq 0 && test "$4" -eq 0' scripts/run-load.sh
! grep -Fq 'test "$5" -eq 12480' scripts/run-load.sh
grep -q 'run_catalog_gate' scripts/run-load.sh
grep -q 'load-\$profile-catalog.txt' scripts/run-load.sh
grep -q 'search_catalog_generation' scripts/run-load.sh
grep -q 'row.indexUid' scripts/run-load.sh
grep -q 'row.indexEpoch' scripts/run-load.sh
grep -q 'CATALOG_INDEX_UID' scripts/run-load.sh
grep -q 'CATALOG_GENERATION' scripts/run-load.sh
grep -q 'CATALOG_INDEX_EPOCH' scripts/run-load.sh

grep -q 'const targetMaterials = 12_480;' tests/load/catalog-gate.js
grep -Fq 'docClass = "material-full"' tests/load/catalog-gate.js
grep -q 'catalog-meta' tests/load/catalog-gate.js
grep -q 'meta.generation !== expectedGeneration' tests/load/catalog-gate.js
grep -q 'index.updatedAt !== expectedEpoch' tests/load/catalog-gate.js
grep -q '/api/cases' tests/load/catalog-gate.js
grep -q '"approve"' tests/load/catalog-gate.js
grep -q 'sleep(outboxLagSeconds)' tests/load/catalog-gate.js
grep -Fq 'responseCallback: http.expectedStatuses(200, 503)' tests/load/catalog-gate.js
grep -q '/health/ready' tests/load/catalog-gate.js
grep -q 'BACKEND_URL' tests/load/catalog-gate.js
grep -q 'BACKEND_URL: http://app:8001' docker-compose.yml
grep -Fq 'http_reqs{operation:${operation}}' tests/load/catalog-gate.js
grep -Fq '"X-Load-Probe": "catalog-gate"' tests/load/catalog-gate.js
grep -Fq 'stageId: "ug", typeId: "ct-figure", templateId: "tpl-general-v1"' tests/load/catalog-gate.js
grep -Fq 'const saved = saveTitle(created, title, csrf);' tests/load/catalog-gate.js
grep -Fq 'const submitted = transition(saved, csrf, "submit");' tests/load/catalog-gate.js
! grep -Fq '"/api/cases", { title }' tests/load/catalog-gate.js
grep -Fq 'load_marker=$http_x_load_probe' deploy/nginx.conf
test "$(grep -Fc 'load_marker=catalog-gate' tests/load/upstream-balance.sh)" -eq 2

bootstrap_command='compose --profile load run --rm --no-deps --env ENABLE_DEMO_SEED=true load-search-init python -m app.cli.bootstrap'
rebuild_command='compose --profile load run --rm --no-deps --env ENABLE_DEMO_SEED=false load-search-init'
startup_command='compose --profile load up -d --wait load-frontend'
test "$(grep -Fxc "$bootstrap_command" scripts/run-load.sh)" -eq 1
test "$(grep -Fxc "$rebuild_command" scripts/run-load.sh)" -eq 1
test "$(grep -Fxc "$startup_command" scripts/run-load.sh)" -eq 1
bootstrap_line="$(grep -nFx "$bootstrap_command" scripts/run-load.sh | cut -d: -f1)"
seed_line="$(grep -n '^seed_load_materials$' scripts/run-load.sh | cut -d: -f1)"
rebuild_line="$(grep -nFx "$rebuild_command" scripts/run-load.sh | cut -d: -f1)"
startup_line="$(grep -nFx "$startup_command" scripts/run-load.sh | cut -d: -f1)"
assert_line="$(grep -n '^assert_load_dataset$' scripts/run-load.sh | cut -d: -f1)"
catalog_line="$(grep -n '^run_catalog_gate pre-load$' scripts/run-load.sh | cut -d: -f1)"
run_line="$(grep -n '^if run_k6; then$' scripts/run-load.sh | cut -d: -f1)"
test "$bootstrap_line" -lt "$seed_line"
test "$seed_line" -lt "$rebuild_line"
test "$rebuild_line" -lt "$startup_line"
test "$startup_line" -lt "$assert_line"
test "$assert_line" -lt "$catalog_line"
test "$catalog_line" -lt "$run_line"

grep -q '^assert_load_worker() {' scripts/run-load.sh
grep -Fq 'compose --profile load ps --status running -q load-search-worker' scripts/run-load.sh
worker_line="$(grep -n '^if assert_load_worker && run_catalog_gate post-load; then$' scripts/run-load.sh | cut -d: -f1)"
test "$catalog_line" -lt "$run_line"
test "$run_line" -lt "$worker_line"

sh -n scripts/run-load.sh
grep -Fq 'compose build load-app load-frontend' scripts/run-load.sh
! grep -Fq 'compose build app frontend' scripts/run-load.sh

grep -q 'setupTimeout:' tests/load/preauthenticated.js
grep -q 'function provisionSessions()' tests/load/preauthenticated.js
grep -q 'data.sessions\[__VU - 1\]' tests/load/preauthenticated.js
grep -Fq "load-app load-frontend load-search-worker load-meilisearch mongo1 mongo2 mongo3" scripts/run-load.sh
grep -q 'sessions.length !== steadyVus' tests/load/preauthenticated.js
grep -q 'new Set(sessions.map((row) => row.session)).size' tests/load/preauthenticated.js
grep -q 'new Set(sessions.map((row) => row.case.id)).size' tests/load/preauthenticated.js
grep -Fq '[cookieName]: { value, replace: true }' tests/load/preauthenticated.js
grep -q 'cookies: authCookies(session)' tests/load/preauthenticated.js
if grep -q 'Cookie:' tests/load/preauthenticated.js; then
  echo "Steady sessions must override the VU cookie jar per request" >&2
  exit 1
fi
auth_options="$(sed -n '/^function authOptions(/,/^}/p' tests/load/preauthenticated.js)"
request_options="$(sed -n '/^function requestOptions(/,/^}/p' tests/load/preauthenticated.js)"
case_request="$(sed -n '/^function caseRequest(/,/^}/p' tests/load/preauthenticated.js)"
cursor_response="$(sed -n '/^function cursorResponse(/,/^}/p' tests/load/preauthenticated.js)"
default_body="$(sed -n '/^export default function/,/^}/p' tests/load/preauthenticated.js)"
printf '%s\n' "$auth_options" | grep -Fq 'cookies: authCookies(session)'
printf '%s\n' "$request_options" | grep -Fq 'authOptions(session, csrf)'
printf '%s\n' "$case_request" | grep -Fq 'requestOptions(context.session, context.csrf'
printf '%s\n' "$cursor_response" | grep -Fq '...authOptions(context.session)'
printf '%s\n' "$default_body" | grep -Fq 'const auth = authOptions(context.session)'
printf '%s\n' "$default_body" | grep -Fq 'readRequests(context, auth,'
if sed -n '/^export default function/,/^}/p' tests/load/preauthenticated.js | grep -q 'login('; then
  echo "Steady measurement must not perform password verification" >&2
  exit 1
fi

for script in tests/load/high-frequency.js tests/load/preauthenticated.js; do
  grep -Fq 'stageId: "ug", typeId: "ct-figure", templateId: "tpl-general-v1"' "$script"
  ! grep -Fq 'document: { type: "doc"' "$script"
  grep -q 'nextCursor' "$script"
  grep -q '"catalog-cursor"' "$script"
  grep -q '"material-cursor"' "$script"
  grep -q '&cursor=' "$script"
  grep -Fq 'http_reqs{operation:${operation}}' "$script"
  grep -Fq 'http_req_duration{operation:${operation}}' "$script"
  grep -Fq 'http_req_failed{operation:${operation}}' "$script"
  grep -Fq 'http_req_failed{operation:${operation},phase:hold}' "$script"
  grep -q 'count>0' "$script"
  grep -q 'rate==0' "$script"
  grep -q '__ITER === 0' "$script"
  grep -q 'phase:hold' "$script"
done

grep -q 'index(\$0, "probe=") == 0' tests/load/upstream-balance.sh
grep -q 'if (server_errors) failed = 1' tests/load/upstream-balance.sh
grep -q 'runtime_errors' scripts/run-load.sh
grep -q 'test ! -s "\$runtime_errors"' scripts/run-load.sh
grep -q 'reset_load_artifacts' scripts/run-load.sh

reset_line="$(grep -n '^reset_load_artifacts$' scripts/run-load.sh | cut -d: -f1)"
seed_line="$(grep -n '^seed_load_materials$' scripts/run-load.sh | cut -d: -f1)"
test "$reset_line" -lt "$seed_line"

sampler_line="$(grep -n '^sample_resources >' scripts/run-load.sh | cut -d: -f1)"
grep -q 'Resource sampler stopped unexpectedly' scripts/run-load.sh
sampler_stop_line="$(grep -n '^if stop_resource_sampler; then$' scripts/run-load.sh | cut -d: -f1)"
sampler_gate_line="$(grep -n '^test "\$sampler_status" -eq 0 || exit "\$sampler_status"$' scripts/run-load.sh | cut -d: -f1)"
test "$sampler_line" -lt "$rebuild_line"
test "$rebuild_line" -lt "$run_line"
test "$run_line" -lt "$sampler_stop_line"
test "$sampler_stop_line" -lt "$sampler_gate_line"

sampler_contract="$(mktemp)"
trap 'rm -f "$sampler_contract"' EXIT INT TERM
sed -n '/^stop_resource_sampler() {/,/^}/p' scripts/run-load.sh >"$sampler_contract"
. "$sampler_contract"
sh -c 'trap "exit 0" TERM; while :; do sleep 1; done' &
resource_pid=$!
sleep 0.1
stop_resource_sampler
sh -c 'exit 7' &
resource_pid=$!
sleep 0.1
if stop_resource_sampler; then sampler_exit=0; else sampler_exit=$?; fi
test "$sampler_exit" -eq 7
rm -f "$sampler_contract"
trap - EXIT INT TERM

cleanup_body="$(sed -n '/^cleanup() {/,/^}/p' scripts/run-load.sh)"
stop_line="$(printf '%s\n' "$cleanup_body" | grep -n 'rm -sf load load-frontend load-app' | cut -d: -f1)"
drop_line="$(printf '%s\n' "$cleanup_body" | grep -n 'drop_test_database' | cut -d: -f1)"
test "$stop_line" -lt "$drop_line"
grep -q 'original_status=\$?' scripts/run-load.sh
grep -q 'verify_load_cleanup' scripts/run-load.sh
grep -q 'database_exists' scripts/run-load.sh
grep -q '^compose_project="case-library-v2"$' scripts/run-load.sh
grep -Fq 'docker compose --project-name "$compose_project"' scripts/run-load.sh
grep -Fq 'load_meili_volume="${compose_project}_load_meili_data"' scripts/run-load.sh
! grep -q 'docker volume .*case-library-v2_load_meili_data' scripts/run-load.sh

grep -q 'dropped_iterations.*count==0' tests/load/high-frequency.js
grep -q 'selectedProfile === "rate"' tests/load/high-frequency.js

for variable in SEARCH_PERCENT MATERIAL_PERCENT CURSOR_PERCENT STEADY_SETUP_TIMEOUT; do
  grep -q "${variable}:" docker-compose.yml
done
if grep -q 'STEADY_WRITE_USERNAME\|STEADY_WRITE_PASSWORD' docker-compose.yml; then
  echo "Steady load must use each VU's own session" >&2
  exit 1
fi

grep -q '^load-all:' Makefile
load_all="$(sed -n '/^load-all:/,/^[^[:space:]]/p' Makefile)"
first_load_command="$(printf '%s\n' "$load_all" | sed -n '2s/^[[:space:]]*//p')"
test "$first_load_command" = 'scripts/run-load.sh reset-all'
grep -q '^reset_all_load_artifacts() {' scripts/run-load.sh
grep -Fq 'for target in smoke peak resilience rate steady; do' scripts/run-load.sh
previous=0
for profile in smoke peak resilience rate steady; do
  line="$(printf '%s\n' "$load_all" | grep -n "scripts/run-load.sh $profile" | cut -d: -f1)"
  test "$line" -gt "$previous"
  previous="$line"
done
for document in README.md docs/operations.md; do
  grep -q 'make load-rate' "$document"
  grep -q 'make load-all' "$document"
done
