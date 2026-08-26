# 目标架构

## 现状盘点

后端 17.4k 行 / 11 个模块，前端 6.2k 行。FastAPI 同步 pymongo 单体，MongoDB 副本集为业务真源，Meilisearch 承载检索目录（ADR 0019），MinIO 存文件。模块内 routes/service/models 三层，跨模块依赖只有 annotations→cases、attachments→cases、case_materials→{cases,materials,attachments,search.outbox} 一组单向边，结构健康，不需要推翻。

| 模块 | 行数 | 判定 |
| --- | --- | --- |
| search | 2542 | outbox 租约/代际 CAS/索引原子切换经 failover 与 1000 VU 负载验收，保留 |
| cases | 1234 | 核心域（lifecycle/snapshots/document_schema），保留 |
| ai | 945 | provider 是 300 行手搓 urllib3+SSE 客户端，routes 是纯 chat 直通，无工具调用——最大替换点 |
| materials | 835 | 导入在请求线程内同步执行，批量任务需异步化 |
| attachments | 577 | 文本抽取只支持 docx+纯文本，手搓 zip 安全检查 |
| auth | 425 | bcrypt+cookie session+CSRF，小而对，保留 |
| documents | 339 | python-docx 手写固定版式渲染，替换为模板填充 |
| case_materials | 255 | 保留 |
| annotations | 247 | 服务端 quote 前缀渐进匹配重挂，换位置映射方案 |
| knowledge | 109 | 只有 seed，PRD 要求的 7 门课知识库基本空白 |

前端无 UI 库、无状态库；api.js/SSE 流解析/useAutosave/useCrashDraft 小而对，保留。WorkbenchView 513 行、AssistantRail 397 行是画布工作台本体，随 agent 改造重构。

## 骨架不变

单体进程布局、compose 拓扑、Mongo 真源 + Meilisearch 只读目录、outbox 事件捕获、版本冻结/审核流、素材分级模型全部保留。变更只发生在四类自研轮子的替换和 PRD v2 缺口的补齐方式上。

## 替换清单

| 自研代码 | 复用目标 | 方式 |
| --- | --- | --- |
| `ai/provider.py` 300 行 urllib3+SSE+queue+线程 | `openai` 官方 SDK | `OpenAI(base_url=…, http_client=…)` 注入钉扎公网 IP 的 httpx transport，保留 SSRF 防护；SDK 接管 SSE 解析、重试、超时、工具调用协议。`ProviderSelection` seam 不变，测试面（test_ai_config、ai-smoke）不变 |
| `documents/render.py`+`styles.py`+`fonts.py` 339 行 | `docxtpl`（python-docx-template） | 版式做成 Word 模板文件放 `assets/docx-templates/`，Jinja2 占位填充正文/元数据；版式调整不再改代码。现有 golden 测试改期望产物即可 |
| `attachments/text.py` docx+纯文本抽取 | `markitdown`（Microsoft） | PDF/DOCX/PPTX/XLSX 统一转 Markdown 供索引与 AI 引用；保留现有大小上限与 zip 炸弹防护壳，libarchive-c 继续解 zip/rar5 |
| 版本对比基于 `diff` 包的纯文本 diff | `prosemirror-changeset` | 在 ProseMirror 文档层面计算增删片段，前后端共享同一 change 结构，「文字级增删高亮」直接渲染 |
| 批注 quote 前缀模糊重挂（服务端） | ProseMirror Mapping（编辑器原生机制） | 锚点改为「绝对位置+quote」双存储；编辑会话内每次事务用 mapping 重映射位置并回写，落库时 quote 仅作跨会话冲突时的兜底校验。「原文已变动」降级路径保留 |

## 新增子系统选型

| 子系统（PRD v2） | 复用目标 | 决策 |
| --- | --- | --- |
| Agent 工具环 | `pydantic-ai` | typed 工具注册、结构化输出（写作候选/候选批注）、OpenAI 兼容 base_url、流式事件；pydantic 2 与现栈同构。工具即现有服务函数薄封装：`search_corpus`=search.service，`fetch_url`=trafilatura 抽取后走 attachments 快照存储，写工具沿用 ADR 0016 的待确认修订语义。修订阻塞、批前快照是应用层状态机，不进框架 |
| 联网检索 `web_search` | SearXNG | compose 加一个服务，JSON API 无密钥，校内可自托管；结果仅作候选不入库 |
| 网页采集副本 | `trafilatura` | 正文+元数据+发布时间一次抽取，替换不了的部分（截图类）明确不支持 |
| 成套教学材料导出 | `docxtpl` 多模板 | 教案/讨论题/PPT 提纲各一个 Word 模板，zipfile 打包整套；对外申报版先跑脱敏扫描再填模板 |
| 知识库 | `markitdown` 入库 + 现有 indexer | PDF 教材转 Markdown→按章节切分→knowledge_sections 集合→复用现有目录投影，无需新检索设施 |
| 自然语言检索语义层 | Meilisearch hybrid search（embedders） | REST embedder 指向平台 AI 的 OpenAI 兼容 `/embeddings`，零新增中间件；同义词用引擎 settings 配置，不写分词代码 |
| 可信度/推荐排序 | Meilisearch customRanking | `sourceTrust`、`publishedAt` 作排序规则，点赞计数弱因子；不引入图数据库，ego 图维持 d3-force |
| 批量导入任务异步化 | 泛化 `search/outbox.py` 租约机制为 `core/jobs.py` | Mongo 集合作队列+租约+心跳，独立 worker 容器消费；导入路由立即返回 job id，进度走现有 job 状态查询。agent 长任务的「当前阶段/失败原因/重试」同一机制 |
| 对外导出脱敏提示 | 自写最小扫描 | 规则扫文档 JSON 与挂载素材访问级别，列出需确认项；无成熟 OSS 匹配中文场景，不自欺 |
| 管理后台界面 | Element Plus | 账号/知识/素材分级/白名单/类型/模板/审核全是列表+表单+对话框，Vue 3 中文生态事实标准 MIT；新页面一律用，旧页面触到才迁 |
| 教师档案与偏好 | 普通 Mongo 集合 + Element Plus 表单 | 无需专门设施 |

## 明确不引入

Redis/Celery/arq（job 用 Mongo 租约）、Neo4j（引用关系聚合查询够用）、fastapi-users/motor 重写 auth、litellm proxy（多一层运维面，openai SDK 已覆盖）、pinia/TanStack Query（session.js+api.js 通过删除测试）、独立向量库（hybrid search 内建）。

## 迁移顺序

每步独立可交付，全部落在既有测试面内：

1. openai SDK 适配器替换 `ai/provider.py`（test_ai_config、ai-smoke 回归）
2. docxtpl 导出替换 documents 渲染三件套（test_docx_export golden 更新）
3. markitdown 抽取接入导入管线（test_attachments、test_material_import_e2e）
4. `core/jobs.py` + 导入异步化（material-import e2e）
5. trafilatura 采集 + SearXNG 上线，`fetch_url` 工具落地（attachment e2e）
6. pydantic-ai agent 环：三个读工具 + 写工具确认门（ADR 0016 语义，workbench e2e）
7. 知识库入库 CLI + 管理页（search catalog 回归）
8. 成套教学材料生成与整套导出 + 脱敏扫描（验收场景 1/6）
9. hybrid search embedder + 同义词 + customRanking（search e2e、load-rate）
10. Element Plus 管理后台改造 + 教师档案/偏好/点赞

约束：所有新封装遵守函数 <20 行质量门；库调用写在模块边界内的薄适配器里，业务逻辑不渗透到第三方类型。
