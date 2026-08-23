#!/bin/sh
set -eu

project_dir="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
marker="distribution-$(date +%s)-$$"

compose() {
  docker compose --project-directory "$project_dir" \
    --env-file "$project_dir/.env.example" "$@"
}

running_replicas() {
  compose ps -q load-app | wc -l | tr -d ' '
}

send_requests() {
  compose exec -T load-frontend sh -c '
    marker="$1"
    count="$2"
    index=0
    while [ "$index" -lt "$count" ]; do
      wget -qO- "http://127.0.0.1/api/constants?probe=$marker" >/dev/null &
      index=$((index + 1))
    done
    wait
  ' _ "$marker" "$requests"
}

upstream_count() {
  compose logs --no-color load-frontend |
    awk -v marker="$marker" '
      index($0, marker) && match($0, /upstream=[^ ]+/) {
        seen[substr($0, RSTART + 9, RLENGTH - 9)] = 1
      }
      END { print length(seen) }
    '
}

replicas="$(running_replicas)"
test "$replicas" -gt 0 || {
  echo "No running app replicas observed" >&2
  exit 1
}
requests="${DISTRIBUTION_REQUESTS:-$((replicas * 40))}"
send_requests
count="$(upstream_count)"
test "$count" -eq "$replicas" || {
  echo "Expected traffic on $replicas app replicas, observed $count" >&2
  exit 1
}
printf 'backend_replicas_observed=%s requests=%s\n' "$count" "$requests"
