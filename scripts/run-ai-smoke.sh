#!/bin/sh
set -eu

project_dir="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
terminal_hidden=false
cd "$project_dir"

compose() {
  docker compose "$@"
}

restore_terminal() {
  if [ "$terminal_hidden" = true ]; then
    stty echo
    printf '\n' >&2
  fi
}

app_environment() {
  compose exec -T app python -c \
    'import os; print(os.environ.get("APP_ENV", ""))' 2>/dev/null
}

read_password() {
  if [ "${AI_SMOKE_PASSWORD+x}" = x ]; then
    password="$AI_SMOKE_PASSWORD"
  elif [ -t 0 ]; then
    printf 'AI smoke password: ' >&2
    terminal_hidden=true
    stty -echo
    IFS= read -r password
    stty echo
    terminal_hidden=false
    printf '\n' >&2
  else
    IFS= read -r password || password=""
  fi
}

run_smoke() {
  printf '%s\n' "$password" |
    compose exec -T -e AI_SMOKE_USERNAME="$username" \
      -e AI_SMOKE_APP_URL=http://frontend app python /app/scripts/ai_smoke.py
}

trap restore_terminal EXIT INT TERM
environment="$(app_environment)" || {
  echo "AI smoke failed: app is not running" >&2
  exit 1
}
username="${AI_SMOKE_USERNAME:-}"
password=""
if [ "$environment" = demo ] && [ -z "$username" ] && [ "${AI_SMOKE_PASSWORD+x}" != x ]; then
  username=admin
  password=admin123
else
  test -n "$username" || {
    echo "AI smoke failed: AI_SMOKE_USERNAME is required" >&2
    exit 1
  }
  read_password
fi
unset AI_SMOKE_PASSWORD
test -n "$password" || {
  echo "AI smoke failed: password is required" >&2
  exit 1
}
run_smoke
password=""
