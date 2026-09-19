# 复杂度门禁与可读性交付证据（截至本切片）

## 阈值依据：真实分布
基准 36c725e 全仓库扫描，命令：
- 后端：`cd backend && .venv/bin/ruff check --no-cache --select C901 --config 'lint.mccabe.max-complexity=1' --output-format concise app`（1412 个函数；cc 分布 1=706、2=401、3=190、4=66、5=38、6=7、7=4，最大 7）
- 前端：`cd frontend && npx eslint --no-config-lookup -c eslint-sweep.mjs 'src/**/*.{js,vue}' --format json`（ESLint complexity 规则，113 文件；生产代码 cc>10 共 12 个，最大 19：MaterialExplorer 19、agentTimeline 17×2、router 15、AgentChatPanel 15/14/11 等）
原始证据：/tmp/case-library-259-evidence/complexity-baseline.md、baseline-backend-complexity.json、baseline-frontend-complexity.json。

## 阈值选择
- 后端 max-complexity=10：高于现状最大值 7，给真实合并留空间；Ruff 官方默认同为 10。选 7 会把现状顶格函数锁死，逼出碎片化；选 15+ 则门禁失去约束力。分布上 cc≥8 当前为 0，10 是"防新增极端"而非"逼存量"。
- 前端 complexity=15：现状 12 个 >10；15 覆盖除 3 个顶格外全部，3 个顶格（MaterialExplorer.syncSearchRoute 19、agentTimeline 两处 17）已在本切片重构为表驱动/规范化数据后降到 ≤11。15 是分布右尾的收敛点，不是机械拆分数。
- 两语言计数口径不同（ESLint 计短路/可选链，Ruff 不计），不做同一数值对齐，只按各自分布选点。
- 成本：门禁为静态扫描（Ruff <1s、ESLint <6s 本机），进 CI 不增加容器构建成本；旧行数门禁（两次容器 run）被完全移除。

## 复现命令（门禁）
- 后端：`cd backend && .venv/bin/ruff check --no-cache app tests ../scripts/ai_smoke.py ../scripts/validate_production_config.py ../scripts/wait_for_mongo.py`（本地等价于镜像内 `ruff check --no-cache app tests /app/scripts /opt/case-library/wait_for_mongo.py`）
- 前端：`cd frontend && npm run check:complexity`
- Make/CI：`make test-backend` / `make test-frontend`（ensure 链保留，镜像内执行同 gate）

## 可读性全生产盘点（改/留与理由）
改变（已提交或本切片）：
1. frontend/src/lib/agentTimeline.js：toolParamSummary/toolResultSummary/sourceHref 的 if 链改三张领域分派表（tool 名→摘要、tool 类型→结果、来源类型→链接），加 Object.hasOwn 防原型键；cc 17/17/10 → ≤8。
2. frontend/src/views/MaterialExplorerView.vue：syncSearchRoute 的 route.query 逐字段 `||""` 散落判空改为单个 routeState 规范化对象 + restored 兜底；语义等价（q:null 仍为空串），cc 19→11。
3. frontend/src/composables/useAgentChat.js：decideArtifact/undoWrite 重复的"变更后按代刷新快照"合并为 refreshAfterThreadMutation；该函数承载一致性规则（isCurrent+threadId 双守卫），非转发。
4. frontend/src/components/AgentChatPanel.vue：chooseThread/addThread 共享的线程切换编排（停止轮询、generation++、清写作上下文、depth 守卫、finally 收尾、回聊天模式、滚动恢复）合并为 transitionThread。
5. frontend/src/views/WorkbenchView.vue：performOverwrite 把 single-use 的 overwriteBaseline/overwriteSucceeded/overwriteFailed 三个跳转收回一条按执行顺序可读的线性流程；保留 flushAutosave 失败不调 API、409 刷新 lifecycle、busy finally 释放、切回草稿/crashDraft/批注/版本刷新的全部顺序。
6. backend/app/modules/cases/lifecycle.py：_require_review_conclusion 与 _require_review_return 逐字相同，合并为 _require_current_review_version（approve 与 return 两命令各自语义不变）。
7. backend/app/modules/cases/versions.py：_insert→_record→_version_record_base 三层中 _record 仅加 sourceRunId 且单调用，合入 _insert。
8. backend/app/modules/agent/artifacts.py：_accept_candidate 单调用纯转发删除，_decide 直呼 _candidate_ai_version。
9. backend/app/modules/agent/routes.py：_editable_conversation 单调用转发，内联进 create_thread（_conversation 仍是上下文解析器）。
10. backend/app/modules/agent/repository.py：公共 transaction 与私有 _transaction 双实现合一；6 个内部调用点统一走公共 transaction。

保留（有独立职责，不为指标删除）：
- refreshVersionHistory（Vue 模板多路径共用命名入口）、lifecycleBody（统一修订号）、_run_view/_model_view（持久层→模型边界投影）、repository 完成围栏与 _persist_version（原子交付/版本联动）、lifecycle._write_case/_change_status（跨状态转换共享 CAS seam）、_commit_write/_restore_document 对（映射与持久化职责不同）、annotations/_transaction 与 materials/_transaction（各自模块内聚，未跨模块合并是因模块边界即领域边界）、PublishedCaseReader/version_readable（可见性策略）、CanvasEditor/CommentPanel 等高 cc 函数（权限谓词组合，改动需先有行为规格，本切片不动）。
- 未改 Workbench 其余部分与 agent/repository.py 其余部分：无逐字重复或单调用转发；agent/repository.py 的 transaction 合并是其中唯一确认点。

## 行为保持证据
- 前端公共回归（单 worker 实测）：AgentChatPanel 63、AgentChatThreads 20、MaterialExplorer 12、router 7、agentTimeline 16+新增边界，全绿；router restore 顺序由受控 deferred 证明（阻塞期间停在 home，resolve 后 my-cases；去掉 await 时该用例红）。
- 后端公共回归（提交 06f247a 时实测）：test_case_workflow + test_version_loop + test_agent_artifact_lock + test_agent_artifact_e2e + test_agent_document_write 共 94 通过。
- 根独立复验：f5b8141 `make config` 退出 0；router await 移除的真实变异红、对照绿（quality-root-recheck.md）。
- 本切片（overwrite 合并、transaction 合一、Dockerfile 去重）待运行测试：WorkbenchView.lifecycle.test.js、WorkbenchView 组件测试、backend tests/test_agent_threads.py、test_agent_chat.py、test_agent_runs_lifecycle.py、test_agent_cancel_boundaries.py、test_annotation_rounds.py（覆盖 snapshot/start/retry/complete/_finish/append_active_event 六个 transaction 调用点）、test_version_loop.py、test_case_workflow.py、make config。

## 已知未决
- 变异测试：Stryker8.7.1 dry-run 通过（agentTimeline 360 mutants，2m46s 基线）；mutmut2.5.1 因 runner PATH 问题一次中断遗留 .mutmut-cache（未验证，不作为证据）；mutmut3 在本仓无 setup.cfg 配置时报 source_paths 缺失，需 setup.cfg 或迁移后评估。全套按模块执行尚未开始。
- 前端 3 个 cc=15 顶格函数（AgentChatPanel directSource/openHistoryVersion、router.redirectForRoute 等）保留：权限/并发守卫组合，拆分将制造无收益间接层；门禁允许其存在，后续有行为规格再动。
