#!/bin/sh
set -eu

python /opt/case-library/wait_for_mongo.py
exec "$@"
