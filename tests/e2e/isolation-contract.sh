#!/bin/sh
# Behavior contract for tests/e2e/isolation-contract.sh's helper expectations
# and the real derivation logic shared by the runners. Everything here runs
# real shell and real docker CLI state; a failed assertion exits non-zero.
set -eu

project_dir="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
compose_file="$project_dir/docker-compose.yml"
overlay_file="$project_dir/deploy/e2e.compose.yml"
project_a=case-library-v2-e2e-iso-a
project_b=case-library-v2-e2e-iso-b

config_for() {
  project="$1"
  IMAGE_PREFIX="$project" docker compose \
    --project-name "$project" \
    --env-file "$project_dir/.env.example" --profile e2e \
    -f "$compose_file" -f "$overlay_file" config --format json
}

config_a="$(config_for "$project_a")"
config_b="$(config_for "$project_b")"

for config in "$config_a" "$config_b"; do
  printf '%s' "$config" | jq -e '
    .name != "case-library-v2" and
    ([.services[] | select(.networks.database != null)] | length) == 0 and
    ([.services[] | select(.networks.edge != null)] | length) == 0
  ' >/dev/null
done

# Distinct resource ownership between the two isolated runs.
test "$config_a" != "$config_b"
printf '%s' "$config_a" | jq -e --arg b "$project_b" '
  ([.volumes[].name] | map(startswith($b)) | any) == false and
  ([.networks[].name] | map(startswith($b)) | any) == false
' >/dev/null
printf '%s' "$config_b" | jq -e --arg a "$project_a" '
  ([.volumes[].name] | map(startswith($a)) | any) == false and
  ([.networks[].name] | map(startswith($a)) | any) == false
' >/dev/null

# No static subnets on the e2e-run networks: Docker auto-allocates unique
# address ranges, so parallel runs cannot collide.
for config in "$config_a" "$config_b"; do
  printf '%s' "$config" | jq -e '
    .networks.e2e_database.ipam.config == null and
    .networks.e2e_test.ipam.config == null
  ' >/dev/null
done

# Image tags are per-project, so one checkout cannot reuse another's stale
# local images.
for config in "$config_a" "$config_b"; do
  printf '%s' "$config" | jq -e '
    .services["e2e-app"].image == (.name + "-e2e-app") and
    .services["backend-e2e"].image == (.name + "-backend-test")
  ' >/dev/null
done

# No host ports are published by the isolated stacks.
for config in "$config_a" "$config_b"; do
  printf '%s' "$config" | jq -e '
    ([.services[] | select(.ports != null and (.ports | length) > 0)] | length) == 0
  ' >/dev/null
done

# The real derivation logic (identical expression to the runners) yields
# distinct project names for two sibling checkouts and never equals the demo
# project name.
dir_a="$project_dir"
dir_b="$(dirname "$project_dir")/iso-b"
full_a="${dir_a}-$(printf '%s' "$dir_a" | sha256sum | cut -c1-8)-e2e"
full_b="${dir_b}-$(printf '%s' "$dir_b" | sha256sum | cut -c1-8)-e2e"
test "$full_a" != "$full_b"
test "$full_a" != case-library-v2
test "$full_b" != case-library-v2
case "$full_a" in *-e2e) ;; *) echo "project name must end in -e2e" >&2; exit 1 ;; esac

# Every build service must carry an explicit per-prefix image tag.
printf '%s' "$config_a" | jq -e '
  ([.services | to_entries[] | select(.value.build != null) | select(.value.image == null)] | length) == 0
' >/dev/null

printf 'isolation-contract: projects %s and %s are independently owned\n' "$project_a" "$project_b"
