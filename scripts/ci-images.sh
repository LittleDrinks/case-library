#!/bin/bash
# Ensure compose services run on fingerprint-current images: pull the
# fingerprint tag from GHCR, else build locally; push rebuilds and publishes
# the fingerprint tags. Fingerprints derive from compose build specs, so
# docker-compose.yml stays the single source of truth.
set -euo pipefail
project_dir="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
compose_project="case-library-v2"

compose() {
  docker compose --project-name "$compose_project" \
    --env-file "$project_dir/.env.example" --profile test --profile e2e "$@"
}

registry() {
  printf 'ghcr.io/%s' "$(printf '%s' "${GITHUB_REPOSITORY:-LittleDrinks/case-library}" | tr '[:upper:]' '[:lower:]')"
}

docker_login() {
  if test -n "${GITHUB_TOKEN:-}"; then
    printf '%s' "$GITHUB_TOKEN" | docker login ghcr.io -u "${GITHUB_ACTOR:-ci}" --password-stdin >/dev/null
  fi
}

service_field() {
  printf '%s' "$config_json" | jq -r --arg s "$1" "$2"
}

service_build_spec() {
  service_field "$1" '.services[$s].build // empty | "\(.dockerfile)|\(.target // "")"'
}

service_image_name() {
  local image
  image="$(service_field "$1" '.services[$s].image // empty')"
  printf '%s' "${image:-$compose_project-$1}"
}

image_key() {
  local base
  base="$(basename "$1")"
  base="${base%.Dockerfile}"
  printf '%s' "${base}${2:+-$2}"
}

copy_sources() {
  awk '
    /^#/ { next }
    { while (sub(/\\$/, "")) { if ((getline nxt) <= 0) break; $0 = $0 nxt } }
    $1 == "COPY" || $1 == "ADD" {
      for (i = 2; i < NF; i++)
        if ($i ~ /\$/) { printf "unsupported COPY source: %s\n", $i > "/dev/stderr"; exit 1 }
        else if ($i !~ /^--/ && $i !~ /^\//) print $i
    }
  ' "$1"
}

fingerprint() {
  {
    printf '%s\n' "$2"
    cat "$1"
    copy_sources "$1" | while IFS= read -r src; do
      git -C "$project_dir" ls-files -s -- "$src" || exit 1
    done
  } | sha256sum | cut -d' ' -f1
}

image_ref() {
  local spec dockerfile target
  spec="$(service_build_spec "$1")"
  test -n "$spec" || return 1
  dockerfile="${spec%%|*}" target="${spec#*|}"
  printf '%s/%s:%s' "$(registry)" "$(image_key "$dockerfile" "$target")" \
    "$(fingerprint "$project_dir/$dockerfile" "$target")"
}

try_pull() {
  local ref
  docker image inspect "$(service_image_name "$1")" >/dev/null 2>&1 && return 0
  ref="$(image_ref "$1")" || return 1
  docker pull --quiet "$ref" && docker tag "$ref" "$(service_image_name "$1")"
}

pull_missed() {
  local status_dir="$1" svc
  shift
  for svc in "$@"; do
    ( try_pull "$svc" && : > "$status_dir/$svc" ) >/dev/null &
  done
  wait
  for svc in "$@"; do test -f "$status_dir/$svc" || printf '%s\n' "$svc"; done
}

ensure() {
  local missed status_dir
  if test -z "${CI:-}"; then
    compose build "$@"
    return 0
  fi
  init_config
  docker_login
  status_dir="$(mktemp -d)"
  missed="$(pull_missed "$status_dir" "$@")"
  rm -rf "$status_dir"
  test -z "$missed" || {
    printf '[ci-images] fingerprint miss, building locally:%s\n' " $missed" >&2
    compose build $missed
  }
}

push_ref() {
  local ref="$1" attempt
  for attempt in 1 2 3; do
    if docker push "$ref"; then return 0; fi
    printf '[ci-images] push attempt %s failed for %s, retrying\n' "$attempt" "$ref" >&2
    sleep 5
  done
  return 1
}

push() {
  init_config
  docker_login
  compose build "$@"
  local svc ref
  for svc in "$@"; do
    ref="$(image_ref "$svc")"
    docker tag "$(service_image_name "$svc")" "$ref"
    push_ref "$ref"
  done
}

init_config() {
  config_json="$(compose config --format json)"
}

command="${1:-}"
shift || true
case "$command" in
  ensure) ensure "$@" ;;
  push) push "$@" ;;
  fingerprint) init_config; image_ref "$1" ;;
  *) echo "Usage: scripts/ci-images.sh ensure|push <service>... | fingerprint <service>" >&2; exit 2 ;;
esac
