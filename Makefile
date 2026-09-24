comma := ,
LOCAL_ENV := $(wildcard $(CURDIR)/.env)
COMPOSE_ENV_FILES := $(CURDIR)/.env.example$(if $(LOCAL_ENV),$(comma)$(LOCAL_ENV))
COMPOSE_DISABLE_ENV_FILE := 1
export COMPOSE_ENV_FILES COMPOSE_DISABLE_ENV_FILE

COMPOSE := docker compose
E2E_SPEC ?= $(SPEC)

.PHONY: up down logs config config-contract release-contract test test-backend test-frontend check-complexity check-backend-complexity check-frontend-complexity backend-e2e e2e e2e-generic e2e-agent e2e-spec ai-smoke load-smoke load-peak load-resilience load-rate load-steady load-all failover backup restore-drill lock-backend

up:
	$(COMPOSE) stop frontend app
	$(COMPOSE) up --build -d --wait --force-recreate meilisearch search-init search-worker app frontend

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f meilisearch search-init search-worker app frontend

config:
	$(COMPOSE) config --quiet
	$(MAKE) config-contract

config-contract:
	$(COMPOSE) --env-file .env.example config --quiet
	tests/failover/compose-contract.sh
	sh tests/e2e/run-e2e-contract.sh
	sh tests/ai/ai-smoke-contract.sh
	sh tests/release/release-contract.sh
	sh tests/failover/isolation-contract.sh

release-contract:
	sh tests/release/release-contract.sh

test: check-complexity
	$(COMPOSE) --env-file .env.example --profile test run --rm backend-test
	$(COMPOSE) --env-file .env.example --profile test run --rm frontend-test

test-backend: check-backend-complexity
	$(COMPOSE) --env-file .env.example --profile test run --rm backend-test

test-frontend: check-frontend-complexity
	$(COMPOSE) --env-file .env.example --profile test run --rm frontend-test

check-complexity: check-backend-complexity check-frontend-complexity


check-backend-complexity:
	$(COMPOSE) --env-file .env.example --profile test build backend-test
	$(COMPOSE) --env-file .env.example --profile test run --rm backend-test ruff check --no-cache --select C901 --config lint.mccabe.max-complexity=10 app tests

check-frontend-complexity:
	$(COMPOSE) --env-file .env.example --profile test build frontend-test
	$(COMPOSE) --env-file .env.example --profile test run --rm frontend-test npm run check:complexity

backend-e2e:
	scripts/run-e2e.sh --backend

e2e:
	scripts/run-e2e.sh $(if $(strip $(E2E_SPEC)),"$(E2E_SPEC)")

e2e-generic:
	scripts/run-e2e.sh --generic

e2e-agent:
	scripts/run-e2e.sh --agent

e2e-spec:
	test -n "$(E2E_SPEC)" || { echo "Usage: make e2e-spec SPEC=frontend/tests/e2e/<name>.spec.js" >&2; exit 2; }
	scripts/run-e2e.sh "$(E2E_SPEC)"

ai-smoke:
	scripts/run-ai-smoke.sh

load-smoke:
	scripts/run-load.sh smoke

load-peak:
	scripts/run-load.sh peak

load-resilience:
	scripts/run-load.sh resilience

load-rate:
	scripts/run-load.sh rate

load-steady:
	scripts/run-load.sh steady

load-all:
	scripts/run-load.sh reset-all
	scripts/run-load.sh smoke
	scripts/run-load.sh peak
	scripts/run-load.sh resilience
	scripts/run-load.sh rate
	scripts/run-load.sh steady

failover:
	scripts/run-failover.sh

backup:
	scripts/mongo-backup.sh

restore-drill:
	scripts/restore-drill.sh $(BACKUP)

lock-backend:
	scripts/lock-backend.sh
