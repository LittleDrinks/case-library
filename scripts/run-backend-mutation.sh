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
mutation_dir="mutants"
report="$mutation_dir/mutmut-cicd-stats.json"
run_status="$mutation_dir/mutmut-run-status.json"
head="$(git -C "$project_dir" rev-parse HEAD 2>/dev/null || printf 'unknown')"
scope="backend/app"
forwarded_args=("$@")
completion="failed"

write_status() {
  local phase="$1" exit_code="$2" tmp="$run_status.tmp.$$"
  python3 - "$tmp" "$head" "$scope" "$phase" "$exit_code" "${forwarded_args[@]}" <<'PY'
import json
import sys

path, head, scope, phase, raw_exit, *args = sys.argv[1:]
payload = {
    "head": head,
    "scope": scope,
    "args": args,
    "status": phase,
    "exit": None if raw_exit == "null" else int(raw_exit),
}
with open(path, "w", encoding="utf-8") as stream:
    json.dump(payload, stream, ensure_ascii=False)
    stream.write("\n")
PY
  mv -f -- "$tmp" "$run_status"
}

validate_result() {
  python3 - "$report" "$mutation_dir" <<'PYTHON'
import json
import pathlib
import sys

try:
    report = json.loads(pathlib.Path(sys.argv[1]).read_text())
    required = {"total", "killed", "survived", "no_tests", "timeout"}
    if not isinstance(report, dict) or not required <= report.keys():
        raise ValueError("missing mutation counts")
    if any(type(report[key]) is not int or report[key] < 0 for key in required):
        raise ValueError("invalid mutation counts")
    values = []
    root = pathlib.Path(sys.argv[2])
    for path in root.glob("app/**/*.meta"):
        if not path.relative_to(root).with_suffix("").is_file():
            continue
        metadata = json.loads(path.read_text())["exit_code_by_key"]
        if not isinstance(metadata, dict):
            raise ValueError("invalid mutation metadata")
        values.extend(metadata.values())
    if any(value is not None and type(value) is not int for value in values):
        raise ValueError("invalid mutation status")
    if report["total"] != len(values):
        raise ValueError("report and metadata totals differ")
except (OSError, ValueError, TypeError, KeyError) as error:
    print(f"Invalid mutation result: {error}", file=sys.stderr)
    raise SystemExit(1)
if not values or any(value is None or value == 2 for value in values):
    raise SystemExit(2)
PYTHON
}

cleanup() {
  local status=$?
  trap - EXIT
  trap '' INT TERM HUP
  if test -n "$mutation_pid"; then
    kill -TERM -- "-$mutation_pid" 2>/dev/null || true
    wait "$mutation_pid" 2>/dev/null || true
  fi
  for path in "${created_links[@]}"; do rm -- "$path"; done
  write_status "$completion" "$status" || true
  exit "$status"
}

trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
trap 'exit 129' HUP

# Invalidate only the owned report after the lock is held. Existing mutant
# metadata remains resumable; an initialization failure cannot expose an old success.
rm -f -- "$report"
mkdir -p "$mutation_dir"
write_status running null

for path in files scripts .env.example; do
  if test -e "$path" || test -L "$path"; then
    echo "Mutation fixture path already exists: backend/$path" >&2
    exit 2
  fi
  ln -s "../$path" "$path"
  created_links+=("$path")
done

status=0
setsid python3 -m mutmut run --max-children 1 "${forwarded_args[@]}" &
mutation_pid=$!
wait "$mutation_pid" || status=$?
mutation_pid=""

if test "$status" -ne 0; then
  completion=failed
  write_status "$completion" "$status"
  exit "$status"
fi

export_status=0
python3 -m mutmut export-cicd-stats || export_status=$?
validation_status=0
validate_result || validation_status=$?
if test "$export_status" -ne 0; then
  status="$export_status"
  rm -f -- "$report"
elif test "$validation_status" -eq 2; then
  status=3
  completion=partial
elif test "$validation_status" -ne 0; then
  status=1
  rm -f -- "$report"
else
  completion=completed
fi
write_status "$completion" "$status"
exit "$status"
