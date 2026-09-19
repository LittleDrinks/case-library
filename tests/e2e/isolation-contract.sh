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

# Exercise the real entry point in same-named hidden checkouts. Docker is
# replaced only inside each private fixture; Compose config above is real.
probe_root="$(mktemp -d)"
trap 'rm -rf "$probe_root"' EXIT
probe_a="$probe_root/one/.checkout"
probe_b="$probe_root/two/.checkout"
for fixture in "$probe_a" "$probe_b"; do
  mkdir -p "$fixture/scripts" "$fixture/bin"
  for script in run-e2e.sh ci-images.sh test-database.sh; do
    cp "$project_dir/scripts/$script" "$fixture/scripts/$script"
  done
  cat > "$fixture/bin/docker" <<'SHIM'
#!/bin/sh
printf '%s|%s|%s\n' "$COMPOSE_PROJECT_NAME" "$IMAGE_PREFIX" "$*" >> "$ISOLATION_CALL_LOG"
case " $* " in *" build "*) exit 73 ;; esac
exit 0
SHIM
  chmod +x "$fixture/bin/docker"
  status=0
  (cd "$fixture" && CI= PATH="$fixture/bin:$PATH" \
    ISOLATION_CALL_LOG="$fixture/calls.log" sh scripts/run-e2e.sh --backend \
    > "$fixture/output.log" 2>&1) || status=$?
  test "$status" -eq 73 || {
    cat "$fixture/output.log" >&2
    echo "entry point must reach the injected build failure (got $status)" >&2
    exit 1
  }
  # Every Docker call must use the same exported identity; build invocation
  # must pass it explicitly to Compose as well.
  awk -F '|' '
    NR == 1 { project = $1 }
    $1 !~ /^[a-z0-9][a-z0-9_-]*$/ || $1 == "case-library-v2" { exit 1 }
    $1 != project || $2 != project { exit 1 }
    $3 ~ / build / {
      if (index($3, "--project-name " project " ") == 0) exit 1
      built = 1
    }
    END { if (!built) exit 1 }
  ' "$fixture/calls.log" || {
    echo "entry point must build with a legal, consistent test identity" >&2
    exit 1
  }
done
project_a_seen="$(head -1 "$probe_a/calls.log" | cut -d '|' -f 1)"
project_b_seen="$(head -1 "$probe_b/calls.log" | cut -d '|' -f 1)"
test "$project_a_seen" != "$project_b_seen" || {
  echo "same-named checkouts must have different project and image identities" >&2
  exit 1
}

# Every build service must carry an explicit per-prefix image tag.
printf '%s' "$config_a" | jq -e '
  ([.services | to_entries[] | select(.value.build != null) | select(.value.image == null)] | length) == 0
' >/dev/null

printf 'isolation-contract: projects %s and %s are independently owned\n' "$project_a" "$project_b"
