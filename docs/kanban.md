# 看板

GitHub Issues 是唯一任务看板，不在本文维护第二套任务列表。

## 2026-06-16 now/next 交接摘要

本节只记录当日交接快照；任务状态仍以 GitHub Issues 为准。

当前基线：backend database.py split 已完成并已进入 `develop`；issue #156 正通过
`docs/frontend-baseline.md` 补齐 alpha frontend baseline 交接口径。
分支 ZIP：`https://github.com/yangxuchen5898/case-library/archive/refs/heads/develop.zip`。

验证证据：

- verifier 已完成本轮 backend prompt/script cleanup 验证：
  `python3 scripts/prompt_eval_harness.py`、
  `docker compose run --rm app python scripts/prompt_eval_harness.py`、
  `docker compose run --rm app python backend/tests/unit/test_prompt_injection.py`、
  `docker compose run --rm app make check`、`docker compose config --quiet`、
  OpenAPI smoke、`git diff --check` 均通过。
- `agent-runs/deadline-20260616-now-next/collect-20260616-032820.final.txt`
  记录最终独立验证：`docker compose run --rm app make check`、两个 desktop
  Playwright 规格（`demo-media` 4 passed，`audit` 6 passed、1 skipped mobile-only）、
  `docker compose config --quiet`、`git diff --check` 均 PASS。
- `agent-runs/test-handoff-fix-20260616/collect-20260616-091834.final.txt`
  记录 backend test layout migration 后续修复：`backend/tests/{unit,integration,smoke}/`
  已建立，`make check`、`py_compile`、`git diff --check` 均通过。
- `agent-runs/test-handoff-fix-20260616/collect-20260616-093006.final.txt`
  记录测试迁移后的最终验证：`py_compile`、`make check`、两个 desktop Playwright
  规格、`docker compose config --quiet`、`git diff --check` 均 PASS。
- `agent-runs/test-handoff-fix-20260616/collect-20260616-093300.final.txt`
  记录已提交并推送 `14cd7ef`，工作区干净且对齐 `origin/develop`。
- #95 database.py split 独立验证已通过：`backend/database.py` 现为 117 行兼容层，
  `backend/main.py` 仍为 157 行；新增 `backend/db/`、`backend/repositories/`、
  `backend/serializers.py`、`backend/services/public.py` 承接 public split；最大
  split 模块为 `backend/repositories/cases.py` 439 行；develop ZIP URL 不变。

status:now：

- #156：alpha UI baseline 已进入当前基线；本轮 baseline 文档引用 #156，明确冻结核心
  UI/交互流程。关闭 #156 不要求生成 demo videos。
- #158：已有 first-stage backend module split 准备材料；先按 API contract 收窄
  边界，不直接做大拆分。

status:next：

- #161：demo-media spec 和命令已可运行；下一步生成并归档 E2E demo videos。该事项
  与 #156 分离，不阻塞 frontend baseline 文档关闭。
- #159/#122：backend tests 已迁入并提交到 `backend/tests/{unit,integration,smoke}/`；
  `Makefile` 已直接调用新路径，旧 `backend/test_*.py` 和 `backend/smoke_test_mongo.py`
  兼容入口已移除。#122 本轮已新增
  `backend/tests/unit/test_public_search_helpers.py`、
  `backend/tests/unit/test_security_dependencies.py`、
  `backend/tests/unit/test_database_repository_helpers.py` 补强公开检索、安全依赖和数据库
  repository helper 单测；验证命令为
  `docker compose run --rm app python backend/tests/unit/test_public_search_helpers.py`、
  `docker compose run --rm app python backend/tests/unit/test_security_dependencies.py`、
  `docker compose run --rm app python backend/tests/unit/test_database_repository_helpers.py`、
  `docker compose run --rm app make check`、`git diff --check`。#122 可关闭，不再作为
  open/follow-up 交接项。
- #79/#80：本轮 cleanup 已完成 root backend scripts 迁入 `backend/scripts/`、root
  `skills/` 移除、`product_prompts/` 成为 runtime prompt source of truth、registry
  loader 加载 prompt metadata 且不泄露 body、prompt eval harness 进入 `scripts/`；不再作为
  open/pending 交接项。
- #117：backend/main.py router split 已落地，`backend/main.py` 现为 157 行；新增
  `backend/routers/`、`backend/security.py`、`backend/dependencies.py` 承接路由、
  认证和依赖装配；不再作为 open/pending 交接项。
- #95：database repository/service split 已完成并已有独立验证；不再作为 open/pending
  交接项。
- #160：prompt/script cleanup 保持 API contract，OpenAPI smoke 与 `make check` 已通过；
  不再作为 open/pending 交接项。
- #157/#85：关键 desktop E2E 已恢复通过；移动端和完整 dev-e2e 后续补强。
- #123：本轮按只读审计建议补 `auditFlow` 小 helper，复用创建向导基础段、
  case-card 查找和公开搜索，降低 smoke/audit 长测试重复；可复现验证命令为
  `node --check frontend/tests/support/auditFlow.js`、
  `node --check frontend/tests/audit.spec.js`、
  `node --check frontend/tests/smoke.spec.js`、`git diff --check`、
  `docker compose -f docker-compose.dev.yml --profile e2e run --rm e2e`。smoke 浏览器运行
  仍因 Docker CLI/socket 权限未完成，#123 不标成完全关闭。
- #118/#144/#96：共享组件和 CreateCase split 已部分完成；旧工作分支不要直接
  合并，按当前 baseline 重新收窄 scope。
- #97：仅有 API 方案；runtime 仍是单 `type` 字段。多选类型实现延后，不作为当前
  handoff blocker。

分支交接：

- 已包含：`issue/4-auth-shell`、`issue/65-backend-ai-chat`、
  `issue/81-86-alpha-backend`、`work/alpha-triage-20260615`、
  `work/issue144-refactor-home-library`、`work/issue146-case-detail-demo`。
- 已被覆盖/不要直接合并：多数旧 `issue/*`、`work/*`、`origin/work/*` 分支已由
  `develop` 的 squash/PR commit 覆盖，应按当前 baseline 重开小切片。
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
