#!/bin/bash
set -euo pipefail

project_dir="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$project_dir/backend"
exec 9>.mutation.lock
flock -n 9 || { echo "Backend mutation testing is already running" >&2; exit 2; }

# Mutmut keeps app's import name but adds a mutants/ directory. Preserve the
# repository-relative paths used by seed loaders and operational contract tests.
created_links=()
mutation_pid=""
cleanup() {
  local status=$?
  trap - EXIT INT TERM HUP
  if test -n "$mutation_pid"; then
    kill -TERM -- "-$mutation_pid" 2>/dev/null || true
    wait "$mutation_pid" 2>/dev/null || true
  fi
  for path in "${created_links[@]}"; do rm -- "$path"; done
  exit "$status"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
trap 'exit 129' HUP
for path in files scripts .env.example; do
  if test -e "$path" || test -L "$path"; then
    echo "Mutation fixture path already exists: backend/$path" >&2
    exit 2
  fi
  ln -s "../$path" "$path"
  created_links+=("$path")
done

status=0
setsid python3 -m mutmut run --max-children 1 "$@" &
mutation_pid=$!
wait "$mutation_pid" || status=$?
mutation_pid=""
python3 -m mutmut export-cicd-stats
exit "$status"
