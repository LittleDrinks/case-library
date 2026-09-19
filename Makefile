comma := ,
LOCAL_ENV := $(wildcard $(CURDIR)/.env)
COMPOSE_ENV_FILES := $(CURDIR)/.env.example$(if $(LOCAL_ENV),$(comma)$(LOCAL_ENV))
COMPOSE_DISABLE_ENV_FILE := 1
export COMPOSE_ENV_FILES COMPOSE_DISABLE_ENV_FILE

COMPOSE := docker compose
# Test-only identity: a fixed "case-library-test-" prefix plus a hash of the
# normalized absolute checkout path, so two checkouts never collide and the
# demo stack (project case-library-v2 from docker-compose.yml) is untouched.
# Exported ONLY in test targets — never globally, or `make up/down` would
# rename the demo project.
TEST_COMPOSE_ARGS = --project-name case-library-test-$(shell printf '%s' "$(CURDIR)" | sha256sum | cut -c1-8) --env-file .env.example
TEST_IMAGE_PREFIX = case-library-test-$(shell printf '%s' "$(CURDIR)" | sha256sum | cut -c1-8)
E2E_SPEC ?= $(SPEC)

.PHONY: up down logs config config-contract release-contract test test-backend test-frontend mutation-backend ensure-backend-test ensure-frontend-test backend-e2e e2e e2e-spec bdd-zh ai-smoke load-smoke load-peak load-resilience load-rate load-steady load-all failover backup restore-drill lock-backend

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
	python3 tests/e2e/backend-mutation-wrapper-probe.py
	sh tests/e2e/isolation-contract.sh
	python3 $(CURDIR)/tests/e2e/make-isolation-probe.py $(CURDIR)
	sh tests/ai/ai-smoke-contract.sh
	sh tests/release/release-contract.sh
	sh tests/failover/isolation-contract.sh

release-contract:
	sh tests/release/release-contract.sh

test: ensure-backend-test ensure-frontend-test
	IMAGE_PREFIX="$(TEST_IMAGE_PREFIX)" COMPOSE_PROJECT_NAME="$(TEST_IMAGE_PREFIX)" $(COMPOSE) $(TEST_COMPOSE_ARGS) --profile test run --rm backend-test
	IMAGE_PREFIX="$(TEST_IMAGE_PREFIX)" COMPOSE_PROJECT_NAME="$(TEST_IMAGE_PREFIX)" $(COMPOSE) $(TEST_COMPOSE_ARGS) --profile test run --rm frontend-test

ensure-backend-test:
	IMAGE_PREFIX="$(TEST_IMAGE_PREFIX)" COMPOSE_PROJECT_NAME="$(TEST_IMAGE_PREFIX)" scripts/ci-images.sh ensure backend-test

ensure-frontend-test:
	IMAGE_PREFIX="$(TEST_IMAGE_PREFIX)" COMPOSE_PROJECT_NAME="$(TEST_IMAGE_PREFIX)" scripts/ci-images.sh ensure frontend-test

test-backend: ensure-backend-test
	IMAGE_PREFIX="$(TEST_IMAGE_PREFIX)" COMPOSE_PROJECT_NAME="$(TEST_IMAGE_PREFIX)" $(COMPOSE) $(TEST_COMPOSE_ARGS) --profile test run --rm backend-test

test-frontend: ensure-frontend-test
	IMAGE_PREFIX="$(TEST_IMAGE_PREFIX)" COMPOSE_PROJECT_NAME="$(TEST_IMAGE_PREFIX)" $(COMPOSE) $(TEST_COMPOSE_ARGS) --profile test run --rm frontend-test

backend-e2e:
	scripts/run-e2e.sh --backend

# 中文 Gherkin 业务验收：在 backend-test 容器内执行 features/ 全部轻量场景，
# 生成中文可读 HTML 报告到宿主 backend/test-results/bdd-zh/（bind mount，可写）；
# 失败退出码由 compose run 原样传播。真实资源场景（search_sync.feature，标记 e2e）
# 由 backend-e2e 套件在隔离环境执行，不在此重复。
bdd-zh: ensure-backend-test
	mkdir -p backend/test-results/bdd-zh
	chmod 0777 backend/test-results/bdd-zh
	IMAGE_PREFIX="$(TEST_IMAGE_PREFIX)" COMPOSE_PROJECT_NAME="$(TEST_IMAGE_PREFIX)" $(COMPOSE) $(TEST_COMPOSE_ARGS) --profile test run --rm \
	  -v "$(CURDIR)/backend/test-results/bdd-zh:/app/backend/test-results/bdd-zh" \
	  backend-test \
	  sh -ceu 'python -m pytest tests/bdd -v -m "not e2e" \
	    --html=test-results/bdd-zh/report.html --self-contained-html \
	    --junitxml=test-results/bdd-zh/report.xml'

e2e:
	scripts/run-e2e.sh $(if $(strip $(E2E_SPEC)),"$(E2E_SPEC)")

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

mutation-backend:
	scripts/run-backend-mutation.sh
