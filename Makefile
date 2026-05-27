.PHONY: install-dev lint format typecheck check test cov frontend-test frontend-build compose-config run up dev down logs

PYTHON_LINT_TARGETS := backend
ifneq ("$(wildcard scripts)","")
PYTHON_LINT_TARGETS += scripts
endif

install-dev:
	pip install -r requirements.txt -r requirements-dev.txt
	pre-commit install

lint:
	ruff check $(PYTHON_LINT_TARGETS)

format:
	ruff format $(PYTHON_LINT_TARGETS)

typecheck:
	@if [ -f backend/core/config.py ] || [ -f backend/core/logging_config.py ]; then \
		targets=""; \
		[ -f backend/core/config.py ] && targets="$$targets backend/core/config.py"; \
		[ -f backend/core/logging_config.py ] && targets="$$targets backend/core/logging_config.py"; \
		mypy $$targets; \
	else \
		echo "Skipping mypy: frozen baseline files are not present yet."; \
	fi

check: lint typecheck
	@if [ -f scripts/check_exceptions.py ]; then \
		python scripts/check_exceptions.py backend/core/config.py backend/core/logging_config.py; \
	fi

test:
	@if [ -d tests ]; then \
		pytest; \
	elif [ -f backend/test_submit_flow.py ]; then \
		python backend/test_submit_flow.py; \
	else \
		echo "No tests or smoke test found."; \
	fi

cov:
	pytest --cov=backend --cov-report=term-missing

frontend-test:
	@if [ -f frontend/package.json ]; then cd frontend && npm test; else echo "Skipping frontend tests: frontend/package.json is not present yet."; fi

frontend-build:
	@if [ -f frontend/package.json ]; then cd frontend && npm run build; else echo "Skipping frontend build: frontend/package.json is not present yet."; fi

compose-config:
	docker compose config

run:
	@if [ -f backend/core/main.py ]; then \
		uvicorn backend.core.main:app --host 0.0.0.0 --port 8001 --reload; \
	else \
		uvicorn backend.main:app --host 0.0.0.0 --port 8001 --reload; \
	fi

dev up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f
