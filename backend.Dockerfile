# syntax=docker/dockerfile:1.7

FROM python:3.12-slim AS production-deps

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    VIRTUAL_ENV=/opt/venv

RUN python -m venv "$VIRTUAL_ENV"
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

COPY backend/requirements.lock /tmp/requirements.lock
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r /tmp/requirements.lock

FROM production-deps AS test-deps

COPY backend/requirements-dev.lock /tmp/requirements-dev.lock
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r /tmp/requirements-dev.lock

FROM python:3.12-slim AS runtime-base

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONPATH="/app/backend" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends libarchive13t64 \
    && rm -rf /var/lib/apt/lists/*
RUN addgroup --system app && adduser --system --ingroup app app
WORKDIR /app/backend

COPY --from=production-deps /opt/venv /opt/venv
COPY scripts/wait_for_mongo.py /opt/case-library/wait_for_mongo.py
COPY scripts/start-backend.sh /usr/local/bin/start-backend
COPY scripts/ai_smoke.py /app/scripts/ai_smoke.py
COPY files/cases_seed.json /app/files/cases_seed.json
COPY files/accounts.csv /app/files/accounts.csv
COPY files/materials_seed.json /app/files/materials_seed.json
COPY files/seed/book/zrbjf-2025.md /app/files/seed/book/zrbjf-2025.md
COPY backend/app ./app

USER app
EXPOSE 8001
ENTRYPOINT ["start-backend"]
CMD ["sh", "-c", "exec python -m uvicorn app.main:app --host 0.0.0.0 --port 8001 --workers ${WEB_CONCURRENCY:-4}"]

FROM runtime-base AS runtime

FROM runtime-base AS test

USER root
COPY --from=test-deps /opt/venv /opt/venv
COPY .env.example /app/.env.example
COPY backend/tests ./tests
COPY scripts/validate_production_config.py /app/scripts/validate_production_config.py
COPY assets/学习资料md.rar /app/fixtures/学习资料md.rar
ENV PYTEST_ADDOPTS="-p no:cacheprovider"
USER app
ENTRYPOINT []
CMD ["python", "-m", "pytest", "-q"]

FROM golang:1.24-bookworm AS production-age-client

ENV GOPROXY=https://goproxy.cn,direct
RUN --mount=type=cache,target=/go/pkg/mod,sharing=locked \
    GOBIN=/out CGO_ENABLED=0 go install filippo.io/age/cmd/age-keygen@v1.3.1

FROM python:3.12-slim AS production-config-check

COPY --from=production-age-client /out/age-keygen /usr/local/bin/age-keygen
COPY scripts/validate_production_config.py /app/scripts/validate_production_config.py
ENTRYPOINT ["python", "/app/scripts/validate_production_config.py"]
