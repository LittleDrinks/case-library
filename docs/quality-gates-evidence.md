# 复杂度门禁与可读性
## 扫描范围与分布
扫描包含应用、测试和列出的运维脚本；低于扫描阈值的函数不在告警计数中。
- 后端：`cd backend && .venv/bin/ruff check --no-cache --select C901 --config 'lint.mccabe.max-complexity=1' --output-format concise app tests ../scripts/ai_smoke.py ../scripts/validate_production_config.py ../scripts/wait_for_mongo.py`
  结果：1004 个函数 cc>1，分布 2=582、3=272、4=88、5=46、6=11、7=4、8=1（最大 8，`unsafe_name` scripts/validate_production_config.py）；app/modules 内最大 7。
- 前端：`cd frontend && npx eslint --no-config-lookup -c eslint.config.js --rule 'complexity: ["error", 1]' --format json 'src/**/*.{js,vue}'`
  结果：114 文件、651 个 cc>1 函数，分布 2=268、3=164、4=78、5=53、6=32、7=22、8=15、9=4、10=5、11=4、12=1、13=1、14=3、15=1。顶格 6 个（≥12）：AgentChatPanel directSource 15 / openHistoryVersion 14、router.redirectForRoute 14、MaterialExplorer.syncSearchRoute 14、CanvasEditor.domSelectionRange 13、useAgentChat.stopChat 12。
## 阈值选择
- 后端 max-complexity=10：模块内现状最大 7（scripts 工具 8 为一次性校验脚本）；10 高于全部现状、与 Ruff 默认一致，作用是拦新增极端而非逼存量合并碎片。选 7 会把现状顶格函数锁死。
- 前端 complexity=15：扫描得到的 651 个 cc>1 函数中，5 个 ≥13；15 收敛右尾、保留真实权限/并发守卫组合（directSource 15、openHistoryVersion 14 为权限与并发守卫链，拆分只会制造转发）。重构后 agentTimeline 三处 17/17/10 已降到 ≤8。
- 两语言计数口径不同（ESLint 计短路/可选链，Ruff 不计），不按同一数值对齐，各按分布选点。
- 门禁随现有 test 镜像执行，替代函数行数检测。
## 复现命令（门禁）
- 后端：`cd backend && .venv/bin/ruff check --no-cache app tests ../scripts/ai_smoke.py ../scripts/validate_production_config.py ../scripts/wait_for_mongo.py`（本地等价于镜像内 `ruff check --no-cache app tests /app/scripts /opt/case-library/wait_for_mongo.py`）
- 前端：`cd frontend && npm run check:complexity`
- Make/CI：`make test-backend` / `make test-frontend`（ensure 链保留，镜像内执行同 gate）
## 可读性整理
调整：
1. frontend/src/lib/agentTimeline.js：toolParamSummary/toolResultSummary/sourceHref 的 if 链改三张领域分派表（tool 名→摘要、tool 类型→结果、来源类型→链接），加 Object.hasOwn 防原型键；cc 17/17/10 → ≤8。
2. frontend/src/views/MaterialExplorerView.vue：syncSearchRoute 的 route.query 逐字段 `||""` 散落判空改为单个 routeState 规范化对象 + restored 兜底；语义等价（q:null 仍为空串），当前扫描 cc=14。
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
- 未改 Workbench 其余部分与 agent/repository.py 其余部分：本次确认的重复事务封装已合并；其余部分未改动。

## 后端覆盖率与变异运行
安装 `backend/requirements-dev.lock` 到 Python 3.12 虚拟环境并激活。
- 覆盖率：`cd backend && coverage run --branch --source=app -m pytest -c tests/pytest.ini -m 'not e2e' && coverage json && coverage report`。
- 变异：仓库根目录执行 `make mutation-backend`。范围为全部 `backend/app`，使用全部非 E2E 测试，包含中文业务场景；一个子进程运行，互斥锁拒绝同 checkout 重入。
- 结果入口必须同时满足 `backend/mutants/mutmut-run-status.json` 与 `backend/mutants/mutmut-cicd-stats.json`：status 必须为 `completed`，并记录本次 `head`、`scope`、转发的 `args` 和 `exit=0`；stats 必须是本次运行生成的有效 JSON。`partial`、`failed`、缺失/无效 status 或 stats 均不是完整结果；既有 `backend/mutants/**/*.meta` 变异缓存保留以支持续跑，不得用缓存替代当前报告。详情在 backend 目录执行 `mutmut results`、`mutmut show <id>`、`mutmut tests-for-mutant <id>`。定向重跑使用 `scripts/run-backend-mutation.sh <id>`。
运行时创建的种子与脚本相对路径链接在退出或中断时清理；已有同名路径不会被覆盖。锁竞争不失效活动所有者的报告；初始化失败先失效本次所有者的旧 stats，再写入 failed status。正常退出只说明运行完成，存活、无覆盖、超时和错误仍需逐项审查，不能当作测试强度通过。

## 前端覆盖率与变异运行
在 frontend 目录执行 `npm ci`，再运行 `npm run test:coverage` 或 `npm run test:mutation`。范围是 src 下全部 JS/Vue 生产文件，排除同目录的 `.test.js`。
覆盖率 HTML/JSON/LCOV 写入 `frontend/coverage`；Stryker JSON 写入 `frontend/reports/mutation`。Stryker 使用 Vitest、逐测试覆盖分析与单个测试进程；无覆盖和存活变异保留在结果中。

Vue 变异输入由已锁定的 Vue 编译器展开 script setup 与模板，保留 setup 绑定；JS 输入不变。编译在专有临时目录中进行，生产源码不改写，结束时删除该目录；同 checkout 使用文件锁拒绝并行写报告。
`frontend/reports/mutation` 保留原始源码、编译后源码、逐文件 SHA-256 清单及 `mutation.json`。Vue 变异位置对应编译后代码，包含模板生成的渲染函数，不能与直接源码插桩的变异数量混为同一分母。文件加载失败会终止基线，不能计作成功测试。仅验证插桩基线：`npm run test:mutation -- --dryRunOnly`。
