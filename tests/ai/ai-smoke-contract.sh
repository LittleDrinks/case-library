#!/bin/sh
set -eu

grep -q '^ai-smoke:' Makefile
grep -Fq 'scripts/run-ai-smoke.sh' Makefile
grep -Fq 'compose exec -T' scripts/run-ai-smoke.sh
grep -Fq 'python /app/scripts/ai_smoke.py' scripts/run-ai-smoke.sh
grep -Fq "printf '%s\\n' \"\$password\"" scripts/run-ai-smoke.sh
grep -Fq 'unset AI_SMOKE_PASSWORD' scripts/run-ai-smoke.sh
if grep -Eq '(^|[[:space:]])(source|\.)[[:space:]]+.*\.env' scripts/run-ai-smoke.sh; then
  echo "AI smoke runner must not source an environment file" >&2
  exit 1
fi
if grep -Eq '(curl[[:space:]].*(-v|--verbose)|set[[:space:]]+-x)' scripts/run-ai-smoke.sh; then
  echo "AI smoke runner must not enable verbose secret logging" >&2
  exit 1
fi
if grep -Eq 'python .*\$password' scripts/run-ai-smoke.sh; then
  echo "AI smoke runner must not pass the password as an argument" >&2
  exit 1
fi
