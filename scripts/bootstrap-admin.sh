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

require_production() {
  compose run --rm -T --no-deps --entrypoint sh app -eu -c \
    'test "$APP_ENV" = production && test "$ENABLE_DEMO_SEED" = false' \
    </dev/null
}

run_bootstrap() {
  compose run --rm -T --no-deps --entrypoint python app \
    -m app.cli.bootstrap_admin --username "$username" --name "$display_name"
}

if [ "$#" -ne 2 ] || [ -z "$1" ] || [ -z "$2" ]; then
  echo "Usage: $0 USERNAME NAME" >&2
  exit 2
fi

username="$1"
display_name="$2"
require_production

if [ ! -t 0 ]; then
  run_bootstrap
  exit
fi

trap restore_terminal EXIT INT TERM
printf 'Password: ' >&2
terminal_hidden=true
stty -echo
IFS= read -r password
stty echo
terminal_hidden=false
printf '\nConfirm password: ' >&2
terminal_hidden=true
stty -echo
IFS= read -r confirmation
stty echo
terminal_hidden=false
printf '\n' >&2
trap - EXIT INT TERM

if [ -z "$password" ] || [ "$password" != "$confirmation" ]; then
  echo "Passwords are empty or do not match" >&2
  exit 2
fi

printf '%s\n' "$password" | run_bootstrap
