# Frontend Rebuild Spec

This document owns frontend rebuild behavior and design constraints. Project
architecture, environment, and quality gates live in `docs/project.md`. Progress
tracking lives in `docs/kanban.md`.

The old frontend was a large static HTML/CSS/JS app. It is useful as a behavior
reference, but should not be copied directly into Vue.

Historical reference files:

- `docs/design/create/1.png`
- `docs/design/create/2.png`
- `docs/design/create/3.png`
- `docs/design/create/4.png`
- `docs/design/create/5.png`
- `/home/q2635/wsl-workspace/case-library-old/README.md`
- `/home/q2635/wsl-workspace/case-library-old/test_cases.md`
- `/home/q2635/wsl-workspace/case-library-old/operate_account.md`
- `/home/q2635/wsl-workspace/case-library-old/frontend/index.html`
- `/home/q2635/wsl-workspace/case-library-old/frontend/js/app.js`
- `/home/q2635/wsl-workspace/case-library-old/frontend/css/style.css`
- `/home/q2635/wsl-workspace/case-library-old/.playwright-cli/`

The tracked design files currently cover the create-case flow. Extract
structured layout information from them first, then compare screenshots. Do not
ask an AI worker to recreate the frontend in one pass.

## Product Workflows

### Public Visitor

- See app header and navigation.
- Browse approved cases.
- Search by keyword.
- Filter by case type and theme.
- Open case detail.
- Like or unlike a public case.
- See statistics, trending cases, and latest cases.

### Normal User

- Log in with an admin-created account.
- If `must_change_password` is true, complete password change before normal use.
- Create a case through the five-step design flow:
  - basic information
  - case content
  - classification
  - AI review
  - submit confirmation
- Save local draft form data where useful.
- See "My Submissions" grouped by pending, approved, needs revision, draft, and all.
- Edit own draft or revision-needed cases.
- Submit eligible cases for review.
- Delete own cases where backend permissions allow it.
- See review comments for cases they are allowed to inspect.

### Admin User

- See all pending review cases.
- Switch review tabs: pending, approved, rejected/needs revision, all.
- Review a case with approve or reject/needs revision and a comment.
- Hide or show approved cases.
- Delete cases where backend permissions allow it.
- Inspect review and version history.

## Create-Case Design Notes

The tracked create flow uses a quiet academic administration UI:

- top navigation with Shanghai University branding, search, notification icon,
  and user icon
- left fixed progress rail with percentage and five steps
- red active step marker, pale red active row background, grey disabled future
  steps, and checkmarks for completed steps
- large white workspace with breadcrumb, page title, explanatory text, and
  restrained rectangular fields
- bottom-right primary red action, secondary outline actions where needed

Design files:

- `docs/design/create/1.png`: basic information; title, author, department, tip card
- `docs/design/create/2.png`: case body; large Markdown textarea, word count, save draft
- `docs/design/create/3.png`: classification; type and theme selects, AI helper hint
- `docs/design/create/4.png`: AI review result; analysis cards and score summary
- `docs/design/create/5.png`: submit confirmation; AI pass notice and final submit card

Current backend gaps relative to these designs:

- no dedicated AI review endpoint
- no attachment upload/authorization agreement workflow despite confirmation copy
- no separate expert-review submission object beyond case status/review records

Until backend support exists, the Vue UI should not fake durable AI or attachment
behavior. It can show a local, clearly bounded pre-submit checklist/state only if
that does not imply server-side validation.

## API Use

Do not maintain a hand-written endpoint catalog here. FastAPI Swagger at
`/docs` and OpenAPI at `/openapi.json` are the API source of truth. Use
`/api/constants` for labels such as case types, themes, and statuses.

## Suggested Vue Slices

1. API client and auth state: token storage, login, logout, forced password change.
2. App shell: header/nav, role-aware links, route/view state.
3. Public case library: list, search, filters, detail modal, like/unlike.
4. Case editor wizard: basic info, content, classification, local review step,
   submit confirmation, draft save, submit, edit existing case.
5. My submissions: status tabs, edit/resubmit/delete, review comments.
6. Admin review: queue, tabs, review modal, hide/show/delete.
7. Stats/home dashboard: statistics, trending, latest.
8. Playwright smoke tests for the critical login-submit-review path.

## Visual Process

For each slice:

1. Extract the old screen's structure from HTML/Playwright snapshots.
2. Build the Vue component with current design conventions.
3. Run the app.
4. Capture desktop and mobile screenshots.
5. Compare with the reference behavior and adjust layout.
6. Run the quality gate documented in `docs/project.md`.

Do not treat pixel-perfect old static UI as mandatory. Preserve information
architecture and workflow behavior first.
