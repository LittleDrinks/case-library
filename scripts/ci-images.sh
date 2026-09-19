#!/bin/bash
# Ensure compose services run on fingerprint-current images: pull the
# fingerprint tag from GHCR, else build locally; push rebuilds and publishes
# the fingerprint tags. Fingerprints derive from compose build specs, so
# docker-compose.yml stays the single source of truth.
set -euo pipefail
project_dir="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
# Image tags and the Compose project must match whoever calls us: when
# scripts/run-e2e.sh (or Make) exports COMPOSE_PROJECT_NAME/IMAGE_PREFIX,
# reuse them so builds and runs hit the same per-checkout tags. Only a bare
# `scripts/ci-images.sh` invocation falls back to the local derivation.
# Bare invocations derive the same per-checkout identity the runners use:
# fixed prefix + normalized absolute checkout path hash.
compose_project="${COMPOSE_PROJECT_NAME:-${TEST_IMAGE_PREFIX:-case-library-test-$(printf '%s' "$(CDPATH= cd -- "$project_dir" && pwd -P)" | sha256sum | cut -c1-8)}}"
IMAGE_PREFIX="${IMAGE_PREFIX:-$compose_project}"
export IMAGE_PREFIX

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
    # CI fingerprint: conservatively covers what the build context sends.
    # .dockerignore is hashed in full (any ignore-rule change invalidates),
    # then every COPY source is walked on disk hashing content, relative
    # path, file mode and symlink targets — matching Docker's context
    # semantics (docs.docker.com/build/concepts/context/), where cache
    # invalidation keys on content plus metadata. Pruned cache dirs mirror
    # the repo .dockerignore; anything not pruned but ignored still
    # invalidates conservatively, which is safe (never stale, at worst
    # extra rebuilds).
    if test -f "$project_dir/.dockerignore"; then
      git -C "$project_dir" hash-object -- .dockerignore
    fi
    copy_sources "$1" | while IFS= read -r src; do
      if test -d "$project_dir/$src"; then
        # Enumerate regular files AND symlinks inside the source directory.
        # BuildKit resolves symlinks through the context, so their targets
        # must enter the fingerprint; hard-coded pruning only excludes the
        # same cache dirs the repo .dockerignore excludes — everything else
        # that is actually sent to the daemon is hashed (conservatively
        # never stale, at worst an extra rebuild).
        (cd "$project_dir/$src" && find . -type d \( -name __pycache__ -o -name node_modules -o -name .git -o -name .venv \) -prune -o \
          \( -type f -o -type l \) ! -name '*.pyc' -print0 | LC_ALL=C sort -z |
          xargs -0 -I{} sh -c 'git hash-object -- "$1"; stat -c "%a %s" "$1"; if test -L "$1"; then readlink "$1"; fi; printf "%s\n" "$1"' _ {})
      else
        git -C "$project_dir" hash-object -- "$src" || exit 1
        if test -L "$project_dir/$src"; then readlink "$project_dir/$src"; fi
        stat -c "%a %s" "$project_dir/$src" 2>/dev/null || true
        printf '%s\n' "$src"
      fi
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

local_image_is_current() {
  local svc ref fingerprint_id
  svc="$1"
  docker image inspect "$(service_image_name "$svc")" >/dev/null 2>&1 || return 1
  ref="$(image_ref "$svc")" || return 1
  fingerprint_id="$(docker image inspect "$ref" --format '{{.Id}}' 2>/dev/null || true)"
  if test -n "$fingerprint_id"; then
    test "$fingerprint_id" = "$(docker image inspect "$(service_image_name "$svc")" --format '{{.Id}}')"
    return $?
  fi
  return 1
}

try_pull() {
  local ref
  if local_image_is_current "$1"; then
    return 0
  fi
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
    # Local builds trust BuildKit's content cache: compose build compares
    # actual build-context file contents and metadata per COPY (per Docker
    # cache-invalidation semantics), so it never reuses stale layers from
    # another checkout or old source. Hand-rolled fingerprinting is CI-only.
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
