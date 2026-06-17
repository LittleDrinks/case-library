.PHONY: install-dev lint format check test test-backend-unit test-backend-integration test-frontend-unit test-e2e-mock cov openapi-smoke typecheck security audit smoke smoke-e2e frontend-build compose-config run up dev down logs dev-up dev-seed dev-e2e dev-down

install-dev:
	pip install -r requirements.txt -r requirements-dev.txt
	pre-commit install

lint:
	ruff check backend

format:
	ruff format backend

check: lint test-backend-unit test-backend-integration test-frontend-unit frontend-build

typecheck:
	mypy backend

security:
	bandit -c pyproject.toml -r backend

audit:
	pip-audit -r requirements.txt -r requirements-dev.txt

test: test-backend-unit test-backend-integration

test-backend-unit:
	pytest backend/tests/unit -m "not real_ai"

test-backend-integration:
	pytest backend/tests/integration

test-frontend-unit:
	@if [ -f frontend/package.json ]; then \
		cd frontend && \
		if [ -f package-lock.json ]; then npm ci; else npm install; fi && \
		npm run test:unit; \
	else \
		echo "No frontend/package.json found."; \
	fi

test-e2e-mock:
	docker compose -f docker-compose.dev.yml --profile e2e run --rm e2e npm run test:e2e:mock

cov:
	pytest backend/tests/unit backend/tests/integration -m "not real_ai" --cov=backend --cov-report=term-missing --cov-report=xml:coverage.xml --cov-report=html:htmlcov --cov-fail-under=30

openapi-smoke:
	pytest backend/tests/integration/test_submit_flow.py::test_openapi_smoke

smoke:
	python backend/tests/smoke/smoke_test_mongo.py

dev-up:
	docker compose -f docker-compose.dev.yml up -d --build --wait --wait-timeout 120

dev-seed:
	docker compose -f docker-compose.dev.yml exec -e ENABLE_DEMO_SEED=true app python scripts/seed_e2e_accounts.py

dev-e2e:
	docker compose -f docker-compose.dev.yml --profile e2e run --rm e2e

smoke-e2e: dev-up
	cd frontend && SMOKE_E2E_COMPOSE_FILE=docker-compose.dev.yml npm run test:e2e

dev-down:
	docker compose -f docker-compose.dev.yml down

frontend-build:
	@if [ -f frontend/package.json ]; then \
		cd frontend && \
		if [ -f package-lock.json ]; then npm ci; else npm install; fi && \
		npm run build; \
	else \
		echo "No frontend/package.json found."; \
	fi

compose-config:
	docker compose config

run:
	uvicorn backend.app.main:app --host 0.0.0.0 --port 8001 --reload

dev up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f
