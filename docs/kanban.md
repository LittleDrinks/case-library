# 看板

GitHub Issues 是唯一任务看板，不在本文维护第二套任务列表。

## 2026-06-16 now/next 交接摘要

本节只记录当日交接快照；任务状态仍以 GitHub Issues 为准。

当前基线：`develop/littledrinks` 已推送到 `099a08c Complete alpha handoff issues`。
分支 ZIP：`https://github.com/yangxuchen5898/case-library/archive/refs/heads/develop/littledrinks.zip`。

验证证据：

- `agent-runs/deadline-20260616-now-next/collect-20260616-032820.final.txt`
  记录最终独立验证：`docker compose run --rm app make check`、两个 desktop
  Playwright 规格（`demo-media` 4 passed，`audit` 6 passed、1 skipped mobile-only）、
  `docker compose config --quiet`、`git diff --check` 均 PASS。
- `agent-runs/test-handoff-fix-20260616/collect-20260616-091834.final.txt`
  记录 backend test layout migration 后续修复：`backend/tests/{unit,integration,smoke}/`
  已建立，`make check`、`py_compile`、`git diff --check` 均通过。该迁移是当前
  follow-up 工作，需在验证后单独 staging/提交。

status:now：

- #156：alpha UI baseline 已进入 `099a08c`，issue 仍 open；关闭前确认 baseline
  文档、截图和验收口径。
- #158：已有 first-stage backend module split 准备材料；先按 API contract 收窄
  边界，不直接做大拆分。
- #160：API contract 已由文档和 backend contract checks 锁定；后续模块拆分继续
  保持 OpenAPI 与字段兼容。

status:next：

- #161：demo-media spec 和命令已可运行；下一步生成并归档 E2E demo videos。
- #159/#122：backend tests 已迁入 `backend/tests/{unit,integration,smoke}/`，当前
  迁移改动是待提交的 follow-up。
- #157/#85：关键 desktop E2E 已恢复通过；移动端和完整 dev-e2e 后续补强。
- #123：已有 helper 化，长流程仍需继续拆小。
- #118/#144/#96：共享组件和 CreateCase split 已部分完成；旧工作分支不要直接
  合并，按当前 baseline 重新收窄 scope。
- #97：仅有 API 方案；runtime 仍是单 `type` 字段。多选类型实现延后，不作为当前
  handoff blocker。

分支交接：

- 已包含：`issue/4-auth-shell`、`issue/65-backend-ai-chat`、
  `issue/81-86-alpha-backend`、`work/alpha-triage-20260615`、
  `work/issue144-refactor-home-library`、`work/issue146-case-detail-demo`。
- 已被覆盖/不要直接合并：多数旧 `issue/*`、`work/*`、`origin/work/*` 分支已由
  `develop/littledrinks` 的 squash/PR commit 覆盖，应按当前 baseline 重开小切片。
- 避免现在合并：`work/frontend-design-migration` 与
  `origin/work/frontend-design-migration` 属于 #90 later scope，且当前与基线冲突。
- 候选合并：无。

- 仓库：`https://github.com/yangxuchen5898/case-library`
- Issues：`https://github.com/yangxuchen5898/case-library/issues`
- 当前 AI 合同相关 issue：`https://github.com/yangxuchen5898/case-library/issues/63`
- 当前 summary PR：`https://github.com/yangxuchen5898/case-library/pull/62`

常用标签：

- `status:now`
- `status:next`
- `status:later`
- `status:blocked`
- `type:harness`
- `type:frontend`
- `type:backend`
- `type:docs`
- `type:test`

工作流：

1. 一次只选一个 `status:now` issue。
2. 使用聚焦分支。
3. 每个 PR 尽量只覆盖一个工作流切片。
4. 关闭 issue 前必须有具体校验证据。
