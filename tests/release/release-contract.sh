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
grep -Fq 'git fetch origin v2:refs/remotes/origin/v2 --depth=1' "$release_workflow"
grep -Fq 'head_sha=$RELEASE_SHA' "$release_workflow"
grep -Fq '.head_branch == "v2"' "$release_workflow"
grep -Fq '.conclusion == "success"' "$release_workflow"
grep -Fq 'pre-alpha' "$release_workflow"
grep -Fq 'org.opencontainers.image.source' "$release_workflow"
for image in app frontend mongo_init meilisearch; do
  grep -Fq "steps.images.outputs.$image" "$release_workflow"
done

digest="sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
CASE_LIBRARY_APP_IMAGE="ghcr.io/littledrinks/case-library-app@$digest" \
CASE_LIBRARY_FRONTEND_IMAGE="ghcr.io/littledrinks/case-library-frontend@$digest" \
CASE_LIBRARY_MONGO_INIT_IMAGE="ghcr.io/littledrinks/case-library-mongo-init@$digest" \
CASE_LIBRARY_MEILISEARCH_IMAGE="ghcr.io/littledrinks/case-library-meilisearch@$digest" \
  "$project_dir/scripts/package-release.sh" v0.1.0-pre-alpha.1 "$temporary/release"

test -f "$temporary/release/case-library-deploy.tar.gz"
test -f "$temporary/release/update.sh"
(cd "$temporary/release" && sha256sum -c checksums.txt)
tar -tzf "$temporary/release/case-library-deploy.tar.gz" | grep -qx './compose.yaml'
tar -tzf "$temporary/release/case-library-deploy.tar.gz" | grep -qx './images.env'
tar -tzf "$temporary/release/case-library-deploy.tar.gz" | grep -qx './update.sh'

mkdir -p "$temporary/fake-bin" "$temporary/server"
cp "$release_dir/update.sh" "$temporary/server/update.sh"
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
PATH="$temporary/fake-bin:$PATH" RELEASE_FIXTURE="$temporary/release" \
DOCKER_LOG="$temporary/docker.log" "$temporary/server/update.sh"

grep -Eq '^APP_SECRET=.{64}$' "$temporary/server/.env"
grep -Eq '^MINIO_ROOT_PASSWORD=.{64}$' "$temporary/server/.env"
grep -Fq "CASE_LIBRARY_RELEASE_VERSION=v0.1.0-pre-alpha.1" "$temporary/server/images.env"
grep -Fq 'config --quiet' "$temporary/docker.log"
grep -Fq 'pull' "$temporary/docker.log"
startup_command='up -d --wait --force-recreate production-config-check mongo-init'
startup_command="$startup_command meilisearch search-init search-worker app frontend"
grep -Fq "$startup_command" "$temporary/docker.log"
