# Claude Code Handoff

Read `AGENTS.md` first. It is the shared entrypoint and contains the current
branch, PR, issue, verification gate, and delegation rules.

## Current Assignment Shape

GPT is the orchestrator. Claude workers should take one narrow GitHub issue slice
at a time, implement only the assigned files, report results, and stop. Workers
do not commit, push, open PRs, delete worktrees, delete volumes, read `.env`, or
modify historical directories.

For issue #63, the recommended first slice is backend AI boundary only:

- Add server-side prompt metadata/loading and OpenAI-compatible chat endpoint.
- Preserve `AI_API_KEY` server-side only.
- Return explicit unavailable/503 behavior when AI is disabled or the remote
  model call fails.
- Do not implement frontend workflow or case persistence in the same slice unless
  explicitly assigned.

## AI Review Semantics

`AI 审核` means pre-submit author self-check. It is advisory material that the
author submits with the case as `ai_reviews` for human expert review. It is not
admin review, not automatic approval/rejection, and not durable multi-turn chat.

Contract source:

- `docs/api.md`
- GitHub issue #63:
  `https://github.com/yangxuchen5898/case-library/issues/63`

Important contract constraints:

- One backend chat boundary: `POST /api/ai/chat`
- Prompt metadata only: `GET /api/prompts`, never prompt content
- Workflow IDs:
  `workflow/completeness`, `workflow/categorization`,
  `workflow/expression`, `workflow/score`
- `ai_reviews` max 3 records FIFO
- No fake AI output and no browser-side credentials

## rmux Worker Startup

Use the project-local wrapper from the repo root:

```bash
.codex/skills/rmux-delegation/scripts/rmux_worker.sh \
  --session issue63-backend-ai-001 \
  --role backend-ai \
  --prompt agent-runs/issue63-backend-ai/prompt.md \
  --worktree /home/q2635/wsl-workspace/case-library \
  --wait \
  --poll 60 \
  --lines 700
```

Local `ccd` resolves through `~/.zshrc` to:

```bash
claude --dangerously-skip-permissions
```

The wrapper has been verified with `issue63-wrapper-intake-003`; final capture is
under `agent-runs/issue63-wrapper-intake-003/final.txt`.

After a worker finishes, collect the final pane state and close the rmux session:

```bash
.codex/skills/rmux-delegation/scripts/rmux_collect.sh \
  --session issue63-backend-ai-001 \
  --role backend-ai
```

Collection writes `collect-*` artifacts under `agent-runs/<session>/` and closes
the session by default.

## Prompt Files

- `agent-prompts/`: tracked reusable prompt contracts only.
- `agent-runs/<session>/`: ignored per-issue prompts, reports, and rmux captures.
- `.codex/skills/rmux-delegation/`: ignored project-local orchestration tooling.
- `skills/`: product/domain prompt-template assets, not Codex workflow tooling.

## Checks

Use the gate in `AGENTS.md` before claiming completion. For narrow worker slices,
run only the assigned checks and report skipped checks with reasons. Final
orchestrator verification should run the full gate.
