# Project Harness

This document owns the project scaffold: architecture, environment, quality
gates, API documentation policy, resource policy, and worker rules. Keep each
project fact here unless it belongs only to frontend design (`docs/frontend-rebuild.md`)
or progress tracking (`docs/kanban.md`).

## Workspace

Work from:

```bash
cd /home/q2635/wsl-workspace/case-library
```

Historical directories are read-only references:

- `/home/q2635/wsl-workspace/case-library-old`
- `/home/q2635/wsl-workspace/case-library-worktree-backup-20260605`

Do not develop from them and do not copy old files wholesale.

## Architecture

- `backend/`: FastAPI app, MongoDB data layer, account scripts, migration/smoke scripts.
- `frontend/`: Vue 3 + Vite app. It is currently a minimal connectivity page.
- `skills/`: prompt/template resources for case writing and classification. Treat them
  as domain assets, not as runtime framework code.
- `docs/design/`: tracked visual design references.
- `agent-prompts/`: tracked worker task contracts.
- `agent-runs/`: ignored worker outputs and pane captures.

Runtime services are defined in `docker-compose.yml`:

- `app`: FastAPI API on host port `8001`
- `frontend`: Vite dev server on host port `18080`
- `mongo`: MongoDB on the Compose network only

## Environment

`.env.example` is the source of truth for local configuration names. Copy it to
`.env` for local secrets and overrides.

Important groups:

- MongoDB: `MONGODB_URI`, `MONGODB_DB_NAME`, `MONGODB_TIMEOUT_MS`
- Auth: `AUTH_SECRET`, `AUTH_TOKEN_TTL`
- OpenAI-compatible AI client placeholders:
  `AI_BASE_URL`, `AI_API_KEY`, `AI_MODELS`, `AI_DEFAULT_MODEL`,
  `AI_TIMEOUT_SECONDS`, `AI_REVIEW_ENABLED`
- Frontend: `VITE_API_BASE_URL`, `FRONTEND_PORT`
- Mirrors: `APT_MIRROR`, `APT_SECURITY_MIRROR`, `PIP_INDEX_URL`,
  `NPM_CONFIG_REGISTRY`

The AI variables are intentionally placeholders until AI-backed review/skill
features are implemented. Fill them in local `.env`; never commit real keys.

## Quality Gate

Primary acceptance gate:

```bash
docker compose run --rm app make check
docker compose config --quiet
```

`make check` runs backend lint, the current backend submit-flow test, and the
frontend Vite build. Add focused tests as behavior is restored instead of widening
the gate with unowned tools.

If the frontend dev server reports a broken Vite install, reset only its dependency
volume:

```bash
docker compose stop frontend
docker volume rm case-library_frontend_node_modules
docker compose up -d frontend
```

## API Documentation

Do not maintain a duplicated hand-written endpoint list. FastAPI owns the API
contract:

- Swagger UI: `http://127.0.0.1:8001/docs`
- OpenAPI JSON: `http://127.0.0.1:8001/openapi.json`
- Runtime labels/constants: `GET /api/constants`

When public API behavior changes, update tests or the OpenAPI-producing route
implementation. Prefer generated API references over manually copied endpoint
tables.

## Resources

Raw runtime data stays out of git. The current repository ignores `data/` for
databases, uploads, Mongo dumps, and local material collections.

The checked historical backup currently has only an empty `data/uploads/`
directory. If material Markdown collections reappear in another old checkout or
backup, treat them as an import source: inspect them, write a narrow importer or
curation note when needed, and commit only reviewed fixtures or generated code.

## AI And Skills

Existing `skills/` content is useful domain knowledge:

- case writing templates
- case classification rules
- reference writing format

Do not migrate old `.claude/` or `.codex/` review workflow bundles into this
repository. They are agent orchestration tooling, not product domain assets.

The future product AI review flow should be rebuilt as a small
OpenAI-compatible chat client configured only through `.env`. It can consume the
tracked domain `skills/` as prompts/templates, but the runtime boundary should be
one chat interface with explicit model selection from `AI_MODELS`.

The create-case design includes an "AI review" step, but the current backend has
no durable AI review endpoint, attachment workflow, or expert submission object.
Do not fake server-side AI validation in the frontend.

## Testing Direction

Current gate is intentionally small. The next testing layer should be Playwright
smoke coverage for the primary user story:

```text
login -> create/submit case -> admin review -> approved case visible publicly
```

Screenshot checks belong with frontend work. Workers must extract layout facts
from `docs/design/create/*.png` before implementing create-case screens.

No benchmark currently exists. Add one only when there is stable behavior to
score, such as AI review consistency, case classification accuracy, or full
user-story completion time. Track that decision in `docs/kanban.md` rather than
adding speculative benchmark code now.

## Worker Rules

Use narrow prompts from `agent-prompts/`. A worker must get:

- role and goal
- allowed files
- forbidden actions
- checks allowed
- required `DONE <role>` final line

Workers do not commit, push, delete Docker volumes, read credentials, or modify
historical directories. Review worker diffs before merging.

Use GitHub Issues as the kanban. `docs/kanban.md` is only an index to the issue
board and must not duplicate task details.
