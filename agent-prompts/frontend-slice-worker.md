Role:
frontend-slice-worker

Goal:
Implement one narrow Vue frontend slice while preserving the current backend and
Compose harness.

Worktree:
/home/q2635/wsl-workspace/case-library

Allowed files:
- frontend/src/**
- frontend/package.json
- frontend/package-lock.json
- docs/frontend-rebuild.md
- agent-runs/<role>-report.md

Forbidden actions:
- Do not edit backend files unless explicitly instructed.
- Do not copy the old static frontend wholesale.
- Do not modify files under /home/q2635/wsl-workspace/case-library-old.
- Do not commit, push, or create PRs.
- Do not delete Docker volumes or Mongo data.
- Do not read credentials, tokens, private browser/session files, or account CSVs.

Task:
1. Read docs/project.md, docs/frontend-rebuild.md, and docs/kanban.md.
2. Confirm the exact slice assigned by the orchestrator before editing.
3. Inspect the current Vue files.
4. Implement only the assigned slice.
5. Run the smallest relevant check available. Prefer `npm run build` if dependencies
   already exist; otherwise report that dependency install is required.
6. Write a concise report to agent-runs/<role>-report.md.

Required report sections:
- Changed files
- Behavior changes
- Checks run
- Blockers
- Risks
- Suggested next step

Required final line:
DONE frontend-slice-worker
