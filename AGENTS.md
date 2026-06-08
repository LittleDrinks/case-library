# Agent Handoff

This file is the agent entrypoint for the restart track. Keep it operational and
short. Do not duplicate product facts that belong in `docs/project.md`,
`docs/frontend-rebuild.md`, or GitHub Issues.

## Current Context

- Worktree: `/home/q2635/wsl-workspace/case-library`
- Branch: `develop/alpha-summary`
- Origin fork: `https://github.com/LittleDrinks/case-library.git`
- Upstream repo: `https://github.com/yangxuchen5898/case-library.git`
- Summary PR: `https://github.com/yangxuchen5898/case-library/pull/62`
- Kanban: `https://github.com/yangxuchen5898/case-library/issues`
- Current AI contract issue: `https://github.com/yangxuchen5898/case-library/issues/63`

Current local tracked changes:

- `docs/api.md` has been replaced with the recovered full API contract.
- Solo-project cleanup deleted `CODE_OF_CONDUCT.md`, `CONTRIBUTING.md`, and
  collaboration boilerplate under `.github/`.

Current ignored local tooling/state:

- `.codex/skills/rmux-delegation/` contains the project-local rmux delegation
  skill and wrapper.
- `.codex/skills/gpt-tasteskill/` is local Codex skill state.
- `agent-runs/` contains ignored one-off worker prompts and rmux captures,
  organized by run/session subdirectory.

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
- Reusable worker prompt contracts: `agent-prompts/`
- One-off worker prompts and run captures: `agent-runs/` (ignored)

One fact belongs in one place. If a fact is already maintained in one of the
above, link to it instead of copying it.

## Prompt Tracking Policy

Track `agent-prompts/` only for reusable worker contracts that are stable across
issues, such as frontend slice or structure extraction roles. Do not track
per-issue prompts, scratch prompts, rmux captures, or worker reports; keep those
under ignored `agent-runs/<session>/`.

Project-local Codex/rmux tooling belongs under ignored `.codex/skills/`, not
`agent-prompts/` and not product `skills/`.

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

This evidence predates the latest local documentation/API-contract cleanup. Run
the full gate again before reporting the current branch as release-ready.

## Orchestrator Workflow

1. Pick one GitHub Issue with `status:now`.
2. Make or reuse a focused branch for that issue.
3. If delegating, write a narrow worker prompt. Use `agent-prompts/` as reusable
   templates and put the concrete prompt under `agent-runs/`.
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

## rmux Delegation

The current working local route is:

```bash
.codex/skills/rmux-delegation/scripts/rmux_worker.sh \
  --session issue63-wrapper-intake-003 \
  --role issue63-wrapper-intake \
  --prompt agent-runs/issue63-wrapper-intake/prompt.md \
  --worktree /home/q2635/wsl-workspace/case-library \
  --wait \
  --poll 60 \
  --lines 700
```

Local reality:

- `ccd` is available through `~/.zshrc` as
  `claude --dangerously-skip-permissions`.
- The wrapper now defaults to `ccd`, waits for shell/Claude readiness, pastes
  the prompt, waits for a standalone `DONE <role>` line, and writes final
  captures under `agent-runs/<session>/`.
- After a worker finishes, collect and close the rmux session with:

```bash
.codex/skills/rmux-delegation/scripts/rmux_collect.sh \
  --session issue63-wrapper-intake-003 \
  --role issue63-wrapper-intake
```

  This writes `collect-*` artifacts under `agent-runs/<session>/` and closes
  the session by default.
- Verified smoke: `issue63-wrapper-intake-003` read GitHub issue #63 and local
  docs, then produced `DONE issue63-wrapper-intake`.
- Workers still do not commit, push, read `.env`, or touch historical dirs.

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

Product AI review semantics are clarified in issue #63 and `docs/api.md`:
`AI 审核` means user-facing pre-submit self-check. It is advisory material
submitted as `ai_reviews` for human expert review, not automatic approval or
rejection.

AI integration should be rebuilt around the `.env` chat settings. Do not fake AI
output or browser-side AI calls. When unavailable, return/show an explicit
disabled or unavailable state.

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
