# 复杂度门禁与可读性交付证据（提交 4a46975）

## 阈值依据：本提交复现分布
命令（全部在本工作区可直接运行，输出落在 /home/q2635/agent-results/case-library-259/）：
- 后端：`cd backend && .venv/bin/ruff check --no-cache --select C901 --config 'lint.mccabe.max-complexity=1' --output-format concise app tests ../scripts/ai_smoke.py ../scripts/validate_production_config.py ../scripts/wait_for_mongo.py > /home/q2635/agent-results/case-library-259/backend-cc-full-sweep-4a46975.txt`
  结果：1004 个函数 cc>1，分布 2=582、3=272、4=88、5=46、6=11、7=4、8=1（最大 8，`unsafe_name` scripts/validate_production_config.py）；app/modules 内最大 7。证据文件已持久化。
- 前端：`cd frontend && npx eslint --no-config-lookup -c eslint.config.js --rule 'complexity: ["error", 1]' --format json 'src/**/*.{js,vue}' > /home/q2635/agent-results/case-library-259/frontend-cc-full-sweep-4a46975.json`
  结果：114 文件、651 个 cc>1 函数，分布 2=268、3=164、4=78、5=53、6=32、7=22、8=15、9=4、10=5、11=4、12=1、13=1、14=3、15=1。顶格 6 个（≥12）：AgentChatPanel directSource 15 / openHistoryVersion 14、router.redirectForRoute 14、MaterialExplorer.syncSearchRoute 14、CanvasEditor.domSelectionRange 13、useAgentChat.stopChat 12。证据文件已持久化。
- 说明：eslint-sweep.mjs 临时扫描脚本已随崩溃丢失且未入库，前端分布一律用入库的 eslint.config.js 加 `--rule complexity:["error",1]` 复现，与门禁同一解析管线（vue flat essential）。

## 阈值选择
- 后端 max-complexity=10：模块内现状最大 7（scripts 工具 8 为一次性校验脚本）；10 高于全部现状、与 Ruff 默认一致，作用是拦新增极端而非逼存量合并碎片。选 7 会把现状顶格函数锁死。
- 前端 complexity=15：现状 651 个 cc>1 中仅 4 个 ≥13；15 收敛右尾、保留真实权限/并发守卫组合（directSource 15、openHistoryVersion 14 为权限与并发守卫链，拆分只会制造转发）。重构后 agentTimeline 三处 17/17/10 已降到 ≤8。
- 两语言计数口径不同（ESLint 计短路/可选链，Ruff 不计），不按同一数值对齐，各按分布选点。
- 成本：Ruff <1s、ESLint ~4s（本机），CI 内随现有 test 镜像执行，无新增容器；旧"函数<20行"门禁（两次容器 run）完全移除。

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
- 变异测试：Stryker8.7.1 dry-run 通过（agentTimeline 360 mutants，2m46s 基线）；mutmut2.5.1 cases 冒烟中断于 10 个变异（4 killed / 3 survived / 477 untested，源码已恢复 HEAD，cache 保留于 backend/.mutmut-cache，未验证不作为最终证据）。
- 成本定位（已证实）：mutmut 基线 93s ≈ 每用例 setup ~1.7s，其中 seed_demo_users 5 账户 × bcrypt-12（实测 hash 0.284s/次，/home/q2635/agent-results/case-library-259/bcrypt-cost-probe.json）≈ 1.42s 是主导项；登录 verify ~0.3s/次 × 25-46 次为次要项。每变异需重跑该基线，487 变异 × ~93s 不可扩展。
- 可执行方案（决策待定）：测试种子/fixture 层复用预计算哈希或低轮次真实 bcrypt（保持 checkpw 真实、生产 passwords.py 默认 12 轮不动、密码安全专项测试不削弱），预计把基线降到 <10s；配合 mutmut3 测试感知选择（当前 3.8.0 需 setup.cfg 提供 source_paths，需先补配置）。全套执行采用可扩展方案后再跑。
- 存活变异检视：3 个 bad_survived 位于 lifecycle.py `_id(prefix)`（line34 两个：prefix 字面量变异常/变长度）与 `_require_admin`（line39 一个：403→404 状态码变异）。_id 前缀是内部 ID 命名空间，无公共合同约束其取值，属等价变异候选（记录依据，不计 killed）；403→404 改变了未授权语义，公共 API 合同（测试断言 403）应当能杀死它——当前两测试文件未覆盖 admin-only lifecycle 路由的 403 断言，属真实测试缺口，待全套执行后在公共 seam 补断言。
