# Agent Handoff

This file is the agent entrypoint for the restart track. Keep it operational and
short. Do not duplicate product facts that belong in `docs/project.md`,
`docs/frontend-rebuild.md`, or GitHub Issues.

## Current Context

- Worktree: `/home/q2635/wsl-workspace/case-library`
- Branch: `rescue/restart`
- Origin fork: `https://github.com/LittleDrinks/case-library.git`
- Upstream repo: `https://github.com/yangxuchen5898/case-library.git`
- Draft PR: `https://github.com/yangxuchen5898/case-library/pull/11`
- Kanban: `https://github.com/yangxuchen5898/case-library/issues`
- Scaffold commit pushed to origin: `fae1432 chore: establish restart scaffold`

Historical directories are read-only references:

- `/home/q2635/wsl-workspace/case-library-old`
- `/home/q2635/wsl-workspace/case-library-worktree-backup-20260605`

Do not develop from them and do not copy files wholesale.

## Source Of Truth

- Project harness, architecture, environment, API policy, testing direction:
  `docs/project.md`
- Frontend design and rebuild constraints: `docs/frontend-rebuild.md`
- Kanban index only: `docs/kanban.md`
- Actual task details and status: GitHub Issues
- Worker prompt contracts: `agent-prompts/`

One fact belongs in one place. If a fact is already maintained in one of the
above, link to it instead of copying it.

## Local Environment

- `.env.example` is tracked.
- `.env` is local and ignored. It currently contains a test AI base URL/API key
  and a model list pulled from the remote `/models` endpoint.
- Never print or commit `AI_API_KEY`.
- AI integration should use one OpenAI-compatible chat client configured by:
  `AI_BASE_URL`, `AI_API_KEY`, `AI_MODELS`, `AI_DEFAULT_MODEL`,
  `AI_TIMEOUT_SECONDS`, `AI_REVIEW_ENABLED`.

## Verification Gate

Before declaring scaffold or implementation work done, run the project gate from
`docs/project.md`:

```bash
docker compose up -d --build
curl -fsS http://127.0.0.1:8001/api/constants
curl -fsS http://127.0.0.1:18080/
docker compose ps
docker compose run --rm app make check
docker compose config --quiet
git diff --check
```

Last known good evidence:

- Local Compose startup succeeded.
- API and frontend endpoints responded.
- `docker compose run --rm app make check` passed.
- PR #11 CI `App` check passed.
- AI `/models` and `/chat/completions` test calls passed with `qwen-plus`.

## Orchestrator Workflow

1. Pick one GitHub Issue with `status:now`.
2. Make or reuse a focused branch for that issue.
3. If delegating, write a narrow worker prompt using `agent-prompts/`.
4. Give each worker:
   - exact role and goal
   - allowed files
   - forbidden actions
   - checks allowed
   - required final line: `DONE <role>`
5. Workers do not commit, push, delete volumes, read secrets, or modify old
   directories.
6. Review worker output and diffs yourself.
7. Run the verification gate or the smallest justified subset, then document any
   skipped checks in the PR.
8. Push to `origin`, open/update a draft PR against upstream, and link the issue.
9. Move labels as the issue progresses:
   - `status:now`
   - `status:next`
   - `status:later`
   - `status:blocked`
10. Close issues only with concrete verification evidence.

Prefer one issue per PR. Split PRs by workflow slice, not by arbitrary file
groups.

## Frontend Rules

Before implementing create-case screens, extract structure from
`docs/design/create/*.png`. The extraction must include at least:

- Shanghai University logo position and proportion
- "强国有我 思政案例库" wordmark position, size, and visual weight
- top navigation layout
- search and icon cluster layout
- left progress rail, step states, active/inactive colors
- page content width, spacing, form fields, primary/secondary buttons

Do not ask a worker to recreate the full frontend in one pass. Build vertical
slices and compare screenshots.

## AI And Skills Policy

Keep current `skills/` as domain prompt/template assets. Do not migrate old
`.claude/` or `.codex/` workflow bundles into this repo.

Future product AI review should be rebuilt around the `.env` chat settings. Do
not fake durable AI review or attachment workflow in the frontend until backend
support exists.

Useful built-in/local skills for orchestrators:

- `rmux-orchestrator`: pane workers with DONE sentinels.
- `github:gh-fix-ci`: inspect and fix failing GitHub Actions.
- `github:gh-address-comments`: process PR review comments.
- `github:yeet`: publish focused changes through GitHub.
- `find-skills`: discover additional skills before installing anything.

Supplemental skill candidates found but not installed:

- `microsoft/playwright-cli@playwright-cli` for browser automation.
- `currents-dev/playwright-best-practices-skill@playwright-best-practices` for
  Playwright test quality.

Do not install low-signal GitHub or design-review skills just because they
exist. The current GitHub plugin and repo-specific design docs are enough until
an issue proves otherwise.
