#!/bin/sh
set -eu

project_dir="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
config_file="${1:-}"

fail() {
  printf '%s\n' "$1" >&2
  exit "${2:-2}"
}

cache_dir="${CASE_LIB_WORKER361_CACHE_DIR:-}"
test -n "$cache_dir" \
  || fail "real AI E2E failed: set the prepared case-lib-worker361 cache directory"
cache_dir="$(realpath "$cache_dir")" \
  || fail "real AI E2E failed: cache directory cannot be resolved"
cache_override="$cache_dir/override.yaml"
artifacts_dir="$cache_dir/artifacts"

test -n "$config_file" && test -r "$config_file" \
  || fail "real AI E2E failed: pass a readable, explicit Compose env file"
test -r "$cache_override" && test -d "$artifacts_dir" \
  || fail "real AI E2E failed: case-lib-worker361 cache is unavailable"
command -v docker >/dev/null 2>&1 && command -v jq >/dev/null 2>&1 \
  && command -v python3 >/dev/null 2>&1 \
  || fail "real AI E2E failed: Docker Compose, jq, and Python 3 are required"

config_file="$(realpath "$config_file")" \
  || fail "real AI E2E failed: explicit Compose env file cannot be resolved"
main_env="$(realpath "$project_dir/.env" 2>/dev/null || true)"
test -z "$main_env" || test "$config_file" != "$main_env" \
  || fail "real AI E2E failed: use the dedicated explicit env file"

git_status="$(git -C "$project_dir" status --porcelain --untracked-files=all)" \
  || fail "real AI E2E failed: source tree status could not be read" 3
test -z "$git_status" \
  || fail "real AI E2E failed: commit the source and run from a clean tree" 3
unset git_status
source_hash="$(git -C "$project_dir" rev-parse HEAD)" \
  || fail "real AI E2E failed: source commit could not be resolved" 3
build_manifest="$cache_dir/real-ai-build-manifest.json"
test -f "$build_manifest" && test ! -L "$build_manifest" && test -r "$build_manifest" \
  || fail "real AI E2E failed: matching final-build manifest is unavailable" 4
build_manifest_hash="$(sha256sum "$build_manifest" | cut -d ' ' -f 1)"
build_record="$(jq -ce --arg source_hash "$source_hash" '
  def image_id: type == "string" and test("^sha256:[a-f0-9]{64}$");
  def file_hash: type == "string" and test("^[a-f0-9]{64}$");
  if .formatVersion == 1 and .gitSha == $source_hash and .gitDirty == false
    and (.images.app | image_id)
    and (.images.test | image_id)
    and (.images.frontend | image_id)
    and (.images.backendTest | image_id)
    and (.fileHashes.appSource | file_hash)
    and (.fileHashes.testSource | file_hash)
    and (.fileHashes.frontendDist | file_hash)
  then {
    images: {
      app: .images.app,
      test: .images.test,
      frontend: .images.frontend,
      backendTest: .images.backendTest
    },
    fileHashes: {
      appSource: .fileHashes.appSource,
      testSource: .fileHashes.testSource,
      frontendDist: .fileHashes.frontendDist
    }
  }
  else empty end
' "$build_manifest" 2>/dev/null)" \
  || fail "real AI E2E failed: final-build manifest does not match the clean source" 4
app_image_id="$(printf '%s' "$build_record" | jq -r '.images.app')"
test_image_id="$(printf '%s' "$build_record" | jq -r '.images.test')"
frontend_image_id="$(printf '%s' "$build_record" | jq -r '.images.frontend')"
backend_test_image_id="$(printf '%s' "$build_record" | jq -r '.images.backendTest')"
app_source_hash="$(printf '%s' "$build_record" | jq -r '.fileHashes.appSource')"
test_source_hash="$(printf '%s' "$build_record" | jq -r '.fileHashes.testSource')"
frontend_dist_hash="$(printf '%s' "$build_record" | jq -r '.fileHashes.frontendDist')"
unset build_record

unset CASE_LIB_WORKER361_CACHE_DIR
unset REAL_AI_PROVIDER_BASE_URL REAL_AI_PREFERRED_MODEL
unset REAL_AI_PROVIDER_KEY_FILE REAL_AI_ADMIN_CREDENTIALS_FILE REAL_AI_EGRESS_SUBNET
unset REAL_AI_ARTIFACTS_DIR REAL_AI_REPORT_NAME REAL_AI_SOURCE_HASH
unset REAL_AI_APP_IMAGE_ID REAL_AI_TEST_IMAGE_ID REAL_AI_FRONTEND_IMAGE_ID
unset REAL_AI_BACKEND_TEST_IMAGE_ID REAL_AI_APP_SOURCE_HASH REAL_AI_TEST_SOURCE_HASH
unset REAL_AI_FRONTEND_DIST_HASH REAL_AI_BUILD_MANIFEST_HASH
artifact_owner="$(stat -c '%u:%g' "$artifacts_dir" 2>/dev/null)" \
  || fail "real AI E2E failed: artifacts owner cannot be resolved" 3
run_uid="$(id -u 2>/dev/null)" \
  || fail "real AI E2E failed: runner uid cannot be resolved" 3
run_gid="$(id -g 2>/dev/null)" \
  || fail "real AI E2E failed: runner gid cannot be resolved" 3
case "$run_uid:$run_gid" in
  *[!0-9:]*|:*) fail "real AI E2E failed: numeric report owner is unavailable" 3 ;;
esac
test "$run_uid:$run_gid" = "$artifact_owner" \
  || fail "real AI E2E failed: runner must own the artifacts directory" 3
unset artifact_owner

result_dir="$(mktemp -d "$artifacts_dir/real-ai.XXXXXX")" \
  || fail "real AI E2E failed: private report directory could not be created"
chmod 700 "$result_dir"
report_name="$(basename "$result_dir")"
report_file="$result_dir/report.json"
report_container_path="/app/test-results/$report_name/report.json"
runtime_hash_dir="$result_dir/runtime-hash"
mkdir -m 700 "$runtime_hash_dir"
project_name="case-lib-worker361"
runtime_started=false
hash_container_id=""
cleanup_status="not_run"
cleanup_failure_code=""

compose() {
  REAL_AI_ARTIFACTS_DIR="$artifacts_dir" \
  REAL_AI_REPORT_NAME="$report_name" \
  REAL_AI_SOURCE_HASH="$source_hash" \
  REAL_AI_APP_IMAGE_ID="$app_image_id" \
  REAL_AI_TEST_IMAGE_ID="$test_image_id" \
  REAL_AI_FRONTEND_IMAGE_ID="$frontend_image_id" \
  REAL_AI_BACKEND_TEST_IMAGE_ID="$backend_test_image_id" \
  REAL_AI_APP_SOURCE_HASH="$app_source_hash" \
  REAL_AI_TEST_SOURCE_HASH="$test_source_hash" \
  REAL_AI_FRONTEND_DIST_HASH="$frontend_dist_hash" \
  REAL_AI_BUILD_MANIFEST_HASH="$build_manifest_hash" \
  REAL_AI_RUN_UID="$run_uid" \
  REAL_AI_RUN_GID="$run_gid" \
    docker compose --env-file "$config_file" --project-name "$project_name" \
      --profile e2e -f "$project_dir/docker-compose.yml" \
      -f "$cache_override" \
      -f "$project_dir/tests/e2e/real-ai.compose.override.yml" "$@"
}

service_image_id() {
  image_ref="$(printf '%s' "$compose_image_refs" | jq -er \
    --arg name "$1" '.[$name]' 2>/dev/null)" \
    || return 1
  docker image inspect --format '{{.Id}}' "$image_ref" 2>/dev/null
}

image_tree_hash() {
  image_ref="$1"
  image_path="$2"
  tree_name="$3"
  tree_dir="$runtime_hash_dir/$tree_name"
  mkdir "$tree_dir" || return 1
  hash_container_id="$(docker create --network none --entrypoint /bin/true \
    "$image_ref" 2>/dev/null)" || return 1
  if ! docker cp "$hash_container_id:$image_path/." "$tree_dir/" >/dev/null 2>&1; then
    return 1
  fi
  if ! docker rm "$hash_container_id" >/dev/null 2>&1; then
    return 1
  fi
  hash_container_id=""
  tree_hash="$(python3 "$project_dir/scripts/hash_real_ai_tree.py" "$tree_dir" 2>/dev/null)" \
    || return 1
  rm -rf "$tree_dir" || return 1
}

require_runtime_mount() {
  printf '%s' "$compose_runtime_data" | jq -e \
    --arg service "$1" --arg source "$2" --arg target "$3" \
    '.mounts[$service] | any(.[]; .type == "bind" and .source == $source and .target == $target and .read_only == true)' \
    >/dev/null 2>&1
}

require_runtime_writable_mount() {
  printf '%s' "$compose_runtime_data" | jq -e \
    --arg service "$1" --arg source "$2" --arg target "$3" \
    '.mounts[$service] | any(.[]; .type == "bind" and .source == $source and .target == $target and .read_only == false)' \
    >/dev/null 2>&1
}

verify_runtime_exit() {
  for service in e2e e2e-frontend e2e-app e2e-search-worker e2e-ai-provider \
    e2e-search-init e2e-meilisearch mongo-init mongo1 mongo2 mongo3 minio; do
    running="$(docker ps -q \
      --filter "label=com.docker.compose.project=$project_name" \
      --filter "label=com.docker.compose.service=$service")"
    test -z "$running" || return 1
  done
  for volume in mongo1_data mongo2_data mongo3_data minio_data e2e_meili_data; do
    retained="$(docker volume ls -q \
      --filter "label=com.docker.compose.project=$project_name" \
      --filter "label=com.docker.compose.volume=$volume")"
    test -n "$retained" || return 1
  done
}

set_cleanup_failure() {
  cleanup_failed=true
  cleanup_status="failed"
  test -n "$cleanup_failure_code" || cleanup_failure_code="$1"
}

finish() {
  exit_status=$?
  trap - EXIT INT TERM
  cleanup_failed=false

  if test -n "$hash_container_id"; then
    if docker rm -f "$hash_container_id" >/dev/null 2>&1; then
      hash_container_id=""
    else
      set_cleanup_failure "hash_container_cleanup_failed"
    fi
  fi

  if [ "$runtime_started" = true ]; then
    if ! compose stop -t 10 e2e e2e-frontend e2e-app e2e-search-worker e2e-ai-provider \
      >/dev/null 2>&1; then
      set_cleanup_failure "service_stop_failed"
    fi

    if test -f "$report_file"; then
      cleanup_output=""
      if cleanup_output="$(compose run --rm --no-deps --pull never --user 0:0 backend-e2e \
        python /app/scripts/clear_real_ai_e2e.py "$report_container_path" \
        2>/dev/null)"; then
        if printf '%s' "$cleanup_output" | jq -e '.cleanup == "passed"' >/dev/null 2>&1; then
          test "$cleanup_status" = "failed" || cleanup_status="passed"
        else
          set_cleanup_failure "cleanup_report_invalid"
        fi
      else
        cleanup_failure_code="$(printf '%s' "$cleanup_output" | jq -r \
          'if type == "object" then .failureCode // empty else empty end' 2>/dev/null || true)"
        case "$cleanup_failure_code" in
          invalid_invocation|invalid_report|report_unavailable|invalid_synthetic_user_id|\
          invalid_synthetic_case_id|invalid_synthetic_id|database_scope_mismatch|\
          index_scope_mismatch|synthetic_user_scope_mismatch|synthetic_case_owner_mismatch|\
          case_owner_required|synthetic_case_missing|test_username_required|test_username_mismatch|\
          synthetic_case_ambiguous|synthetic_user_missing|ownership_root_changed|\
          cleanup_dependency_failure) ;;
          *) cleanup_failure_code="cleanup_command_failed" ;;
        esac
        set_cleanup_failure "$cleanup_failure_code"
      fi
      unset cleanup_output
    fi

    if ! compose stop -t 10 e2e-search-init e2e-meilisearch mongo-init \
      mongo1 mongo2 mongo3 minio >/dev/null 2>&1; then
      set_cleanup_failure "service_stop_failed"
    fi
    if ! verify_runtime_exit; then
      set_cleanup_failure "retained_resource_check_failed"
    fi
  fi

  if test -f "$report_file"; then
    report_tmp="$result_dir/report.sanitized.json"
    jq --arg cleanup "$cleanup_status" --arg failure_code "$cleanup_failure_code" \
      'del(.cleanupIdentity) | (.failed //= []) | .cleanup = $cleanup | if $cleanup == "failed" then .failed += [{"stage":"cleanup","code":$failure_code}] else . end' \
      "$report_file" \
      >"$report_tmp" || cleanup_failed=true
    if test -f "$report_tmp"; then
      chmod 600 "$report_tmp"
      mv "$report_tmp" "$report_file"
      jq -c '{sourceHash, runtimeBuild, syntheticIds, model, resultSummary, testStatus, runStatus, permissions, verified, failed, notRun, cleanup}' \
        "$report_file"
    else
      printf '%s\n' '{"testStatus":"failed","failed":[{"stage":"report","code":"safe_report_unavailable"}],"cleanup":"failed"}'
    fi
  else
    printf '%s\n' '{"testStatus":"not_run","failed":[{"stage":"report","code":"report_unavailable"}],"notRun":["real_ai_account_flow"],"cleanup":"not_run"}'
    exit_status=71
  fi

  rm -rf "$runtime_hash_dir"

  if [ "$cleanup_failed" = true ]; then
    printf '%s\n' "real AI E2E failed: scoped cleanup or retained-resource check" >&2
    exit 70
  fi
  exit "$exit_status"
}
trap finish EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

cd "$project_dir"
if ! compose config --quiet >/dev/null 2>&1; then
  fail "real AI E2E failed: required provider config, secret file, or subnet is invalid" 3
fi
compose_environment="$(compose config --environment 2>/dev/null)" \
  || fail "real AI E2E failed: Compose environment capture failed" 3
test -n "$compose_environment" \
  || fail "real AI E2E failed: Compose environment is empty" 3
unset compose_environment
compose_runtime_data="$(compose config --format json 2>/dev/null | jq -ce '
  {
    images: {
      app: .services["e2e-app"].image,
      test: .services.e2e.image,
      frontend: .services["e2e-frontend"].image,
      backendTest: .services["backend-e2e"].image
    },
    mounts: {
      e2e: [.services.e2e.volumes[]? | {type, source, target, read_only}],
      backendTest: [.services["backend-e2e"].volumes[]? | {type, source, target, read_only}]
    },
    providerBaseUrl: .services.e2e.environment.REAL_AI_PROVIDER_BASE_URL
  }
' 2>/dev/null)" \
  || fail "real AI E2E failed: Compose service configuration is unavailable" 3
compose_image_refs="$(printf '%s' "$compose_runtime_data" | jq -c '.images')"
provider_base_url="$(printf '%s' "$compose_runtime_data" | jq -er '.providerBaseUrl')" \
  || fail "real AI E2E failed: provider endpoint is missing" 3
if ! printf '%s' "$provider_base_url" \
  | python3 "$project_dir/scripts/validate_real_ai_provider_url.py" >/dev/null 2>&1; then
  fail "real AI E2E failed: provider endpoint must be public HTTPS" 3
fi
unset provider_base_url
test_spec_source="$(realpath "$project_dir/frontend/tests/e2e/real-ai-account-flow.spec.js")"
test_config_source="$(realpath "$project_dir/frontend/playwright.real-ai.config.js")"
test_reporter_source="$(realpath "$project_dir/frontend/tests/e2e/real-ai-safe-reporter.js")"
cleanup_script_source="$(realpath "$project_dir/scripts/clear_real_ai_e2e.py")"
require_runtime_mount e2e "$test_spec_source" "/app/tests/e2e/real-ai-account-flow.spec.js" \
  && require_runtime_mount e2e "$test_config_source" "/app/playwright.real-ai.config.js" \
  && require_runtime_mount e2e "$test_reporter_source" "/app/tests/e2e/real-ai-safe-reporter.js" \
  && require_runtime_writable_mount e2e "$artifacts_dir" "/app/test-results" \
  && require_runtime_mount backendTest "$cleanup_script_source" "/app/scripts/clear_real_ai_e2e.py" \
  || fail "real AI E2E failed: mounted test source does not match this runner" 4
host_app_source_hash="$(python3 "$project_dir/scripts/hash_real_ai_tree.py" \
  "$project_dir/backend/app" 2>/dev/null)" \
  || fail "real AI E2E failed: app source hash is unavailable" 4
host_test_source_hash="$(python3 "$project_dir/scripts/hash_real_ai_tree.py" \
  "$project_dir" frontend/playwright.real-ai.config.js \
  frontend/tests/e2e/real-ai-account-flow.spec.js \
  frontend/tests/e2e/real-ai-safe-reporter.js \
  scripts/clear_real_ai_e2e.py 2>/dev/null)" \
  || fail "real AI E2E failed: test source hash is unavailable" 4
test "$host_app_source_hash" = "$app_source_hash" \
  || fail "real AI E2E failed: app source does not match the build record" 4
test "$host_test_source_hash" = "$test_source_hash" \
  || fail "real AI E2E failed: mounted test source does not match the build record" 4
unset host_app_source_hash host_test_source_hash
actual_app_image_id="$(service_image_id app)" \
  || fail "real AI E2E failed: cached app image is unavailable" 4
actual_test_image_id="$(service_image_id test)" \
  || fail "real AI E2E failed: cached test image is unavailable" 4
actual_frontend_image_id="$(service_image_id frontend)" \
  || fail "real AI E2E failed: cached frontend image is unavailable" 4
actual_backend_test_image_id="$(service_image_id backendTest)" \
  || fail "real AI E2E failed: cached backend test image is unavailable" 4
test "$actual_app_image_id" = "$app_image_id" \
  || fail "real AI E2E failed: app image ID does not match the build record" 4
test "$actual_test_image_id" = "$test_image_id" \
  || fail "real AI E2E failed: test image ID does not match the build record" 4
test "$actual_frontend_image_id" = "$frontend_image_id" \
  || fail "real AI E2E failed: frontend image ID does not match the build record" 4
test "$actual_backend_test_image_id" = "$backend_test_image_id" \
  || fail "real AI E2E failed: backend test image ID does not match the build record" 4
image_tree_hash "$app_image_id" "/app/backend/app" appSource \
  || fail "real AI E2E failed: app image source tree is unavailable" 4
actual_app_source_hash="$tree_hash"
image_tree_hash "$frontend_image_id" "/usr/share/nginx/html" frontendDist \
  || fail "real AI E2E failed: frontend distribution tree is unavailable" 4
actual_frontend_dist_hash="$tree_hash"
test "$actual_app_source_hash" = "$app_source_hash" \
  || fail "real AI E2E failed: app image source does not match the build record" 4
test "$actual_frontend_dist_hash" = "$frontend_dist_hash" \
  || fail "real AI E2E failed: frontend distribution does not match the build record" 4
unset compose_runtime_data compose_image_refs actual_app_image_id actual_test_image_id
unset actual_frontend_image_id actual_backend_test_image_id
unset actual_app_source_hash actual_frontend_dist_hash tree_hash

runtime_started=true
if ! compose up --detach --wait --no-build --pull never e2e-frontend >/dev/null 2>&1; then
  fail "real AI E2E failed: cached isolated services did not become ready" 5
fi
if ! compose run --rm --no-deps --pull never e2e >/dev/null 2>&1; then
  fail "real AI E2E failed: sanitized browser flow report is available" 1
fi
