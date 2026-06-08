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
- `frontend/`: Vue 3 + Vite alpha frontend with an app shell, role-aware
  navigation, and restored public, authenticated, and admin workflows. Not
  production-complete.
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

### Import Source Policy

Raw runtime data, Mongo dumps, uploads, and unreviewed material collections stay
ignored and out of git. The repository root `.gitignore` already covers `data/`
for this reason. Do not add exceptions for raw assets.

Historical material collections are **import sources only**, not committed raw
assets. They may appear in old checkouts or backups as Markdown files, JSON
bundles, or Mongo exports. Their role is to feed a one-time or repeatable
import/curation step, not to be snapshotted as-is into the product repository.

### Handling Reappearing Old Material Collections

If a material Markdown collection reappears in an old checkout or backup:

1. **Inspect read-only first.** Inventory the files: count, size, structure,
   schema drift, duplication, and obvious quality problems (encoding, broken
   frontmatter, missing required fields).
2. **Decide the path based on condition and value:**
   - **Narrow importer** — if the collection is large, semi-structured, and worth
     keeping in sync with schema evolution. Write a small script that reads from
     the external path and outputs validated fixtures or direct DB inserts. Commit
     only the importer and its tests.
   - **Curated fixtures** — if only a small, high-value subset is worth keeping.
     Extract, review, normalize, and commit the fixtures under a tracked path such
     as `backend/tests/fixtures/` or `docs/fixtures/`. Include a note explaining
     source and selection rationale. Historical case or material fixtures must not
     be stored under `skills/` unless they are deliberately transformed into
     prompt/template assets.
   - **Curation note** — if the collection is low quality, redundant, or
     superseded. Write a short markdown note documenting what was found, why it
     was rejected, and where the source lives, then leave the data outside git.
3. **Never commit raw unreviewed collections.** The committed artifacts are the
   importer, the curated fixtures, or the documentation — never the original
   dump.

### Checked Backup Data State

As of 2026-06-06, the read-only historical directories were checked:

| Path | Exists | Content |
|---|---|---|
| `/home/q2635/wsl-workspace/case-library-old/data` | **No** | Directory does not exist. |
| `/home/q2635/wsl-workspace/case-library-worktree-backup-20260605/data/uploads` | **Yes** | Empty directory (no files). |

This state should be re-checked only when a new backup or old checkout is
discovered.

## AI And Skills

### Alpha Decision: Transient UI Guidance Only

In the alpha phase, AI review remains **transient/local UI guidance only**.
It is **not** a durable backend approval, audit, validation, or review record.
The create-case wizard may show a local pre-submit checklist or state summary
that helps the author self-review, but it must not imply server-side AI
validation exists or persist any AI-generated judgment as an official record.

### Durable AI Review (Future Backend Design)

A durable AI review feature requires an explicit later backend design covering:

- Persistence schema for AI review records (what is stored, TTL, versioning)
- Review record semantics (what "AI passed/failed" means, thresholds, scoring)
- Auth/traceability (who requested the review, which model, prompt version,
  temperature, timestamp)
- Model configuration and fallback (primary model, fallback model, error handling)
- Failure handling (timeout, rate limit, invalid response format, retry policy)
- Relationship to human expert review (AI review as advisory vs. gate,
  escalation rules, override workflow)

Do not implement or simulate any of the above until there is a dedicated design
document and backend endpoint.

### OpenAI-Compatible Client Boundary

When implemented, the AI client must be:

- **Server-side only** — never expose `AI_API_KEY` to browser code
- **Configured through `.env`** using these variables:
  - `AI_BASE_URL` — endpoint base URL
  - `AI_API_KEY` — API key (server-side only)
  - `AI_MODELS` — comma-separated available models
  - `AI_DEFAULT_MODEL` — fallback when none specified
  - `AI_TIMEOUT_SECONDS` — request timeout
  - `AI_REVIEW_ENABLED` — feature flag to disable AI features entirely
- **One chat interface** — a single chat completion path, not multiple
  specialized endpoints
- **Explicit model selection** — model chosen from `AI_MODELS`, defaulting to
  `AI_DEFAULT_MODEL`; reject unknown models
- **Feature flag and timeout honored** — when `AI_REVIEW_ENABLED=false`, AI
  routes return 503 or equivalent; always respect `AI_TIMEOUT_SECONDS`

### Skills/Prompts

Existing `skills/` content is useful domain knowledge:

- case writing templates
- case classification rules
- reference writing format

These are **domain prompt/template assets**, not runtime framework code. They
may feed future product prompts/templates when the AI client is implemented.

Do not migrate old `.claude/` or `.codex/` review workflow bundles into this
repository. They are agent orchestration tooling, not product domain assets.

### Explicit Non-Goals

- No fake "server AI passed" state in frontend or backend
- No attachment/expert workflow simulation
- No browser-side AI credentials or direct API calls
- No durable AI audit trail until full backend support exists

## Testing Direction

Current gate is intentionally small. The Playwright smoke test covers the primary
user story end-to-end:

```text
login -> create/submit case -> admin review -> approved case visible publicly
```

Run it when Compose services are up:

```bash
make smoke-e2e
# or
cd frontend && npm run test:e2e
```

For the containerized development E2E runner, use:

```bash
docker compose -f docker-compose.dev.yml up -d --build
docker compose -f docker-compose.dev.yml --profile e2e run --rm e2e
```

The dev compose app startup normalizes deterministic test accounts via
`scripts/seed_e2e_accounts.py`. Equivalent Make targets are available:

```bash
make dev-up
make dev-e2e
make dev-down
```

The audit E2E currently runs the desktop Playwright project, saves audit and
failure screenshots to `agent-runs/screenshots`, and verifies:

```text
default admin login requires password change
author submit -> admin approve -> public search
```

Screenshot checks belong with frontend work. Workers must extract layout facts
from `docs/design/create/*.png` before implementing create-case screens.

No benchmark code exists in alpha. Do not add benchmark infrastructure until
there is a real AI endpoint and stable fixtures/source policy to measure against.

Later benchmark candidates (track in GitHub Issues or `docs/kanban.md` only
after the behavior exists):

- Classification accuracy against `skills/zhutifenlei` rules
- Review consistency over curated case fixtures
- Prompt regression using `skills/anlibianxie/evals/evals.json`

Track that decision in `docs/kanban.md` rather than adding speculative benchmark
code now.

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
