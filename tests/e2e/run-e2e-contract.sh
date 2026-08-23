#!/bin/sh
set -eu

project_dir="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
runner="$project_dir/scripts/run-e2e.sh"
compose_file="$project_dir/docker-compose.yml"
pytest_config="$project_dir/backend/tests/pytest.ini"
meili_test="$project_dir/backend/tests/test_search_meilisearch_e2e.py"
case_content_test="$project_dir/backend/tests/test_search_case_content_e2e.py"
query_budget_test="$project_dir/backend/tests/test_auth_query_budget_e2e.py"

require_line() {
  grep -Fqx "$1" "$runner" || {
    echo "Missing run-e2e contract: $1" >&2
    exit 1
  }
}

require_line 'clear_e2e_bucket() {'
require_line '  compose --profile e2e run --rm --no-deps backend-e2e python tests/clear_e2e_bucket.py'
require_line 'clear_e2e_bucket'
require_line 'compose build e2e-app e2e-frontend backend-e2e e2e-ai-provider e2e-meilisearch'
require_line '  compose --profile e2e stop e2e-frontend e2e-app e2e-search-worker'
require_line '  drop_test_database "$database"'
require_line '  compose --profile e2e run --rm --no-deps e2e-search-init'
require_line '  compose --profile e2e up -d --force-recreate --no-deps e2e-search-worker'
require_line '  compose --profile e2e up -d --force-recreate --no-deps --wait e2e-app'
require_line '  compose --profile e2e up -d --force-recreate --no-deps --wait e2e-frontend'
require_line 'preclean_e2e_resources'
require_line '  original_status=$?'
require_line '  test "$original_status" -ne 0 && exit "$original_status"'
require_line '  exit "$cleanup_status"'
require_line 'trap cleanup EXIT'
require_line "trap 'exit 130' INT"
require_line "trap 'exit 143' TERM"
grep -Fqx '    command: ["python", "-m", "pytest", "-q", "-c", "tests/pytest.ini", "-m", "e2e", "tests"]' "$compose_file"
docker compose --env-file "$project_dir/.env.example" --profile e2e \
  config --format json | jq -e \
  '.services["e2e-app"].environment.MONGODB_URI | endswith("&appName=e2e-app")' \
  >/dev/null
if grep -Eq 'MEILI_CONTRACT_KEY[=:]' "$compose_file"; then
  echo "E2E must receive its Meilisearch key through a secret file" >&2
  exit 1
fi
grep -Fqx 'addopts = --strict-markers' "$pytest_config"
grep -Fq 'pytest.mark.e2e("MEILI_CONTRACT_URL", "MEILI_CONTRACT_KEY_FILE")' "$meili_test"
grep -Fq 'Path(os.environ["MEILI_CONTRACT_KEY_FILE"])' "$meili_test"

search_body="$(sed -n '/^def _search(/,/^$/p' "$case_content_test")"
pulse_line="$(printf '%s\n' "$search_body" | grep -n 'WorkerHeartbeat(context.database' | cut -d: -f1)"
request_line="$(printf '%s\n' "$search_body" | grep -n 'context.http.get("/api/search"' | cut -d: -f1)"
test -n "$pulse_line"
test "$pulse_line" -lt "$request_line"
grep -Fq 'MEASURE_ATTEMPTS = 3' "$query_budget_test"
grep -Fq 'return min(samples, key=lambda sample: sum(sample[0]["mongoOps"].values()))' \
  "$query_budget_test"
test "$(grep -Fc '_best_measure(' "$query_budget_test")" -eq 6
test "$(grep -Fc 'catalogReadConcerns"] == ("snapshot", "snapshot")' \
  "$query_budget_test")" -eq 2

for test_file in "$project_dir"/backend/tests/*_e2e.py; do
  grep -Fq 'pytest.mark.e2e' "$test_file"
  if grep -Fq 'skipif' "$test_file"; then
    echo "$test_file must not conditionally skip E2E coverage" >&2
    exit 1
  fi
  if grep -Fq 'pytest.skip' "$test_file"; then
    echo "$test_file must not skip E2E coverage" >&2
    exit 1
  fi
done
grep -q 'mcr.microsoft.com/playwright:v1.62.1-noble' "$project_dir/deploy/e2e.Dockerfile"
if grep -q 'playwright install' "$project_dir/deploy/e2e.Dockerfile"; then
  echo "E2E image must use the Playwright base image without reinstalling browsers" >&2
  exit 1
fi

clear_line="$(grep -n '^clear_e2e_bucket$' "$runner" | cut -d: -f1)"
tests_line="$(grep -n '^compose --profile e2e run --rm --no-deps backend-e2e$' "$runner" | cut -d: -f1)"
test "$clear_line" -lt "$tests_line" || {
  echo "E2E bucket must be cleared before tests run" >&2
  exit 1
}

reset_line="$(grep -n '^reset_browser_state$' "$runner" | cut -d: -f1)"
browser_line="$(grep -n '^compose --profile e2e run --rm --no-deps e2e$' "$runner" | cut -d: -f1)"
test "$tests_line" -lt "$reset_line" && test "$reset_line" -lt "$browser_line" || {
  echo "E2E app state must reset between backend and browser suites" >&2
  exit 1
}

reset_body="$(sed -n '/^reset_browser_state() {/,/^}/p' "$runner")"
stop_line="$(printf '%s\n' "$reset_body" | grep -n 'stop .*e2e-search-worker' | cut -d: -f1)"
drop_line="$(printf '%s\n' "$reset_body" | grep -n 'drop_test_database' | cut -d: -f1)"
init_line="$(printf '%s\n' "$reset_body" | grep -n '^  rebuild_search$' | cut -d: -f1)"
worker_line="$(printf '%s\n' "$reset_body" | grep -n 'up .*e2e-search-worker' | cut -d: -f1)"
app_line="$(printf '%s\n' "$reset_body" | grep -n 'up .*e2e-app' | cut -d: -f1)"
frontend_line="$(printf '%s\n' "$reset_body" | grep -n 'up .*e2e-frontend' | cut -d: -f1)"
test "$stop_line" -lt "$drop_line"
test "$drop_line" -lt "$init_line"
test "$init_line" -lt "$worker_line"
test "$worker_line" -lt "$app_line"
test "$app_line" -lt "$frontend_line"

test "$(grep -c '^rebuild_search$' "$runner" || true)" -eq 0
grep -q '^compose_project="case-library-v2"$' "$runner"
grep -Fq 'docker compose --project-name "$compose_project"' "$runner"
grep -Fq 'e2e_meili_volume="${compose_project}_e2e_meili_data"' "$runner"
grep -Fq 'e2e_network="${compose_project}_e2e_test"' "$runner"
grep -Fq 'compose --profile e2e ps -aq' "$runner"
! grep -Eq 'docker (volume|network) .*case-library-v2_e2e_' "$runner"
grep -Fq 'db.getMongo().getDBNames().includes' "$runner"
grep -Fq 'client.list_objects(bucket, recursive=True)' "$project_dir/backend/tests/clear_e2e_bucket.py"

cleanup_body="$(sed -n '/^cleanup() {/,/^}/p' "$runner")"
mock_cleanup_step() { test "${cleanup_failure:-}" != "$1"; }
stop_e2e_runtime() { mock_cleanup_step stop; }
clear_e2e_bucket() { mock_cleanup_step bucket; }
drop_and_verify_database() { mock_cleanup_step database; }
remove_e2e_services() { mock_cleanup_step services; }
remove_e2e_volume() { mock_cleanup_step volume; }
remove_e2e_network() { mock_cleanup_step network; }
verify_e2e_resources_absent() { mock_cleanup_step verify; }

assert_cleanup_status() {
  original="$1"
  cleanup_failure="$2"
  expected="$3"
  set +e
  (eval "$cleanup_body"; (exit "$original"); cleanup)
  actual=$?
  set -e
  test "$actual" -eq "$expected"
}

assert_cleanup_status 0 "" 0
assert_cleanup_status 0 volume 1
assert_cleanup_status 7 "" 7
assert_cleanup_status 7 volume 7
