# AI Agent Rules

This file summarizes project-specific AI behavior rules. Read `AGENTS.md` and
`docs/project.md` first for the current branch, verification gate, environment,
and source-of-truth policy.

## Repository Boundaries

- Work from `/home/q2635/wsl-workspace/case-library`.
- Treat `/home/q2635/wsl-workspace/case-library-old` and
  `/home/q2635/wsl-workspace/case-library-worktree-backup-20260605` as read-only
  references.
- Do not copy old files wholesale. Extract behavior or structure, then implement
  deliberately in the current codebase.
- Keep local agent prompts, worker captures, screenshots, and reports under
  ignored `agent-runs/` or local tooling directories.

## Secrets And Data

- Never print, commit, or expose `AI_API_KEY`, `.env`, account CSVs, Mongo dumps,
  uploads, browser sessions, or private tokens.
- `.env.example` may contain configuration names and non-sensitive examples only.
- Product AI calls must go through the backend. Browser code must never receive
  provider credentials.
- Raw data collections and runtime uploads stay outside git unless deliberately
  transformed into reviewed fixtures or documentation.

## AI Product Semantics

`AI 审核` means author-side pre-submit self-check. It is advisory material for
human expert review, not automatic approval/rejection and not admin review.

Current contract direction:

- Alpha prompt metadata: `GET /api/prompts?category=alpha`, currently
  `alpha/paragraph-review`
- Alpha AI review boundary: `POST /api/cases/{case_id}/ai-review`, which creates
  a versioned read-only paragraph-comment snapshot
- Legacy workflow prompts under `workflow/*` and `POST /api/ai/chat` are kept as
  compatibility surfaces, not the alpha teacher review path
- Submitted advisory records: `ai_reviews`, capped at 3 records
- No fake AI output when AI is disabled or unavailable

Keep `docs/api.md`, `docs/project.md`, `docs/prd.md`, `docs/ai.md`, and GitHub
issues aligned when AI behavior changes.

## Worker Conduct

- Work one GitHub issue at a time.
- Do not commit, push, delete worktrees, delete Docker volumes, or close issues
  unless explicitly assigned by the orchestrator/user.
- Run the narrow relevant checks for the assigned slice and report skipped checks.
- End worker reports with the requested `DONE <role>` sentinel when a worker
  prompt requires it.

## Verification

Before claiming implementation work is done, use the gate in `docs/project.md`
or document the smaller justified subset:

```bash
docker compose run --rm app make check
docker compose config --quiet
git diff --check
```
