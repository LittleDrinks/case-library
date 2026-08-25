#!/bin/sh
set -eu

root="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
asset_name=case-library-deploy.tar.gz
checksum_name=checksums.txt

fail() {
  printf '%s\n' "$1" >&2
  exit 1
}

fetch() {
  url="$1"
  destination="$2"
  if command -v curl >/dev/null 2>&1; then
    curl --fail --location --silent --show-error "$url" --output "$destination"
  elif command -v wget >/dev/null 2>&1; then
    wget -qO "$destination" "$url"
  else
    fail "curl or wget is required"
  fi
}

random_hex() {
  od -An -N32 -tx1 /dev/urandom | tr -d ' \n'
}

write_environment() {
  umask 077
  app_secret="$(random_hex)"
  meili_key="$(random_hex)"
  minio_password="$(random_hex)"
  printf '%s\n' \
    'APP_ENV=demo' 'ENABLE_DEMO_SEED=true' 'MONGODB_DB_NAME=case_library_v3' \
    'MONGODB_MAX_POOL_SIZE=100' 'FRONTEND_BIND_ADDRESS=127.0.0.1' \
    'FRONTEND_PORT=8080' 'API_PORT=8001' 'WEB_CONCURRENCY=4' \
    'SESSION_COOKIE_SECURE=false' 'SESSION_TTL_SECONDS=43200' \
    "APP_SECRET=$app_secret" "MEILI_MASTER_KEY=$meili_key" 'AI_BASE_URL=' \
    'AI_API_KEY=' 'AI_MODELS=' 'AI_DEFAULT_MODEL=' 'AI_TIMEOUT_SECONDS=60' \
    'MINIO_ROOT_USER=case-library' "MINIO_ROOT_PASSWORD=$minio_password" \
    'OBJECT_STORE_BUCKET=case-library' > "$root/.env"
}

copy_file() {
  source="$1"
  destination="$2"
  mode="$3"
  cp "$source" "$destination.new"
  chmod "$mode" "$destination.new"
  mv "$destination.new" "$destination"
}

install_bundle() {
  bundle_dir="$1"
  for file in compose.yaml images.env .env.example update.sh; do
    test -f "$bundle_dir/$file" || fail "Release bundle is missing $file"
  done
  copy_file "$bundle_dir/compose.yaml" "$root/compose.yaml" 644
  copy_file "$bundle_dir/images.env" "$root/images.env" 600
  copy_file "$bundle_dir/.env.example" "$root/.env.example" 600
  copy_file "$bundle_dir/update.sh" "$root/update.sh" 755
}

release_path() {
  selector="${1:-latest}"
  test "$selector" = latest && {
    printf '%s\n' releases/latest/download
    return
  }
  printf '%s\n' "$selector" | grep -Eq '^v[0-9]+\.[0-9]+\.[0-9]+-pre-alpha\.[0-9]+$' || fail "Use latest or vX.Y.Z-pre-alpha.N"
  printf '%s\n' "releases/download/$selector"
}

compose() {
  docker compose --env-file "$root/.env" --env-file "$root/images.env" -f "$root/compose.yaml" "$@"
}

command -v docker >/dev/null 2>&1 || fail "Docker Engine with Compose is required"
command -v sha256sum >/dev/null 2>&1 || fail "sha256sum is required"
release="$(release_path "${1:-latest}")"
temporary="$(mktemp -d)"
trap 'rm -rf "$temporary"' EXIT HUP INT TERM
base_url="https://github.com/LittleDrinks/case-library/$release"
fetch "$base_url/$asset_name" "$temporary/$asset_name"
fetch "$base_url/$checksum_name" "$temporary/$checksum_name"
(cd "$temporary" && grep "  $asset_name\$" "$checksum_name" | sha256sum -c -)
mkdir "$temporary/bundle"
tar -xzf "$temporary/$asset_name" -C "$temporary/bundle"
install_bundle "$temporary/bundle"
test -f "$root/.env" || write_environment
compose config --quiet
compose pull
compose up -d --wait --force-recreate production-config-check mongo-init meilisearch search-init search-worker app frontend
version="$(sed -n 's/^CASE_LIBRARY_RELEASE_VERSION=//p' "$root/images.env")"
printf 'Case Library %s is ready.\n' "${version:-unknown}"
