#!/bin/sh
set -eu

LOCK_ROOT=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)

docker run --rm \
  -e PIP_DISABLE_PIP_VERSION_CHECK=1 \
  -v "$LOCK_ROOT/backend:/work" \
  -w /work \
  python:3.12-slim \
  sh -ceu '
    python -m pip install --quiet pip-tools==7.6.0
    pip-compile --resolver=backtracking --strip-extras --no-header --no-annotate --no-emit-index-url --output-file=requirements.lock requirements.txt
    pip-compile --resolver=backtracking --strip-extras --no-header --no-annotate --no-emit-index-url --output-file=requirements-dev.lock requirements-dev.txt
  '
