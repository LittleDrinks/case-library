#!/bin/sh
set -eu

compose() {
  docker compose --env-file .env.example "$@"
}

service_config() {
  echo "$config" | awk -v service="  $1:" '
    $0 == service { selected = 1 }
    selected && $0 ~ /^  [[:alnum:]_-]+:$/ && $0 != service { exit }
    selected { print }
  '
}

services="$(compose config --services)"
config="$(compose config)"
e2e_config="$(compose --profile e2e config)"
load_config="$(compose --profile load config)"
restore_config="$(compose --profile restore config)"
ops_config="$(compose --profile ops config)"
production_config="$(APP_ENV=production compose config)"
mixed_production_json="$(APP_ENV=Production compose config --format json)"
spaced_production_json="$(APP_ENV=' Production ' compose config --format json)"
config_check="$(service_config production-config-check)"
production_check="$(config="$production_config" service_config production-config-check)"
app_config="$(service_config app)"
frontend_config="$(service_config frontend)"
minio_config="$(service_config minio)"
meili_config="$(service_config meilisearch)"
mongo1_config="$(service_config mongo1)"
mongo2_config="$(service_config mongo2)"
mongo3_config="$(service_config mongo3)"
search_init_config="$(service_config search-init)"
search_worker_config="$(service_config search-worker)"
e2e_app_config="$(config="$e2e_config" service_config e2e-app)"
e2e_frontend_config="$(config="$e2e_config" service_config e2e-frontend)"
e2e_meili_config="$(config="$e2e_config" service_config e2e-meilisearch)"
e2e_init_config="$(config="$e2e_config" service_config e2e-search-init)"
e2e_worker_config="$(config="$e2e_config" service_config e2e-search-worker)"
backend_e2e_config="$(config="$e2e_config" service_config backend-e2e)"
load_app_config="$(config="$load_config" service_config load-app)"
load_frontend_config="$(config="$load_config" service_config load-frontend)"
load_meili_config="$(config="$load_config" service_config load-meilisearch)"
load_init_config="$(config="$load_config" service_config load-search-init)"
load_worker_config="$(config="$load_config" service_config load-search-worker)"
restore_tools_config="$(config="$restore_config" service_config restore-tools)"
backup_tools_config="$(config="$ops_config" service_config backup-tools)"

for service in app frontend meilisearch search-init search-worker minio mongo1 mongo2 mongo3 mongo-init production-config-check; do
  echo "$services" | grep -qx "$service"
done

echo "$config_check" | grep -q 'network_mode: none'
echo "$config_check" | grep -q 'APP_ENV: demo'
echo "$config_check" | grep -q 'BACKUP_AGE_RECIPIENT:'
for secret in app_secret minio_root_user minio_root_password backup_age_identity; do
  echo "$config_check" | grep -q "source: $secret"
done
for persistent_config in "$mongo1_config" "$mongo2_config" "$mongo3_config" "$meili_config" "$minio_config"; do
  echo "$persistent_config" | grep -B2 -A2 'production-config-check:' | grep -q 'service_completed_successfully'
done
grep -q 'validate_production_config.py' backend.Dockerfile
echo "$config_check" | grep -q 'image: case-library-v2-production-config-check'
echo "$config_check" | grep -q 'target: production-config-check'
echo "$production_check" | grep -q 'app_environment='
echo "$production_check" | grep -q 'test "$${app_environment}" != production'
echo "$production_check" | grep -q 'Single-host Compose does not support APP_ENV=production'
for production_json in "$mixed_production_json" "$spaced_production_json"; do
  mixed_command="$(printf '%s' "$production_json" | jq -r \
    '.services["production-config-check"].command[-1]' | sed 's/\$\$/\$/g')"
  if mixed_output="$(sh -c "$mixed_command" 2>&1)"; then
    echo "Single-host Compose accepted non-canonical production" >&2
    exit 1
  fi
  echo "$mixed_output" | grep -q 'Single-host Compose does not support APP_ENV=production'
done
grep -q 'FROM golang:1.24-bookworm AS production-age-client' backend.Dockerfile
grep -q 'GOPROXY=https://goproxy.cn,direct' backend.Dockerfile
grep -q 'COPY --from=production-age-client /out/age-keygen' backend.Dockerfile
if grep -Eq '^FROM production-age-client AS (runtime|test)$' backend.Dockerfile; then
  echo "Runtime and test stages must not inherit the age builder" >&2
  exit 1
fi
if grep -Eq '^COPY --from=production-age-client .*(runtime|test)' backend.Dockerfile; then
  echo "Runtime and test stages must not copy from the age builder" >&2
  exit 1
fi
if echo "$app_config" | grep -q 'CORS_ALLOW_ORIGINS'; then
  echo "App must not receive CORS_ALLOW_ORIGINS from Compose" >&2
  exit 1
fi

if echo "$services" | grep -qi onlyoffice; then
  echo "OnlyOffice must not be part of the deployment" >&2
  exit 1
fi

echo "$app_config" | grep -q 'host_ip: 127.0.0.1'
echo "$app_config" | grep -q 'published: "8001"'
echo "$frontend_config" | grep -q 'host_ip: 127.0.0.1'
echo "$frontend_config" | grep -q 'published: "18080"'
echo "$frontend_config" | grep -q 'edge:'
echo "$minio_config" | grep -q 'minio/minio:RELEASE.2025-09-07T16-13-09Z'
echo "$minio_config" | grep -q '/minio/health/live'
echo "$minio_config" | grep -q 'source: minio_data'
echo "$minio_config" | grep -q 'target: /data'
echo "$app_config" | grep -q 'OBJECT_STORE_ENDPOINT: minio:9000'
echo "$app_config" | grep -q 'OBJECT_STORE_BUCKET: case-library'
echo "$app_config" | grep -q 'MONGODB_DB_NAME: case_library_v3'
echo "$app_config" | grep -q '/case_library_v3?replicaSet=rs0'
echo "$app_config" | grep -q '/run/secrets/minio_root_user'
echo "$app_config" | grep -q '/run/secrets/minio_root_password'
echo "$app_config" | grep -q 'SEARCH_URL: http://meilisearch:7700'
echo "$app_config" | grep -q 'SEARCH_INDEX_UID: catalog'
echo "$app_config" | grep -q 'SEARCH_API_KEY_FILE: /run/secrets/meili_master_key'
echo "$app_config" | grep -q 'source: meili_master_key'
echo "$app_config" | grep -B2 -A2 'search-init:' | grep -q 'service_completed_successfully'
echo "$app_config" | grep -B2 -A2 'search-worker:' | grep -q 'service_started'
echo "$meili_config" | grep -q 'image: case-library-v2-meilisearch'
echo "$meili_config" | grep -q 'dockerfile: deploy/meilisearch.Dockerfile'
echo "$meili_config" | grep -q 'source: meili_data'
echo "$meili_config" | grep -q 'target: /meili_data'
echo "$meili_config" | grep -q 'source: meili_master_key'
if echo "$meili_config" | grep -q 'MEILI_MASTER_KEY:'; then
  echo "Meilisearch must receive its key through a secret file" >&2
  exit 1
fi
echo "$search_init_config" | grep -q 'app.modules.search.rebuild'
echo "$search_init_config" | grep -q 'APP_ENV: demo'
echo "$search_init_config" | grep -q 'ENABLE_DEMO_SEED: "true"'
echo "$search_worker_config" | grep -q 'app.modules.search.worker'
echo "$search_worker_config" | grep -B2 -A2 'search-init:' | grep -q 'service_completed_successfully'
echo "$e2e_app_config" | grep -q 'OBJECT_STORE_BUCKET: case-library-e2e'
echo "$e2e_app_config" | grep -q 'image: case-library-v2-e2e-app'
echo "$e2e_frontend_config" | grep -q 'image: case-library-v2-e2e-frontend'
echo "$e2e_app_config" | grep -q 'SEARCH_URL: http://e2e-meilisearch:7700'
echo "$e2e_app_config" | grep -q 'SEARCH_INDEX_UID: catalog_e2e'
echo "$e2e_meili_config" | grep -q 'image: case-library-v2-e2e-meilisearch'
echo "$e2e_meili_config" | grep -q 'source: e2e_meili_data'
echo "$e2e_init_config" | grep -q 'app.modules.search.rebuild'
echo "$e2e_init_config" | grep -q 'APP_ENV: test'
echo "$e2e_init_config" | grep -q 'ENABLE_DEMO_SEED: "true"'
echo "$e2e_worker_config" | grep -q 'app.modules.search.worker'
echo "$e2e_worker_config" | grep -B2 -A2 'e2e-search-init:' | grep -q 'service_completed_successfully'
echo "$backend_e2e_config" | grep -q 'MEILI_CONTRACT_URL: http://e2e-meilisearch:7700'
echo "$backend_e2e_config" | grep -q 'MEILI_CONTRACT_KEY_FILE: /run/secrets/meili_master_key'
echo "$backend_e2e_config" | grep -q 'source: meili_master_key'
if echo "$backend_e2e_config" | grep -Eq 'MEILI_CONTRACT_KEY[=:]'; then
  echo "Backend E2E must receive its Meilisearch key through a secret file" >&2
  exit 1
fi
echo "$load_app_config" | grep -q 'image: case-library-v2-load-app'
echo "$load_frontend_config" | grep -q 'image: case-library-v2-load-frontend'
echo "$load_app_config" | grep -q 'SEARCH_URL: http://load-meilisearch:7700'
echo "$load_app_config" | grep -q 'SEARCH_INDEX_UID: catalog_load'
echo "$load_meili_config" | grep -q 'image: case-library-v2-load-meilisearch'
echo "$load_meili_config" | grep -q 'source: load_meili_data'
echo "$load_init_config" | grep -q 'app.modules.search.rebuild'
echo "$load_init_config" | grep -q 'APP_ENV: demo'
echo "$load_init_config" | grep -q 'ENABLE_DEMO_SEED: "false"'
echo "$load_worker_config" | grep -q 'app.modules.search.worker'
echo "$load_worker_config" | grep -B2 -A2 'mongo-init:' | grep -q 'service_completed_successfully'
echo "$load_worker_config" | grep -B2 -A2 'load-meilisearch:' | grep -q 'service_healthy'
if echo "$load_worker_config" | grep -q 'load-search-init:'; then
  echo "Load worker must start only after the explicit catalog rebuild" >&2
  exit 1
fi
echo "$load_app_config" | grep -q 'ENABLE_DEMO_SEED: "false"'
if echo "$load_app_config" | grep -q 'load-search-init:'; then
  echo "Load app must not trigger an implicit catalog rebuild" >&2
  exit 1
fi
echo "$load_app_config" | grep -A1 'deploy:' | grep -q 'replicas: 4'
echo "$load_app_config" | grep -q 'MONGODB_MAX_POOL_SIZE: "10"'
echo "$load_app_config" | grep -q 'WEB_CONCURRENCY: "4"'
load_replicas="$(echo "$load_app_config" | awk '/replicas:/ { print $2; exit }')"
load_pool="$(echo "$load_app_config" | awk '/MONGODB_MAX_POOL_SIZE:/ { gsub(/"/, "", $2); print $2; exit }')"
load_workers="$(echo "$load_app_config" | awk '/WEB_CONCURRENCY:/ { gsub(/"/, "", $2); print $2; exit }')"
test "$((load_replicas * load_pool * load_workers))" -le 160
echo "$restore_tools_config" | grep -q 'restore_test:'
echo "$backup_tools_config" | grep -q 'BACKUP_AGE_RECIPIENT:'
echo "$restore_tools_config" | grep -q '/run/secrets/backup_age_identity'

if echo "$backup_tools_config" | grep -q 'backup_age_identity'; then
  echo "Backup tools must not receive the age private identity" >&2
  exit 1
fi

if echo "$restore_tools_config" | grep -q 'database:'; then
  echo "Restore tools must not join the production database network" >&2
  exit 1
fi

if echo "$restore_tools_config" | grep -q 'MONGODB_ADMIN_URI'; then
  echo "Restore tools must not receive the production Mongo URI" >&2
  exit 1
fi

if echo "$frontend_config" | grep -q 'database:'; then
  echo "Frontend must not join the database network" >&2
  exit 1
fi

if echo "$config" | grep -q 'type: bind'; then
  echo "Production services must not use bind mounts" >&2
  exit 1
fi

if echo "$app_config" | grep -q -- '--reload'; then
  echo "Production app must not use reload" >&2
  exit 1
fi

compose config --quiet
make -pn | grep -q '^COMPOSE_ENV_FILES := .*\.env.example'
make -pn | grep -q '^COMPOSE_DISABLE_ENV_FILE := 1$'
up_commands="$(make -n up)"
stop_line="$(printf '%s\n' "$up_commands" | grep -n 'stop frontend app' | cut -d: -f1)"
up_line="$(printf '%s\n' "$up_commands" | grep -n 'up --build -d --wait --force-recreate' | cut -d: -f1)"
test -n "$stop_line"
test -n "$up_line"
test "$stop_line" -lt "$up_line"
echo "$up_commands" | grep -q 'up --build -d --wait --force-recreate meilisearch search-init search-worker app frontend'
config_commands="$(make -n config)"
echo "$config_commands" | grep -qx 'docker compose config --quiet'
echo "$config_commands" | grep -qx 'make config-contract'
contract_commands="$(make -n config-contract)"
echo "$contract_commands" | grep -q -- '--env-file .env.example config --quiet'
grep -Eq 'client_max_body_size[[:space:]]+129m;' deploy/nginx.conf
grep -q -- '--excludeCollection=sessions' scripts/backup-bundle-tool.sh
grep -q -- '--excludeCollection=ai_usage' scripts/backup-bundle-tool.sh
grep -q -- '--excludeCollection=search_outbox' scripts/backup-bundle-tool.sh
grep -q -- '--excludeCollection=search_revocations' scripts/backup-bundle-tool.sh
grep -q -- '--excludeCollection=search_catalog_state' scripts/backup-bundle-tool.sh
grep -q -- '--excludeCollection=search_control' scripts/backup-bundle-tool.sh
grep -q -- '--excludeCollection=search_catalog_generation' scripts/backup-bundle-tool.sh
grep -q -- '--excludeCollection=search_worker_state' scripts/backup-bundle-tool.sh
test "$(grep -o 'search_worker_state' scripts/backup-bundle-tool.sh | wc -l | tr -d ' ')" -eq 2
test "$(grep -o 'search_worker_state' tests/failover/backup-restore.sh | wc -l | tr -d ' ')" -eq 2
grep -q 'case_snapshots' scripts/backup-bundle-tool.sh
grep -q 'age --encrypt' scripts/backup-bundle-tool.sh
grep -q 'age --decrypt' scripts/backup-bundle-tool.sh
sh tests/load/capacity-contract.sh
grep -Fq 'load-search-init python -m app.cli.bootstrap' scripts/run-load.sh
grep -Fq 'compose --profile load run --rm --no-deps --env ENABLE_DEMO_SEED=false load-search-init' scripts/run-load.sh
grep -Fq 'docker compose --project-name "$compose_project"' scripts/run-load.sh
grep -Fq 'docker volume rm "$load_meili_volume"' scripts/run-load.sh
grep -Fq 'docker compose --project-name "$compose_project"' scripts/run-e2e.sh
grep -Fq 'docker volume rm "$e2e_meili_volume"' scripts/run-e2e.sh
grep -Fq 'getmeili/meilisearch:v1.45.1' deploy/meilisearch.Dockerfile
