Role:
frontend-structure-worker

Goal:
Extract structured frontend requirements from the old static frontend and old
Playwright snapshots so the Vue rebuild can be implemented in small slices.

Worktree:
/home/q2635/wsl-workspace/case-library

Allowed files:
- docs/frontend-rebuild.md
- docs/project.md
- docs/kanban.md
- agent-runs/frontend-structure-worker-report.md

Read-only references:
- /home/q2635/wsl-workspace/case-library/docs/design/create/
- /home/q2635/wsl-workspace/case-library-old/README.md
- /home/q2635/wsl-workspace/case-library-old/test_cases.md
- /home/q2635/wsl-workspace/case-library-old/operate_account.md
- /home/q2635/wsl-workspace/case-library-old/frontend/index.html
- /home/q2635/wsl-workspace/case-library-old/frontend/js/app.js
- /home/q2635/wsl-workspace/case-library-old/frontend/css/style.css
- /home/q2635/wsl-workspace/case-library-old/.playwright-cli/

Forbidden actions:
- Do not edit frontend source code.
- Do not copy old frontend code into the new Vue app.
- Do not modify files under /home/q2635/wsl-workspace/case-library-old.
- Do not commit, push, or create PRs.
- Do not read credentials, tokens, private browser/session files, or account CSVs.

Task:
1. Extract the create-case flow structure from docs/design/create/*.png.
2. Identify the old app's screens, modals, states, and user-role differences.
3. Identify API calls each screen depends on.
4. Identify the smallest implementation slices for Vue.
5. Note any inconsistencies between design files, old docs, old frontend, and current backend.
6. Update docs/frontend-rebuild.md only if it removes ambiguity without duplicating docs/project.md or docs/kanban.md.
7. Write a concise report to agent-runs/frontend-structure-worker-report.md.

Required report sections:
- Create-flow design structure
- Screens and states
- API dependencies
- Role and permission rules
- Rebuild slices
- Open questions
- Risks

Required final line:
DONE frontend-structure-worker
