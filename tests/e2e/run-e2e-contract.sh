#!/bin/sh
set -eu

project_dir="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
runner="$project_dir/scripts/run-e2e.sh"
makefile="$project_dir/Makefile"
workflow="$project_dir/.github/workflows/ci.yml"
playwright_config="$project_dir/frontend/playwright.config.js"
compose_file="$project_dir/docker-compose.yml"
pytest_config="$project_dir/backend/tests/pytest.ini"
meili_test="$project_dir/backend/tests/test_search_meilisearch_e2e.py"
case_content_test="$project_dir/backend/tests/test_search_case_content_e2e.py"
query_budget_test="$project_dir/backend/tests/test_auth_query_budget_e2e.py"
backend_e2e_command='compose --profile e2e run --rm --no-deps backend-e2e'

require_line() {
  grep -Fqx "$1" "$runner" || {
    echo "Missing run-e2e contract: $1" >&2
    exit 1
  }
}

matching_line() {
  printf '%s\n' "$1" | grep -n "$2" | cut -d: -f1
}

require_line 'clear_e2e_bucket() {'
require_line "  $backend_e2e_command python tests/clear_e2e_bucket.py"
require_line 'compose up -d mongo1 mongo2 mongo3'
require_line 'browser_build_services="e2e-app e2e-frontend backend-e2e e2e-ai-provider e2e-meilisearch e2e"'
require_line 'backend_build_services="e2e-app backend-e2e e2e-ai-provider e2e-meilisearch"'
require_line 'compose build $build_services'
require_line 'compose up -d --wait mongo-init'
require_line '  compose --profile e2e stop -t 1 e2e-frontend e2e-app e2e-search-worker'
require_line '  compose --profile e2e stop -t 1 agent-e2e-app agent-e2e-loser agent-e2e-frontend agent-e2e-gateway'
require_line '  drop_test_database "$database"'
require_line '  compose --profile e2e up -d --wait e2e-app'
require_line '  compose --profile e2e up -d --wait e2e-frontend'
require_line 'preclean_e2e_resources'
e2e_runner_lines="$(cat "$runner")"
mongo_bg_line=$(printf '%s\n' "$e2e_runner_lines" | grep -nFx 'compose up -d mongo1 mongo2 mongo3' | cut -d: -f1)
build_line=$(printf '%s\n' "$e2e_runner_lines" | grep -nFx 'compose build $build_services' | cut -d: -f1)
mongo_wait_line=$(printf '%s\n' "$e2e_runner_lines" | grep -nFx 'compose up -d --wait mongo-init' | cut -d: -f1)
test "$mongo_bg_line" -lt "$build_line" || {
  echo "Mongo replica set must boot in the background while images build" >&2
  exit 1
}
test "$build_line" -lt "$mongo_wait_line" || {
  echo "Mongo health wait must come after image builds" >&2
  exit 1
}
if grep -Fq 'docker build -f deploy/e2e.Dockerfile' "$runner"; then
  echo "Playwright image must be built once via compose service e2e" >&2
  exit 1
fi
if grep -Fq 'compose build agent-' "$runner"; then
  echo "Agent e2e services must reuse shared images instead of rebuilding" >&2
  exit 1
fi
require_line 'run_browser_tests() {'
require_line '  set -- compose --profile e2e run --rm --no-deps \'
require_line '    -v "$artifact_dir:/app/test-results" e2e'
require_line '  test -z "$browser_spec" || set -- "$@" npm run test:e2e -- "$browser_spec"'
require_line 'run_backend_suite() {'
require_line '  compose --profile e2e run --rm --no-deps backend-e2e'
require_line 'run_browser_suite() {'
require_line '  backend) run_backend_suite ;;'
require_line '  browser) run_browser_suite ;;'
require_line '  original_status=$?'
require_line '  test "$original_status" -ne 0 && exit "$original_status"'
require_line '  exit "$cleanup_status"'
require_line 'trap cleanup EXIT'
require_line "trap 'exit 130' INT"
require_line "trap 'exit 143' TERM"
grep -Fq 'E2E_SPEC ?= $(SPEC)' "$makefile"
grep -q '^test-backend:' "$makefile"
grep -q '^test-frontend:' "$makefile"
grep -q '^backend-e2e:' "$makefile"
grep -q '^e2e-spec:' "$makefile"
make -C "$project_dir" -n e2e | grep -Eq '^scripts/run-e2e\.sh[[:space:]]*$'
make -C "$project_dir" -n backend-e2e | grep -Fx 'scripts/run-e2e.sh --backend'
make -C "$project_dir" -n e2e-spec SPEC=frontend/tests/e2e/homepage.spec.js | \
  grep -Fx 'scripts/run-e2e.sh "frontend/tests/e2e/homepage.spec.js"'
grep -Fq 'artifact_dir="${E2E_ARTIFACT_DIR:-$project_dir/test-results/e2e}"' "$runner"
grep -Fq 'frontend/tests/e2e/*.spec.js' "$runner"
grep -Fq 'tests/e2e/*.spec.js' "$runner"
test "$(grep -Fc 'compose --profile e2e run --rm --no-deps backend-e2e' "$runner")" -eq 2
! grep -Fq 'reset_browser_state' "$runner"
stop_lines="$(grep 'compose .* stop ' "$runner")"
test "$(printf '%s\n' "$stop_lines" | grep -c ' stop -t 1 ')" -eq 2

backend_job="$(sed -n '/^  backend-e2e:$/,/^  [a-z][a-z-]*:$/p' "$workflow")"
browser_job="$(sed -n '/^  e2e:$/,/^  [a-z][a-z-]*:$/p' "$workflow")"
grep -Fqx 'concurrency:' "$workflow"
grep -Fqx '  group: ${{ github.workflow }}-${{ github.ref }}' "$workflow"
grep -Fqx '  cancel-in-progress: true' "$workflow"
printf '%s\n' "$backend_job" | grep -Fq '    name: Backend E2E'
printf '%s\n' "$backend_job" | grep -Fq '        run: make backend-e2e'
! printf '%s\n' "$backend_job" | grep -Fq '    needs:'
printf '%s\n' "$browser_job" | grep -Fq '    name: E2E'
printf '%s\n' "$browser_job" | grep -Fq '        run: make e2e'
! printf '%s\n' "$browser_job" | grep -Fq '    needs:'
grep -Fq 'outputDir: "test-results"' "$playwright_config"
grep -Fq '["json", { outputFile: "test-results/report.json" }]' "$playwright_config"
grep -Fq 'trace: "retain-on-failure"' "$playwright_config"
grep -Fq 'screenshot: "only-on-failure"' "$playwright_config"
grep -Fq 'name: "generic"' "$playwright_config"
grep -Fq 'name: "agent"' "$playwright_config"
test ! -e "$project_dir/frontend/playwright.agent.config.js"
e2e_config="$(
  docker compose --env-file "$project_dir/.env.example" --profile e2e config --format json
)"
for service in mongo1 mongo2 mongo3 minio e2e-app agent-e2e-app agent-e2e-loser \
  agent-e2e-frontend agent-e2e-gateway e2e-frontend; do
  printf '%s' "$e2e_config" | jq -e --arg service "$service" \
    '.services[$service].healthcheck.interval == "1s"' >/dev/null
done
printf '%s' "$e2e_config" | jq -e \
  '.services["backend-e2e"].command == [
    "python", "-m", "pytest", "-q", "-c", "tests/pytest.ini",
    "-m", "e2e", "tests"
  ]' >/dev/null
printf '%s' "$e2e_config" | jq -e \
  '.services["e2e-app"].environment.MONGODB_URI | endswith("&appName=e2e-app")' \
  >/dev/null
if grep -Eq 'MEILI_CONTRACT_KEY[=:]' "$compose_file"; then
  echo "E2E must receive its Meilisearch key through a secret file" >&2
  exit 1
fi
grep -Fqx 'addopts = --strict-markers' "$pytest_config"
grep -Fq 'pytest.mark.e2e("MEILI_CONTRACT_URL", "MEILI_CONTRACT_KEY_FILE")' "$meili_test"
grep -Fq 'key_file = os.environ["MEILI_CONTRACT_KEY_FILE"]' "$meili_test"
grep -Fq 'Path(key_file).read_text(encoding="utf-8").strip()' "$meili_test"

search_body="$(sed -n '/^def _search(/,/^$/p' "$case_content_test")"
pulse_line="$(matching_line "$search_body" 'WorkerHeartbeat(context.database')"
request_line="$(matching_line "$search_body" 'context.http.get("/api/search"')"
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

backend_suite="$(sed -n '/^run_backend_suite() {/,/^}/p' "$runner")"
browser_suite="$(sed -n '/^run_browser_suite() {/,/^}/p' "$runner")"
printf '%s\n' "$backend_suite" | grep -Fq '  clear_e2e_bucket'
printf '%s\n' "$backend_suite" | grep -Fq '  start_agent_app'
printf '%s\n' "$backend_suite" | grep -Fq '  compose --profile e2e run --rm --no-deps backend-e2e'
printf '%s\n' "$browser_suite" | grep -Fq '  clear_e2e_bucket'
printf '%s\n' "$browser_suite" | grep -Fq '  run_browser_tests'
printf '%s\n' "$browser_suite" | grep -Fq '  test -n "$browser_spec" || run_agent_browser_tests'
! printf '%s\n' "$browser_suite" | grep -Fq 'backend-e2e'
! printf '%s\n' "$browser_suite" | grep -Fq 'drop_test_database'

grep -q '^compose_project="case-library-v2"$' "$runner"
grep -Fq 'docker compose --project-name "$compose_project"' "$runner"
grep -Fq 'e2e_meili_volume="${compose_project}_e2e_meili_data"' "$runner"
grep -Fq 'e2e_network="${compose_project}_e2e_test"' "$runner"
grep -Fq 'compose --profile e2e ps -aq' "$runner"
! grep -Eq 'docker (volume|network) .*case-library-v2_e2e_' "$runner"
grep -Fq 'db.getMongo().getDBNames().includes' "$runner"
grep -Fq 'client.list_objects(bucket, recursive=True)' \
  "$project_dir/backend/tests/clear_e2e_bucket.py"

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
