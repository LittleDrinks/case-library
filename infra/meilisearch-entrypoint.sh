#!/bin/sh
set -eu

MEILI_MASTER_KEY="$(cat /run/secrets/meili_master_key)"
export MEILI_MASTER_KEY
exec /bin/meilisearch "$@"
