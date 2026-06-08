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

Pages without tracked design mockups should take their functional behavior from
the historical reference files above, especially the old public case library,
detail, like/unlike, statistics, login, "My Submissions", and admin review
screens. Their visual system should still be derived from the create-case design:
same Shanghai University header, red academic brand language, restrained white
workspace, compact form controls, small-radius cards, and role-aware navigation.
Do not revive the old static frontend's unrelated visual styling.

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

## Extracted Create-Case Layout Facts

All five tracked create-flow references are `2550x2163` canvases. Preserve the
relative information architecture and proportions; pixel-perfect copying is not
required.

### Global Shell

- Header is a full-width white bar about 140 px tall in the reference, with a
  subtle bottom border. It remains visually separate from the left rail and the
  main workspace.
- Shanghai University branding sits at the far left of the header, roughly 60 px
  from the left edge. The logo plus "上海大学 / SHANGHAI UNIVERSITY" block is about
  200 px wide and 60 px tall, vertically centered in the header.
- The "强国有我 思政案例库" wordmark starts to the right of the university mark,
  around 350 px from the canvas left edge. It is the strongest header element:
  red, brush-style for "强国有我", bold sans for "思政案例库", and roughly twice the
  visual height of a navigation label.
- Top navigation is horizontally centered after the wordmark: "首页", "案例库",
  "创建案例", "我的提交". The active item in these references is "案例库", red with
  a short red underline. Other items are dark grey.
- Search and icons form a right cluster: a rounded search input about 500 px wide
  with placeholder "搜索学术资源...", followed by search, notification, and user
  icons. Icons are monochrome grey/black and should use existing icon assets or a
  library rather than text labels.
- The main page is an administration workspace, not a landing page: white
  background, restrained borders, compact labels, and large readable form fields.

### Left Progress Rail

- The rail is fixed-width, about 570 px in the reference, with a vertical divider
  at its right edge. It starts below the header and extends to the bottom.
- Progress summary appears near the rail top: title "进度", green "80% 完成", and a
  green horizontal progress bar on a pale grey track.
- The step list contains five rows in this order: "基本信息", "案例内容", "分类选择",
  "AI 审核", "提交确认". Each row has a semantic line icon, a circular check-state
  marker, and a text label.
- Active step state: pale red row background, 6 px red bar on the far left, red
  label text, and a darker step icon.
- Completed step state: neutral row background, normal grey/dark label, and a red
  check marker. Future step state: pale grey icon, marker, and label.
- The active row changes per screen, while prior rows become completed. The first
  screen shows "基本信息" active and future rows disabled; the final screen shows
  "提交确认" active and all prior rows completed.

### Main Workspace

- Content begins to the right of the rail, about 700 px from the canvas left edge,
  with a maximum working width around 1700 px. Keep forms aligned to this column
  instead of centering each control independently.
- Breadcrumbs sit above each title, using grey text and chevrons. The current
  breadcrumb can be red on deeper steps.
- Page titles are large and black, around 56 px in the reference. Descriptive copy
  is medium grey and sits directly under the title.
- Inputs are rectangular with very small radius or square corners, light grey
  borders, and pale placeholder text. Field labels are dark and compact. Required
  fields use a red asterisk.
- Primary actions are red filled rectangular buttons with white text and a right
  arrow/send icon. Secondary actions are white outline buttons with grey or muted
  red borders. Bottom actions align to the lower right of the workspace except
  where a card-owned submit button appears inside the confirmation card.

### Step Content

- Basic information (`1.png`): fields are "案例标题", "作者姓名", and "所属部门/学院".
  The title input spans the full form width. Author and department form a two-column
  row. A bordered "编写小贴士" tip card follows the fields with a red lightbulb icon.
- Case body (`2.png`): the primary control is a very large Markdown textarea with
  placeholder text, a bottom-right resize handle, and inline counters for current
  word count and estimated reading time. Buttons are "保存草稿" and "继续".
- Classification (`3.png`): a pale yellow hint banner says uncertain users can ask
  the bottom-right AI assistant. Fields are two full-width selects, "案例类型" and
  "案例主题", each with helper text. A floating red square AI assistant button sits
  near the bottom-right viewport edge.
- AI review (`4.png`): show a red "整体审核进度" label with a full-width red progress
  bar and "100% 已完成". Results are a two-column card grid: content structure,
  classification accuracy, expression standardization, and a highlighted score
  summary card with red border and circular score display. Actions are "返回修改"
  and "继续".
- Submit confirmation (`5.png`): show a bordered pass notice "AI 智能审核已通过",
  then a large submission card titled "提交至专家审核" with a "待审核" status pill,
  checklist rows, and a red "正式提交案例" button with a send icon.

Current backend gaps relative to these designs:

- no dedicated AI review endpoint
- no attachment upload/authorization agreement workflow despite confirmation copy
- no separate expert-review submission object beyond case status/review records

Until backend support exists, the Vue UI must not fake durable AI or attachment
behavior. The AI review step (step 4) and submit confirmation (step 5) should be
implemented as follows in alpha:

- **Step 4 "AI 审核"**: show a local, clearly bounded pre-submit checklist or
  self-review summary only. It must not imply server-side validation, display a
  fake "AI passed" score, or store any AI-generated judgment. It is transient
  UI guidance that disappears on navigation.
- **Step 5 "提交确认"**: show the standard submit card with a "待审核" status
  pill pointing to human expert review. Do not show "AI 智能审核已通过" or any
  language implying server-side AI validation has occurred.
- **Classification AI assistant**: the UI may keep only transient browser state
  for a one-round assistant interaction that helps choose type/theme. Any future
  model call must go through the server-side OpenAI-compatible client boundary.
  Do not persist assistant state or expose browser-side AI credentials.

## API Use

Do not maintain a hand-written endpoint catalog here. Use FastAPI Swagger at
`/docs` and OpenAPI at `/openapi.json` as the current implementation reference,
and use `docs/api.md` only as recovered target-state design material. Use
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
