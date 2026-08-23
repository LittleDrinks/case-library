#!/bin/sh
set -eu

project_dir="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
marker="upstream-keepalive-$(date +%s)-$$"

compose() {
  docker compose --project-directory "$project_dir" \
    --env-file "$project_dir/.env.example" "$@"
}

run_probe() {
  compose --profile load run --rm --no-deps -T \
    -e KEEPALIVE_PROBE="$marker" \
    -e KEEPALIVE_VUS="${KEEPALIVE_VUS:-1000}" \
    -e KEEPALIVE_IDLE_SECONDS=5 \
    -e KEEPALIVE_REUSE_CYCLES=2 \
    -v "$project_dir/tests/load:/tests:ro" \
    load run /tests/upstream-keepalive.js
}

probe_counts() {
  compose --profile load logs --no-color load-frontend | awk -v marker="$marker" '
    index($0, marker) && /recv\(\) failed \(104: Connection reset by peer\)/ { reset++ }
    index($0, marker) && /upstream server temporarily disabled/ { disabled++ }
    index($0, marker) && /no live upstreams/ { no_live++ }
    index($0, marker) && match($0, /status=[0-9]+/) {
      responses++
      if (substr($0, RSTART + 7, 1) == "5") server_errors++
    }
    index($0, marker) && match($0, /upstream=[0-9.]+:[0-9]+/) {
      peers[substr($0, RSTART + 9, RLENGTH - 9)] = 1
    }
    END {
      print responses + 0, server_errors + 0, reset + 0, disabled + 0, no_live + 0, length(peers)
    }
  '
}

replicas="$(compose --profile load ps -q load-app | wc -l | tr -d ' ')"
test "$replicas" -eq 4 || {
  echo "Expected 4 running load-app replicas, observed $replicas" >&2
  exit 1
}

if run_probe; then
  probe_status=0
else
  probe_status=$?
fi

set -- $(probe_counts)
printf 'responses=%s 5xx=%s reset=%s disabled=%s no_live=%s peers=%s\n' \
  "$1" "$2" "$3" "$4" "$5" "$6"
test "$probe_status" -eq 0
test "$1" -gt 0
test "$2" -eq 0
test "$3" -eq 0
test "$4" -eq 0
test "$5" -eq 0
test "$6" -eq "$replicas"
