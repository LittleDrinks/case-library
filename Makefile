.PHONY: install-dev lint format check test cov smoke smoke-e2e frontend-build compose-config run up dev down logs dev-up dev-seed dev-e2e dev-down

install-dev:
	pip install -r requirements.txt -r requirements-dev.txt
	pre-commit install

lint:
	ruff check backend

format:
	ruff format backend

check: lint test frontend-build

test:
	@if find tests -type f -name 'test_*.py' 2>/dev/null | grep -q .; then \
		pytest; \
	elif [ -f backend/test_submit_flow.py ]; then \
		python backend/test_submit_flow.py; \
	else \
		echo "No tests or smoke test found."; \
	fi

cov:
	pytest --cov=backend --cov-report=term-missing

smoke:
	python backend/smoke_test_mongo.py

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
	uvicorn backend.main:app --host 0.0.0.0 --port 8001 --reload

dev up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f
