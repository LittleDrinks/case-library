#!/bin/sh
set -eu

project_dir="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
runner="$project_dir/scripts/run-e2e.sh"
makefile="$project_dir/Makefile"
workflow="$project_dir/.github/workflows/ci.yml"
playwright_config="$project_dir/frontend/playwright.config.js"
compose_file="$project_dir/docker-compose.yml"
overlay_file="$project_dir/deploy/e2e.compose.yml"
pytest_config="$project_dir/backend/tests/pytest.ini"
meili_test="$project_dir/backend/tests/test_search_meilisearch_e2e.py"
case_content_test="$project_dir/backend/tests/test_search_case_content_e2e.py"
query_budget_test="$project_dir/backend/tests/test_auth_query_budget_e2e.py"
config_project=case-library-v2-e2e-contract

grep -q '^test-backend: ensure-backend-test$' "$makefile"
grep -q '^test-frontend: ensure-frontend-test$' "$makefile"
grep -Fq 'ruff check --no-cache app tests /app/scripts /opt/case-library/wait_for_mongo.py' "$compose_file"
grep -Fq '"check:complexity": "eslint --config eslint.config.js src"' "$project_dir/frontend/package.json"
grep -Fq 'complexity: ["error", 15]' "$project_dir/frontend/eslint.config.js"

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
require_line "  compose --profile e2e run --rm --no-deps backend-e2e python tests/clear_e2e_bucket.py"
require_line 'scripts/ci-images.sh ensure mongo-init production-config-check'
require_line 'compose up -d mongo1 mongo2 mongo3'
require_line 'scripts/ci-images.sh ensure $ensure_services'
require_line 'compose up -d --wait mongo-init'
require_line '  drop_test_database "$database"'
require_line '  compose --profile e2e up -d --wait e2e-app'
require_line '  compose --profile e2e up -d --wait e2e-frontend'
require_line 'preclean_e2e_resources'
e2e_runner_lines="$(cat "$runner")"
ensure_boot_line=$(printf '%s\n' "$e2e_runner_lines" | grep -nFx 'scripts/ci-images.sh ensure mongo-init production-config-check' | cut -d: -f1)
mongo_bg_line=$(printf '%s\n' "$e2e_runner_lines" | grep -nFx 'compose up -d mongo1 mongo2 mongo3' | cut -d: -f1)
ensure_line=$(printf '%s\n' "$e2e_runner_lines" | grep -nFx 'scripts/ci-images.sh ensure $ensure_services' | cut -d: -f1)
mongo_wait_line=$(printf '%s\n' "$e2e_runner_lines" | grep -nFx 'compose up -d --wait mongo-init' | cut -d: -f1)
test "$ensure_boot_line" -lt "$mongo_bg_line" || {
  echo "mongo-init and production-config-check images must exist before mongo up so mongo never triggers a local build" >&2
  exit 1
}
test "$mongo_bg_line" -lt "$ensure_line" || {
  echo "Remaining image pulls must overlap the mongo replica set boot" >&2
  exit 1
}
test "$ensure_line" -lt "$mongo_wait_line" || {
  echo "Mongo health wait must come after image ensure" >&2
  exit 1
}
ci_images="$project_dir/scripts/ci-images.sh"
test -x "$ci_images"
grep -Fq 'compose config --format json' "$ci_images"
grep -Fq 'docker pull --quiet "$ref"' "$ci_images"
grep -Fq 'docker tag "$ref"' "$ci_images"
# ci-images must adopt the caller's project/prefix (so run-e2e's build and
# run resolve the same tags) and only fall back when they are unset.
grep -Fq 'COMPOSE_PROJECT_NAME:-' "$ci_images"
grep -Fq 'IMAGE_PREFIX:-' "$ci_images"
# Behavioral probes run against a self-contained fixture checkout with its
# own copy of the scripts, so mutations never touch the live tree and the
# fixture's derivation is independent of this checkout's path hash.
probe_dir="$(mktemp -d)"
trap 'rm -rf "$probe_dir"' EXIT
mkdir -p "$probe_dir/scripts" "$probe_dir/backend/app" "$probe_dir/backend/tests"
cp "$ci_images" "$probe_dir/scripts/ci-images.sh"
cp "$project_dir/backend/app/__init__.py" "$probe_dir/backend/app/__init__.py"
cp "$project_dir/backend/tests/pytest.ini" "$probe_dir/backend/tests/pytest.ini"
cp "$project_dir/backend/requirements.lock" "$probe_dir/backend/requirements.lock"
cp "$project_dir/.env.example" "$probe_dir/.env.example"
cat > "$probe_dir/docker-compose.yml" <<'YAML'
services:
  backend-test:
    profiles: ["test"]
    image: ${IMAGE_PREFIX:-fixture-fallback}-backend-test
    build:
      context: .
      dockerfile: backend.Dockerfile
      target: test
    network_mode: none
YAML
cat > "$probe_dir/backend.Dockerfile" <<'DOCKER'
FROM alpine:3
COPY backend/app ./app
COPY backend/tests ./tests
COPY backend/requirements.lock /tmp/requirements.lock
DOCKER
git init -q "$probe_dir"
git -C "$probe_dir" -c user.email=probe@local -c user.name=probe add -A
git -C "$probe_dir" -c user.email=probe@local -c user.name=probe commit -qm base
fp_probe() { (cd "$probe_dir" && env -u COMPOSE_PROJECT_NAME -u IMAGE_PREFIX bash ./scripts/ci-images.sh fingerprint backend-test); }
# Adopt-vs-fallback must be observed through ci-images' own Docker calls,
# not compose's env interpolation: a recording docker shim answers compose
# config with a minimal valid JSON (no daemon access) and we assert the
# --project-name ci-images chose. Fingerprint under the shim still fails at
# image inspect (no such image) — expected; the log line is the evidence.
mkdir -p "$probe_dir/bin"
cat > "$probe_dir/bin/docker" <<SHIM
#!/bin/sh
printf '%s\n' "\$*" >> "$probe_dir/docker-calls.log"
for a in "\$@"; do
  case "\$a" in
    --format)
      printf '%s\n' '{"services": {"backend-test": {"build": {"dockerfile": "backend.Dockerfile", "target": "test"}, "image": "fixture-image"}}}'
      exit 0
      ;;
  esac
done
exit 1
SHIM
chmod +x "$probe_dir/bin/docker"
(
  cd "$probe_dir"
  PATH="$probe_dir/bin:$PATH" COMPOSE_PROJECT_NAME=adopt-probe-e2e IMAGE_PREFIX=adopt-probe-e2e \
    bash ./scripts/ci-images.sh fingerprint backend-test >/dev/null 2>&1
)
grep -Fq -- '--project-name adopt-probe-e2e' "$probe_dir/docker-calls.log" || {
  echo "ci-images must adopt the caller's COMPOSE_PROJECT_NAME" >&2
  exit 1
}
: > "$probe_dir/docker-calls.log"
(
  cd "$probe_dir"
  PATH="$probe_dir/bin:$PATH" env -u COMPOSE_PROJECT_NAME -u IMAGE_PREFIX \
    bash ./scripts/ci-images.sh fingerprint backend-test >/dev/null 2>&1
)
fixture_fallback_project="case-library-test-$(printf '%s' "$(CDPATH= cd -- "$probe_dir" && pwd -P)" | sha256sum | cut -c1-8)"
grep -Fq -- "--project-name $fixture_fallback_project" "$probe_dir/docker-calls.log" || {
  echo "bare invocation must fall back to the fixture-derived project ($fixture_fallback_project)" >&2
  exit 1
}
# Fingerprint mutation probes: new untracked COPY source and a rename must
# each change the fingerprint; reverting restores it.
fp_baseline="$(fp_probe)"
echo probe > "$probe_dir/backend/app/zz_probe_untracked.py"
fp_untracked="$(fp_probe)"
rm "$probe_dir/backend/app/zz_probe_untracked.py"
mv "$probe_dir/backend/app/__init__.py" "$probe_dir/backend/app/__init_renamed.py"
fp_renamed="$(fp_probe)"
mv "$probe_dir/backend/app/__init_renamed.py" "$probe_dir/backend/app/__init__.py"
test "$fp_baseline" != "$fp_untracked" || {
  echo "fingerprint ignores a new untracked COPY source" >&2
  exit 1
}
test "$fp_baseline" != "$fp_renamed" || {
  echo "fingerprint ignores a renamed COPY source" >&2
  exit 1
}
test "$fp_baseline" = "$(fp_probe)" || {
  echo "fingerprint must be stable after reverting the probes" >&2
  exit 1
}

# Isolation contract: the runner derives its Compose project and image tag
# prefix from the checkout directory plus a path hash (always isolated, no
# opt-in flag), and keeps every resource name derived from that project.
grep -Fq 'dir_slug="$(printf '"'"'%s'"'"' "$(basename "$project_dir")" | sed '"'"'s/^[.]//'"'"' | tr '"'"'[:upper:]'"'"' '"'"'[:lower:]'"'"' | sed '"'"'s/[^a-z0-9_-]/-/g'"'"')"' "$runner"
grep -Fq 'dir_hash="$(printf '"'"'%s'"'"' "$(CDPATH= cd -- "$project_dir" && pwd -P)" | sha256sum | cut -c1-8)"' "$runner"
grep -Fq 'compose_project="case-library-e2e-${dir_slug}-${dir_hash}"' "$runner"
grep -Fq "trap 'exit 129' HUP" "$runner"
grep -Fq 'flock -n 9' "$runner"
# Whole-entrypoint failure probe: with a PATH docker shim injecting a
# failure at the mongo-init health wait, the runner after the failure must
# only perform owned teardown (compose down) plus inventory inspections —
# never run/up/build/pull (no bucket-clear container).
python3 "$project_dir/tests/e2e/entrypoint-failure-probe.py" "$project_dir" >/dev/null
# Lock ownership is behavior: with the lock held (Python fcntl), a second
# runner must exit 2 through a PATH shim and issue zero Docker calls, and
# destructive cleanup must be registered only after the lock is owned.
lock_line="$(grep -n 'flock -n 9' "$runner" | cut -d: -f1)"
trap_line="$(grep -n '^trap cleanup EXIT$' "$runner" | cut -d: -f1)"
test -n "$lock_line" && test -n "$trap_line"
test "$lock_line" -lt "$trap_line"
python3 "$project_dir/tests/e2e/lock-owner-probe.py" "$project_dir" >/dev/null
python3 "$project_dir/tests/e2e/lock-owner-probe.py" "$project_dir" load >/dev/null
# Cleanup is ownership-only: no bucket-clear container in the teardown path.
cleanup_body="$(sed -n '/^cleanup() {/,/^}/p' "$runner")"
! printf '%s\n' "$cleanup_body" | grep -Fq 'clear_e2e_bucket' || {
  echo "cleanup must not run the bucket-clear container; teardown deletes the owned MinIO volume" >&2
  exit 1
}
# Fingerprint mutation probes (fixture-based) live further down; ensure the
# lock regression precedes them to fail fast on isolation regressions.
require_line 'export IMAGE_PREFIX="$compose_project"'
grep -Fq 'deploy/e2e.compose.yml' "$runner"
! grep -Eq 'docker (volume|network) .*case-library-v2_e2e_' "$runner"
test "$(grep -Fc 'case-library-v2' "$runner")" -eq 1

# Both suites must still run through ci-images with the same ensure list.
grep -Fq 'browser_ensure_services=' "$runner"
grep -Fq 'backend_ensure_services=' "$runner"

test "$(grep -Fc 'compose --profile e2e run --rm --no-deps backend-e2e' "$runner")" -eq 2

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

# Behavior: the merged run config (docker-compose.yml + overlay, project
# derived from the checkout directory) gives this checkout its own replica
# set volumes, minio volume, auto-allocated networks, image tags, and no
# host ports. The unmerged base file stays untouched for the demo stack.
isolated_config="$(
  IMAGE_PREFIX="$config_project" docker compose \
    --project-name "$config_project" \
    --env-file "$project_dir/.env.example" --profile e2e \
    -f "$compose_file" -f "$overlay_file" config --format json
)"
printf '%s' "$isolated_config" | jq -e \
  '.services["backend-e2e"].command == [
    "python", "-m", "pytest", "-q", "-c", "tests/pytest.ini",
    "-m", "e2e", "tests"
  ]' >/dev/null
printf '%s' "$isolated_config" | jq -e \
  '.services["e2e-app"].environment.MONGODB_URI | endswith("&appName=e2e-app")' \
  >/dev/null
printf '%s' "$isolated_config" | jq -e --arg project "$config_project" '
  .services["e2e-app"].image == ($project + "-e2e-app") and
  .services["backend-e2e"].image == ($project + "-backend-test") and
  .services["e2e"].image == ($project + "-e2e") and
  .services["e2e-frontend"].image == ($project + "-e2e-frontend") and
  .services.mongo1.image == "mongo:7"
' >/dev/null
printf '%s' "$isolated_config" | jq -e --arg project "$config_project" '
  .volumes.e2e_mongo1_data.name == ($project + "_e2e_mongo1_data") and
  .volumes.e2e_mongo2_data.name == ($project + "_e2e_mongo2_data") and
  .volumes.e2e_mongo3_data.name == ($project + "_e2e_mongo3_data") and
  .volumes.e2e_minio_data.name == ($project + "_e2e_minio_data") and
  .volumes.e2e_meili_data.name == ($project + "_e2e_meili_data")
' >/dev/null
printf '%s' "$isolated_config" | jq -e '
  (.services.mongo1.networks | keys | sort) == ["e2e_database"] and
  (.services.minio.networks | keys | sort) == ["e2e_database"] and
  (.services["e2e-app"].networks | keys | sort) == ["e2e_database", "e2e_test"] and
  (.services["backend-e2e"].networks | keys | sort) == ["e2e_database", "e2e_test"] and
  (.services | to_entries | map(select(.value.networks.database != null)) | length) == 0
' >/dev/null
printf '%s' "$isolated_config" | jq -e '
  .services["e2e-app"].ports == null and
  .services.frontend.ports == null and
  .services.app.ports == null
' >/dev/null
printf '%s' "$isolated_config" | jq -e '
  .networks["e2e_database"].internal == true and
  .networks["e2e_database"].ipam.config == null and
  .networks["e2e_test"].internal == true and
  .networks["e2e_test"].ipam.config == null
' >/dev/null

# The e2e runner services keep 1s healthchecks in the isolated stack too.
for service in mongo1 mongo2 mongo3 minio e2e-app agent-e2e-app agent-e2e-loser \
  agent-e2e-frontend agent-e2e-gateway e2e-frontend; do
  printf '%s' "$isolated_config" | jq -e --arg service "$service" \
    '.services[$service].healthcheck.interval == "1s"' >/dev/null
done

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
printf '%s\n' "$browser_suite" | grep -Fq '  test -n "$browser_spec" || run_bdd_browser_tests'
require_line '    -v "$artifact_dir/bdd:/app/test-results" e2e npm run test:e2e:bdd'
printf '%s\n' "$browser_suite" | grep -Fq '  test -n "$browser_spec" || run_agent_browser_tests'
! printf '%s\n' "$browser_suite" | grep -Fq 'backend-e2e'
! printf '%s\n' "$browser_suite" | grep -Fq 'drop_test_database'

grep -Fq 'docker compose --project-name "$compose_project"' "$runner"
grep -Fq 'db.getMongo().getDBNames().includes' "$runner"
grep -Fq 'client.list_objects(bucket, recursive=True)' \
  "$project_dir/backend/tests/clear_e2e_bucket.py"

# Cleanup must be one destructive pass that removes every owned resource
# (containers, volumes, networks via compose down --volumes), then verify
# against the real Docker resource inventory — not a name grep.
cleanup_body="$(sed -n '/^cleanup() {/,/^}/p' "$runner")"
verify_body="$(sed -n '/^verify_e2e_resources_absent() {/,/^}/p' "$runner")"
printf '%s\n' "$verify_body" | grep -Fq 'com.docker.compose.project'
printf '%s\n' "$cleanup_body" | grep -Fq 'teardown_e2e_resources'
printf '%s\n' "$cleanup_body" | grep -Fq 'verify_e2e_resources_absent'
teardown_body="$(sed -n '/^teardown_e2e_resources() {/,/^}/p' "$runner")"
printf '%s\n' "$teardown_body" | grep -Fq 'down --volumes --remove-orphans'
grep -Fq 'trap cleanup EXIT' "$runner"
grep -Fq "trap 'exit 130' INT" "$runner"
grep -Fq "trap 'exit 143' TERM" "$runner"

# The exclusive lock must be taken before any teardown runs, so a second run
# in the same checkout can never preclean an active run's resources.
lock_line="$(grep -n 'flock -n 9' "$runner" | cut -d: -f1)"
preclean_line="$(grep -n '^preclean_e2e_resources$' "$runner" | cut -d: -f1)"
test -n "$lock_line" && test -n "$preclean_line"
test "$lock_line" -lt "$preclean_line"

# Behavior: evaluating the real verify function against the real Docker CLI
# (mocked only at the docker() boundary with a resource inventory) reports
# absence when the inventory is empty and presence when it is not.
verify_eval() {
  inventory="$1"
  (
    compose_project=inventory-probe
    docker() {
      case "$1" in
        ps|volume|network) if test -n "$inventory"; then printf '%s\n' "$inventory"; fi ;;
      esac
      return 0
    }
    eval "$verify_body"
    verify_e2e_resources_absent
  )
}
rc_empty=0
verify_eval '' >/dev/null 2>&1 || rc_empty=$?
rc_owned=0
verify_eval 'abc123' >/dev/null 2>&1 || rc_owned=$?
test "$rc_empty" -eq 0 || {
  echo "verify_e2e_resources_absent must succeed on an empty inventory" >&2
  exit 1
}
test "$rc_owned" -ne 0 || {
  echo "verify_e2e_resources_absent must fail while owned resources remain" >&2
  exit 1
}

grep -Fq 'E2E_SPEC ?= $(SPEC)' "$makefile"
grep -q '^backend-e2e:' "$makefile"
grep -q '^e2e-spec:' "$makefile"
make -C "$project_dir" -n e2e | grep -Eq '^scripts/run-e2e\.sh[[:space:]]*$'
make -C "$project_dir" -n backend-e2e | grep -Fx 'scripts/run-e2e.sh --backend'
make -C "$project_dir" -n e2e-spec SPEC=frontend/tests/e2e/homepage.spec.js | \
  grep -Fx 'scripts/run-e2e.sh "frontend/tests/e2e/homepage.spec.js"'
grep -Fq 'artifact_dir="${E2E_ARTIFACT_DIR:-$project_dir/test-results/e2e}"' "$runner"
grep -Fq 'frontend/tests/e2e/*.spec.js' "$runner"
grep -Fq 'tests/e2e/*.spec.js' "$runner"
! grep -Fq 'reset_browser_state' "$runner"
# Teardown is a single compose down pass, not per-service stops.
! grep -Eq 'compose .* stop ' "$runner"

# Refusing to drop a database through another project's mongo is behavior,
# verified against the shared helper.
grep -Fq 'verify_mongo_project_ownership' "$project_dir/scripts/test-database.sh"
grep -Fq 'com.docker.compose.project' "$project_dir/scripts/test-database.sh"
grep -Fq '. "$project_dir/scripts/test-database.sh"' "$runner"

# Behavior: the real cleanup body propagates both the original status and a
# cleanup failure, evaluated with the destructive steps stubbed.
assert_cleanup_status() {
  original="$1"
  fail_teardown="$2"
  expected="$3"
  set +e
  (
    compose_project=cleanup-probe
    teardown_e2e_resources() {
      if test -n "$fail_teardown"; then return 7; fi
      return 0
    }
    verify_e2e_resources_absent() { return 0; }
    eval "$cleanup_body"
    (exit "$original")
    cleanup
  )
  actual=$?
  set -e
  test "$actual" -eq "$expected"
}

assert_cleanup_status 0 "" 0
assert_cleanup_status 0 fail 1
assert_cleanup_status 9 "" 9
assert_cleanup_status 9 fail 9

python3 "$project_dir/tests/e2e/browser-report-probe.py"
