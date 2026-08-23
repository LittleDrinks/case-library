#!/bin/sh
set -eu

project_dir="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"

compose() {
  docker compose --project-directory "$project_dir" \
    --env-file "$project_dir/.env.example" "$@"
}

replicas="$(compose ps -q load-app | wc -l | tr -d ' ')"
test "$replicas" -gt 0
minimum_basis_points="$((8000 / replicas))"

compose logs --no-color load-frontend | awk \
  -v expected="$replicas" -v minimum="$minimum_basis_points" '
    index($0, "probe=") == 0 && index($0, "load_marker=catalog-gate") == 0 && match($0, /status=[0-9]+/) {
      status = substr($0, RSTART + 7, RLENGTH - 7)
      responses += 1
      if (status >= 500) server_errors += 1
    }
    index($0, "probe=") == 0 && index($0, "load_marker=catalog-gate") == 0 && match($0, /upstream=[^ ]+/) {
      address = substr($0, RSTART + 9, RLENGTH - 9)
      sub(/,$/, "", address)
      if (address !~ /:[0-9]+$/) next
      counts[address] += 1
      total += 1
    }
    END {
      printf "nginx_responses=%d nginx_5xx=%d\n", responses, server_errors
      if (!total) {
        print "No upstream requests observed" > "/dev/stderr"
        exit 1
      }
      for (address in counts) {
        basis_points = int(counts[address] * 10000 / total)
        printf "upstream=%s requests=%d share=%.2f%%\n", address, counts[address], basis_points / 100
        if (basis_points < minimum) failed = 1
      }
      if (server_errors) failed = 1
      if (length(counts) != expected) {
        printf "Expected %d upstreams, observed %d\n", expected, length(counts) > "/dev/stderr"
        failed = 1
      }
      if (failed) exit 1
    }
  '
