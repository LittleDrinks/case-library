# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A full-stack web application serving as an intelligent case library for ideological and political education (思政课) case management at Shanghai University. The platform supports three case types and an AI-assisted case creation workflow.

## Running the Application

**Quick start (Windows):**
```batch
start.bat
```

**Manual start:**
```bash
cd backend
pip install -r requirements.txt
python demo.py        # Initialize demo data (run once)
python init_users.py  # Initialize users (run once)
python -m uvicorn main:app --host 0.0.0.0 --port 8001
```

Access at `http://localhost:8001`. The frontend is served as static files mounted on the FastAPI app — no separate frontend server needed.

## Testing & Utilities

```bash
cd backend
python simple_test.py   # Basic API smoke tests
python test_api.py      # Comprehensive API tests
python check_db.py      # Inspect database contents
```

No lint configuration exists in this project.

## Architecture

### Stack
- **Backend:** Python/FastAPI + MongoDB (via `pymongo`), served via Uvicorn on port 8001
- **Frontend:** Vanilla HTML/CSS/JS (no framework), served as static files from `frontend/`
- **Database:** MongoDB. Connection is configured via `MONGODB_URI` (default `mongodb://localhost:27017`) and `MONGODB_DB_NAME` (default `case_library`), loaded from `.env` in `backend/database.py`. The legacy `data/cases.db` SQLite file is only read by the one-shot migration script `backend/migrate_sqlite_to_mongo.py` and is not used at runtime.

### Backend modules (`backend/`)
- `main.py` — All FastAPI routes (~10+ route groups); the only entry point
- `database.py` — MongoDB data access layer: connection, index creation in `init_db()`, integer-id allocation via the `counters` collection, and all query/mutation helpers
- `search_engine.py` — Thin wrapper around `database.py` search/recommendation helpers (regex-based, not TF-IDF)
- `case_processor.py` — Case classification and processing helpers
- `migrate_sqlite_to_mongo.py`, `migrate_timestamps.py`, `init_users.py`, `demo.py`, `account_admin.py`, `smoke_test_mongo.py`, `test_submit_flow.py` — one-shot migration / seeding / admin / smoke-test scripts

### Database schema
Key MongoDB collections: `cases`, `users`, `reviews`, `versions`, `deployments`, `counters`. Each business collection has an integer `id` field allocated from `counters` (in addition to Mongo's `_id`). Indexes (created in `database.py:init_db()`) include unique indexes on `id` / `username`, plus compound indexes on `(status, created_at)`, `(author, status, created_at)`, `(owner_username, status, created_at)`, and a TEXT index `cases_text_idx` over `title`/`content`/`keywords`. The `deployments` collection has indexes defined but no write path in current code.

Case status workflow (values defined in `CASE_STATUSES` in `backend/database.py`):
```
draft → pending_review → approved (in library)
            ↑                ↓
            └── needs_revision (on rejection)
```
On approval, `review_case` also sets `is_approved=true` and `is_in_library=true` on the case document.

### Case type system
- **TYPE_A** (思政课教学案例): Ideological theory teaching cases
- **TYPE_B** (课程思政共享资源案例): Curriculum-integrated ideological education
- **TYPE_C** (实践育人案例): Practice/volunteer activity cases

Classification rules are in `classifier.md`; writing templates are in `template-sizhengke.md`, `template-kechengsizheng.md`, `template-shijian.md`.

### AI skill system (`skills/sijiao-case-library/`, `SKILL.md`)
The root `SKILL.md` and `skills/` directory define a 6-step AI workflow for processing raw materials (text, URLs, images) into structured cases using the templates. This is documentation for AI assistants, not executable code.

### API surface (in `backend/main.py`)
- `GET/POST/PUT/DELETE /api/cases`, `/api/cases/{id}`, `/api/cases/{id}/submit`
- `POST /api/reviews/{id}`, `GET /api/reviews/{id}`, `GET /api/versions/{id}`
- `GET /api/search`, `GET /api/search/advanced`, `GET /api/recommendations/{id}`
- `GET /api/trending`, `GET /api/latest`, `GET /api/statistics`, `GET /api/constants`
- `POST /api/auth/login`, `POST /api/auth/register`
- `POST /api/cases/{id}/mark-in-library`, `POST /api/cases/batch-mark-in-library`
- `GET /api/sync/sql` — SQL DB sync interface for external system integration
