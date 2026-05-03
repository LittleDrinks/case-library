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
- **Backend:** Python/FastAPI + SQLite, served via Uvicorn on port 8001
- **Frontend:** Vanilla HTML/CSS/JS (no framework), served as static files from `frontend/`
- **Database:** `data/cases.db` (SQLite)

### Backend modules (`backend/`)
- `main.py` — All FastAPI routes (~10+ route groups); the only entry point
- `database.py` — All SQLite schema definitions and query functions
- `search_engine.py` — TF-IDF full-text search and recommendation logic
- `case_processor.py` — Case classification and processing helpers

### Database schema
Key tables: `cases`, `users`, `reviews`, `versions`, `deployments`, `case_index`

Case status workflow:
```
draft → pending_review → approved_pending_deploy → approved (in library)
                                  ↓
                           needs_revision → pending_review
```

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
