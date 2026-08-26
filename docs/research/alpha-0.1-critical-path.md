---
sources:
  - README.md
  - CONTEXT.md
  - Makefile
  - .github/workflows/ci.yml
  - .github/workflows/release.yml
  - docs/adr/0006-workbench-newcase-admin.md
  - docs/adr/0015-case-folder-and-case-citations.md
  - docs/adr/0016-ai-write-tools-confirmed-revisions.md
  - docs/adr/0017-canvas-workbench-document-model.md
  - docs/adr/0019-meilisearch-catalog.md
  - frontend/src/router.js
  - frontend/src/views/MyCasesView.vue
  - frontend/src/views/WorkbenchView.vue
  - frontend/src/views/SearchView.vue
  - frontend/src/components/AssistantRail.vue
  - frontend/src/lib/writingCandidate.js
  - frontend/tests/e2e/ai-settings.spec.js
  - frontend/tests/e2e/search-materials.spec.js
  - frontend/tests/e2e/workbench.spec.js
  - backend/app/modules/ai/routes.py
  - backend/app/modules/cases/models.py
  - backend/app/modules/cases/service.py
  - backend/app/modules/cases/template.py
  - backend/tests/test_case_lifecycle_e2e.py
  - backend/tests/test_search_case_content_e2e.py
  - https://github.com/LittleDrinks/case-library/milestone/1
  - https://github.com/LittleDrinks/case-library/issues/14
  - https://github.com/LittleDrinks/case-library/issues/15
  - https://github.com/LittleDrinks/case-library/issues/16
  - https://github.com/LittleDrinks/case-library/issues/21
  - https://github.com/LittleDrinks/case-library/issues/22
  - https://github.com/LittleDrinks/case-library/issues/23
  - https://github.com/LittleDrinks/case-library/issues/24
  - https://github.com/LittleDrinks/case-library/issues/26
  - https://github.com/LittleDrinks/case-library/issues/27
  - https://github.com/LittleDrinks/case-library/issues/28
  - https://github.com/LittleDrinks/case-library/issues/29
  - https://github.com/LittleDrinks/case-library/issues/30
  - https://github.com/LittleDrinks/case-library/issues/31
  - https://github.com/LittleDrinks/case-library/issues/32
  - https://github.com/LittleDrinks/case-library/issues/33
  - https://github.com/LittleDrinks/case-library/issues/36
  - https://github.com/LittleDrinks/case-library/issues/37
  - https://github.com/LittleDrinks/case-library/issues/38
  - https://github.com/LittleDrinks/case-library/issues/39
  - https://api.github.com/repos/LittleDrinks/case-library/branches/v2/protection
---
# Alpha 0.1 关键路径
## 结论
黄金路径主链是 `#14 -> #37 -> #39` 与并行的 `#38 -> #39`；#15、#16 虽未进 milestone，却被 #37 明确指定为保存/冲突/快照协调和候选会话状态的责任方，是遗漏的实现依赖。#14 又把 `find_sources` 执行交给 #22，因此按 #14 当前六 mode 范围关闭完整 Alpha 合约时，#22 也是遗漏的 Next 依赖，虽不阻塞 #39 的固定选区改写。#30、#36 是并行质量门禁；#39 是黄金路径最终集成点。
现有候选生成、确认/拒绝、三条阻塞、快照、回滚和失效已有单元与 E2E；#14/#37 是服务端归权和交互/模块边界重构，不是从零开发。生命周期、冻结版本、发布投影、匿名详情和检索 outbox 同样已有跨层测试，#39 应复用并验证。当前缺口可直接从源码定位：新建仍提交客户端 `title/document`，AI 仍走通用 `/api/ai/chat` 且前端拼提示词，工作台路由只校验登录；空查询页面已隐藏 AI，#30 主要剩零 AI 请求矩阵的明确回归证明。
## 执行顺序
1. **落实 #37 已确认设计**：#37 已确认方案 B：保留左侧目录、中央画布和右侧 `AI / 批注 / 附件` 标签，仅重构 AI 标签页；输入器采用圆角单体，`+` 只承载 #49 的联网检索，`@` 由 #48 独立实现。桌面与移动端仍须覆盖选区入口、候选状态、三条阻塞、409、过期和回滚不可用反馈。
2. **先统一 #14/#39 合约**：#39 使用 #14 未定义的 `taskMode=writing_candidate`，固定模型 JSON 又缺少 #14 结构化结果的 `kind`；先确定 provider 输入、模型原始输出和应用 SSE `result` 三层字段，再写假服务与测试。
3. **并行建立两个输入契约**：#38 完成代码目录、三级选择与服务端模板化创建；#14 完成案例授权、revision、服务端提示词和结构化候选输出。#38 会删除现有 `title/document` 创建契约，当前后端和 E2E 创建 helper 必须同步改造，不能为测试保留 fallback。
4. **补齐 #37 的隐藏依赖后实现交互**：先交付 #15 的 flush/save/409/reconcile/snapshot/rollback 接口，再以 #14 合约完成 #16 的候选集合、阻塞、取消、失效和会话生命周期，最后由 #37 只做选区入口、内联预览与用户动作。若不单独完成 #15/#16，必须把相同责任显式并入 #37；不能继续让页面编排协议。
5. **并行完成 #22 的 Alpha Next 合约**：#14 的 `find_sources` 必须由 #22 消费 `sourceScopes/urls` 并返回工具事件；不把 #22 串入 #39，但在完整关闭 #14 和 milestone 前完成真实权限检索、联网候选、URL 采集与失败重试 E2E。
6. **并行关闭边界缺陷**：#36 在画布挂载前判定作者/管理员/普通读者去向；#30 先确认现有代码行为，再补齐空查询组件和 E2E 请求次数矩阵。函数长度门禁已由 #29 清理，仍以 `make test` 复验。
7. **最后实现 #39**：固定假 AI、固定模板与固定检索词串起创建、接受候选、提交、审核发布、检索和匿名冻结版本读取；只用 API 读取状态和等待目录收敛。`make test`、`make e2e` 连续两次通过后关闭 milestone。
## 依赖与处置
| Issue | 处置 | 依据 |
| --- | --- | --- |
| #14 | 主链 | #37 的五个选区动作和 #39 的确定性假 AI 都消费其服务端合约；其 `find_sources` 又把 #22 带入完整 Alpha 合约。 |
| #15 | 遗漏的阻塞依赖 | #37 把保存、409、响应丢失、快照与回滚交给 #15；不是 #37 的重复 UI 工作。 |
| #16 | 遗漏的阻塞依赖 | #37 把候选集合、三条阻塞、取消和会话生命周期交给 #16；不是 #14 的提示词/HTTP 合约重复。 |
| #22 | 遗漏的 Alpha Next 依赖 | 不阻塞 #39 固定写作路径，但 #14 当前合约要求它消费 `find_sources` 的范围并定义工具结果；完整关闭 #14 前必须完成。 |
| #29 | 已完成质量门禁 | `make test` 先执行函数长度检查；CI 已改为运行同一门禁。 |
| #30 | 并行回归门禁，先复现 | #39 使用非空固定词；当前组件已对空查询不挂载 AI，先核实现有 E2E 请求数，剩余工作应限于缺失回归，不重复改行为。 |
| #36 | 并行权限门禁 | #39 的匿名公开页只覆盖无作者控件；直接访问工作台的重定向和无内容闪现仍由 #36 独立验收。 |
| #37 | 主链 | 方案 B 已确认；依赖 #14 及 #15/#16 的 Alpha 接口；首期只支持同一文本块的非空选区，不扩到本节、跨块或持久任务。 |
| #38 | 主链并行输入 | 是 #23 完整课程/用途/可管理模板模型的有意 Alpha 切片，不是重复实现；代码目录首期唯一真源。 |
| #39 | 最终集成门禁 | 明示阻塞依赖 #14/#37/#38；审核发布、公开详情和检索目录均复用现有能力。 |
## 重叠与非范围
| Issue | 结论 |
| --- | --- |
| #21 | 设计参考文档清理，与黄金路径无运行时依赖。 |
| #26 | Later，并与 #22 部分重叠网页副本持久化；其“URL 直接创建素材”还与 ADR 0015 的“先成为案例附件、发布后投影为素材”冲突，后续应按附件边界重写。 |
| #27 | 不在 Alpha；#38 明确排除课程，课程检索分面要等 #23 或生产目录提供稳定课程元数据。 |
| #28 | 非 Alpha 功能阻塞且前提部分过时：仓库已有 CI/release workflow；剩余工作是让 CI 精确运行 `make test`、失败 artifact 和 v2 分支保护。当前 v2 未启用保护。 |
| #31 | 生产跨故障域拓扑、恢复演练与容量发布，不属于单机演示 Alpha。 |
| #32 | 生产资源治理，不属于固定代码目录和 demo seed 的 Alpha；与 #23/#38 是后续数据来源关系，不是重复功能。 |
| #33 | 安全扫描工具升级与失败证据，不影响固定假 AI 黄金路径。 |
| #23/#24 | #39 明确不依赖；完整课程/用途/模板管理和完整教学材料套件留待后续。 |
## 建议 milestone 描述
> 教师从“我的案例”按学段、案例类型和模板创建案例，在作者专属画布内生成并确认一次 AI 选区修订，保存后提交审核；管理员发布后，匿名用户可通过非空检索读取同一冻结版本。黄金路径包含 #14、#37、#38、#39；#22 作为 Alpha Next 补全 #14 的真实资料工具合约；#29 验证测试门禁，#30 验证空查询零 AI 请求，#36 验证作者模式访问边界。#37 所需工作版本协调和 AI 写会话接口按 #15/#16 完成或显式纳入 #37。完成条件：#14/#39 provider、模型输出与 SSE 字段一致，`make test` 通过，`make e2e` 连续两次通过，资料工具真实 E2E 通过，桌面与 390px 移动视口无误导入口、内容闪现、横向滚动。课程与完整模板管理、教学材料套件、网页变化复核、生产内容/部署/分支治理和安全扫描工具不在 Alpha 0.1。
