#!/bin/sh
set -eu

project_dir="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
release_dir="$project_dir/deploy/release"
temporary="$(mktemp -d)"
trap 'rm -rf "$temporary"' EXIT HUP INT TERM

for workflow in \
  "$project_dir/.github/workflows/ci.yml" \
  "$project_dir/.github/workflows/release.yml"
do
  ruby -e 'require "yaml"; YAML.load_file(ARGV.fetch(0))' "$workflow"
done
sh -n "$release_dir/update.sh"
sh -n "$project_dir/scripts/package-release.sh"
if grep -Eq '^[[:space:]]*build:' "$release_dir/compose.yaml"; then
  echo "Release Compose must not build images" >&2
  exit 1
fi

config="$(
  docker compose \
    --env-file "$project_dir/.env.example" \
    --env-file "$release_dir/images.env.example" \
    -f "$release_dir/compose.yaml" \
    config
)"
for service in \
  mongo1 mongo2 mongo3 mongo-init minio meilisearch search-init search-worker app frontend
do
  printf '%s\n' "$config" | grep -qx "  $service:"
done
for image in app frontend mongo-init meilisearch; do
  printf '%s\n' "$config" | grep -q "ghcr.io/littledrinks/case-library-$image:latest"
done
printf '%s\n' "$config" | grep -q 'service_completed_successfully'
printf '%s\n' "$config" | grep -q 'source: mongo1_data'
printf '%s\n' "$config" | grep -q 'source: minio_data'
printf '%s\n' "$config" | grep -q 'source: meili_data'
ci="$project_dir/.github/workflows/ci.yml"
release_workflow="$project_dir/.github/workflows/release.yml"
grep -Fq 'workflow_call:' "$ci"
for job in config backend-test frontend-test e2e; do
  grep -Fq "  $job:" "$ci"
done
for command in 'make config' 'make test-backend' 'make test-frontend' 'make e2e'; do
  grep -Fq "$command" "$ci"
done
if grep -Eq 'docker compose .* (backend-test|frontend-test)' "$ci"; then
  echo "CI must invoke test stages through Make targets" >&2
  exit 1
fi
grep -Fq 'E2E_ARTIFACT_DIR:' "$ci"
grep -Fq 'actions/upload-artifact@v4' "$ci"
grep -Fq 'if: failure()' "$ci"
grep -Fq 'actions: read' "$release_workflow"
grep -Fq 'packages: write' "$release_workflow"
grep -Fq 'git fetch origin main:refs/remotes/origin/main --depth=1' "$release_workflow"
grep -Fq 'head_sha=$RELEASE_SHA' "$release_workflow"
grep -Fq '.head_branch == "main"' "$release_workflow"
grep -Fq '.conclusion == "success"' "$release_workflow"
grep -Fq -- '-alpha\.' "$release_workflow"
grep -Fq 'alpha-v\1/' "$release_workflow"
grep -Fq '"$DISPLAY_NAME"' "$release_workflow"
grep -Fq 'org.opencontainers.image.source' "$release_workflow"
for image in app frontend mongo_init meilisearch; do
  grep -Fq "steps.images.outputs.$image" "$release_workflow"
done

digest="sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
CASE_LIBRARY_APP_IMAGE="ghcr.io/littledrinks/case-library-app@$digest" \
CASE_LIBRARY_FRONTEND_IMAGE="ghcr.io/littledrinks/case-library-frontend@$digest" \
CASE_LIBRARY_MONGO_INIT_IMAGE="ghcr.io/littledrinks/case-library-mongo-init@$digest" \
CASE_LIBRARY_MEILISEARCH_IMAGE="ghcr.io/littledrinks/case-library-meilisearch@$digest" \
  "$project_dir/scripts/package-release.sh" v2.0.0-alpha.1 "$temporary/release"

test -f "$temporary/release/case-library-deploy.tar.gz"
test -f "$temporary/release/update.sh"
(cd "$temporary/release" && sha256sum -c checksums.txt)
tar -tzf "$temporary/release/case-library-deploy.tar.gz" | grep -qx './compose.yaml'
tar -tzf "$temporary/release/case-library-deploy.tar.gz" | grep -qx './images.env'
tar -tzf "$temporary/release/case-library-deploy.tar.gz" | grep -qx './update.sh'

mkdir -p "$temporary/fake-bin"
cat > "$temporary/fake-bin/curl" <<'EOF'
#!/bin/sh
set -eu
url=""
output=""
while test "$#" -gt 0; do
  case "$1" in
    --output) output="$2"; shift 2 ;;
    http*) url="$1"; shift ;;
    *) shift ;;
  esac
done
printf '%s\n' "$url" >> "$CURL_LOG"
case "$url" in
  *checksums.txt) cp "$RELEASE_FIXTURE/checksums.txt" "$output" ;;
  *) cp "$RELEASE_FIXTURE/case-library-deploy.tar.gz" "$output" ;;
esac
EOF
cat > "$temporary/fake-bin/docker" <<'EOF'
#!/bin/sh
printf '%s\n' "$*" >> "$DOCKER_LOG"
EOF
chmod 755 "$temporary/fake-bin/curl" "$temporary/fake-bin/docker"

install_run() {
  selector="$1" root="$2"
  mkdir -p "$root"
  cp "$release_dir/update.sh" "$root/update.sh"
  : > "$temporary/curl.log"; : > "$temporary/docker.log"
  PATH="$temporary/fake-bin:$PATH" RELEASE_FIXTURE="$temporary/release" \
    CURL_LOG="$temporary/curl.log" DOCKER_LOG="$temporary/docker.log" \
    "$root/update.sh" "$selector"
}
assert_installed() {
  root="$1" log="$2"
  grep -Eq '^APP_SECRET=.{64}$' "$root/.env"
  grep -Eq '^MINIO_ROOT_PASSWORD=.{64}$' "$root/.env"
  grep -Fq "CASE_LIBRARY_RELEASE_VERSION=v2.0.0-alpha.1" "$root/images.env"
  grep -Fq 'config --quiet' "$log"
  grep -Fq 'pull' "$log"
  startup_command='up -d --wait --force-recreate production-config-check mongo-init'
  startup_command="$startup_command meilisearch search-init search-worker app frontend"
  grep -Fq "$startup_command" "$log"
}
install_run latest "$temporary/server"
assert_installed "$temporary/server" "$temporary/docker.log"
grep -Fq 'releases/latest/download/case-library-deploy.tar.gz' "$temporary/curl.log"
install_run v2.0.0-alpha.1 "$temporary/server-selector"
assert_installed "$temporary/server-selector" "$temporary/docker.log"
grep -Fq 'releases/download/v2.0.0-alpha.1/case-library-deploy.tar.gz' "$temporary/curl.log"
grep -Fq 'releases/download/v2.0.0-alpha.1/checksums.txt' "$temporary/curl.log"
if grep -Fq 'releases/latest/download' "$temporary/curl.log"; then
  echo "Explicit selector must not use the latest download path" >&2
  exit 1
fi

mkdir -p "$temporary/server-bad"
cp "$release_dir/update.sh" "$temporary/server-bad/update.sh"
if PATH="$temporary/fake-bin:$PATH" RELEASE_FIXTURE="$temporary/release" \
  CURL_LOG="$temporary/curl.log" DOCKER_LOG="$temporary/docker-bad.log" \
  "$temporary/server-bad/update.sh" v2.0.0 2>/dev/null; then
  echo "update.sh must reject non-alpha selectors" >&2
  exit 1
fi
test ! -s "$temporary/docker-bad.log"
