#!/bin/sh
set -eu

version="${1:?version is required}"
output_dir="${2:?output directory is required}"
: "${CASE_LIBRARY_APP_IMAGE:?CASE_LIBRARY_APP_IMAGE is required}"
: "${CASE_LIBRARY_FRONTEND_IMAGE:?CASE_LIBRARY_FRONTEND_IMAGE is required}"
: "${CASE_LIBRARY_MONGO_INIT_IMAGE:?CASE_LIBRARY_MONGO_INIT_IMAGE is required}"
: "${CASE_LIBRARY_MEILISEARCH_IMAGE:?CASE_LIBRARY_MEILISEARCH_IMAGE is required}"

printf '%s\n' "$version" | grep -Eq '^v[0-9]+\.[0-9]+\.[0-9]+-pre-alpha\.[0-9]+$' || {
  echo "Version must be vX.Y.Z-pre-alpha.N" >&2
  exit 1
}

project_dir="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
temporary="$(mktemp -d)"
trap 'rm -rf "$temporary"' EXIT HUP INT TERM
mkdir -p "$output_dir"
cp "$project_dir/deploy/release/compose.yaml" "$temporary/compose.yaml"
cp "$project_dir/deploy/release/.env.example" "$temporary/.env.example"
cp "$project_dir/deploy/release/update.sh" "$temporary/update.sh"
chmod 755 "$temporary/update.sh"
printf '%s\n' \
  "CASE_LIBRARY_RELEASE_VERSION=$version" \
  "CASE_LIBRARY_APP_IMAGE=$CASE_LIBRARY_APP_IMAGE" \
  "CASE_LIBRARY_FRONTEND_IMAGE=$CASE_LIBRARY_FRONTEND_IMAGE" \
  "CASE_LIBRARY_MONGO_INIT_IMAGE=$CASE_LIBRARY_MONGO_INIT_IMAGE" \
  "CASE_LIBRARY_MEILISEARCH_IMAGE=$CASE_LIBRARY_MEILISEARCH_IMAGE" > "$temporary/images.env"
tar -C "$temporary" -czf "$output_dir/case-library-deploy.tar.gz" .
cp "$temporary/update.sh" "$output_dir/update.sh"
(cd "$output_dir" && sha256sum case-library-deploy.tar.gz update.sh > checksums.txt)
