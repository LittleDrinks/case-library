# 后端模块拆分边界草案

本文记录后端拆分边界和迁移顺序。issue #167 已落地第一个 concrete rewrite slice：
后端运行时进入 `backend/app` 包，并在不改变 API、Mongo 文档结构或前端依赖字段的前提下
引入 package imports。issue #168 的第一片已开始把重 HTTP route 的业务编排迁入
`backend/app/domains/` service 层。issue #169 将 API schema、case serializer 和 API-facing
常量继续按 domain/shared 边界收拢。issue #170 已将运行时代码、测试和脚本迁到 canonical
`backend.app.*`、`backend.repositories.*`、`backend.services.*` 边界，并移除已无活跃调用方的
旧 top-level prompt/search/case processor 模块。alpha 结构清理已继续删除无内部调用方的
top-level 兼容 facade；新增内部代码不得重新引入旧 security、dependencies、schema、
serializer、database、main 或 `backend/routers/*` 依赖。

## 当前职责盘点

- `backend/app/main.py`：canonical FastAPI app、CORS、OpenAPI 示例、路由装配和静态资源装配。
- `backend/app/api/router.py`：API router 聚合入口。
- `backend/app/api/routes/`：canonical API route 实现，按 auth、ai、cases、reviews、public、
  static 拆分；route 只保留 FastAPI 参数、响应模型和 HTTP 错误映射。
- `backend/app/domains/cases/service.py`：案例列表/detail/create/update/delete/submit/visibility/like
  的业务权限、状态和 repository 编排；route 只保留 FastAPI 参数和 HTTP 错误映射。
- `backend/app/domains/cases/processing.py`：`auto_process` 路径使用的案例模板、关键词提取和
  自动处理 helper；旧 `backend/case_processor.py` 已移除。
- `backend/app/domains/cases/schemas.py`：案例、版本和通用 success response 的 Pydantic schema。
- `backend/app/domains/cases/serializers.py`：案例、版本、公开字段白名单和审核版本快照覆盖的
  API serializer 实现。
- `backend/app/domains/ai/service.py`：AI prompt 渲染、模型配置校验、模型调用、JSON 解析和
  AI review version 保存编排；route 只保留 JSON body 解析及既有响应体映射。
- `backend/app/domains/ai/schemas.py`：AI prompt/chat schema，包含稳定 OpenAPI 组件名
  `AIChatRequest`。
- `backend/app/domains/reviews/schemas.py`、`backend/app/domains/users/schemas.py`、
  `backend/app/domains/public/schemas.py`：人工审核、登录用户、公开检索/统计/constants schema。
- `backend/app/shared/constants.py`：前后端共享的 API-facing 类型、主题和状态标签；数据库枚举仍
  属于 `backend/db/constants.py`。
- `backend/app/domains/public/service.py`：公开搜索 facade，供 public route 使用；公开查询实现仍在
  `backend/services/public.py`。旧 `backend/search_engine.py` 已移除。
- `backend/app/core/`：认证 token helper、当前用户解析和 FastAPI bearer 依赖；旧
  `backend/security.py` 和 `backend/dependencies.py` 兼容导出已移除。
- `backend/routers/`：旧 route import surface 已移除；route import 必须使用
  `backend/app/api/routes/` canonical 实现。
- `backend/db/`：Mongo 连接、索引、计数器、时间格式化、常量和输入校验；`backend/app/db/database.py`
  显式聚合 canonical db/repository/service 导出，供 app package 内部汇总导入使用。
- 旧 `backend/serializers.py` 兼容导出已移除；serializer import 必须使用
  `backend/app/domains/cases/serializers.py`。
- `backend/repositories/`：用户、案例、版本和审核 Mongo 读写 helper。
- `backend/services/public.py`：公开检索、推荐、热门、最新和统计缓存。
- `backend/services/cache.py`：公开读缓存 seam；当前承载统计缓存的 in-process 实现和统一失效入口。
- `backend/services/abuse.py`：公开浏览/点赞类写入的匿名身份和限流 seam；默认策略保持兼容，不阻断请求。
- `backend/db/transactions.py`：Mongo 多集合写入的事务/补偿边界；当前在未启用 session transaction
  的情况下提供 best-effort compensation scope。
- 旧 `backend/schemas.py` 兼容导出已移除；Pydantic 模型定义已按 `cases`、`reviews`、
  `users`、`public`、`ai` domain 拆分。OpenAPI 组件名保持类名不变。
- `backend/ai_client.py`：OpenAI-compatible 模型调用边界。Prompt 元数据和内容加载位于
  `backend/app/domains/ai/prompts/`；旧 `backend/prompts.py` 已移除。

## 目标边界

- `backend/db/connection.py`：Mongo client、database getter、index init。
- `backend/db/counters.py`：自增整数 `id` 计数器同步和分配。
- `backend/db/datetime.py`、`backend/db/validators.py`：时间格式化、输入校验和字段规范化。
- `backend/repositories/`：只放 Mongo collection 读写；保持自增整数 `id` 和现有文档字段。
- `backend/repositories/cases.py`：案例创建、更新、软删除、列表、隐藏和浏览/点赞计数写入。
- `backend/repositories/versions.py`：版本列表、最新版本查找和 AI review 版本创建。
- `backend/repositories/reviews.py`：提交审核、人工审核和审核记录查询。
- `backend/repositories/users.py`：认证用户、密码、用户状态和公开用户序列化。
- `backend/app/domains/reviews/helpers.py`：无数据库副作用的 AI review/段落批注规范化 helper。
- `backend/services/public.py`：公开查询、推荐、热门、最新和统计缓存；统计缓存失效通过
  `backend/services/cache.py` 的公开读缓存 seam 统一触发，由会改变公开案例状态或公开计数的
  repository 写入点调用。
- `backend/services/abuse.py`：公开浏览、点赞、取消点赞等匿名写入的身份提取和限流 seam；默认
  limiter 为兼容模式，后续可接入 Redis 或网关限流。
- `backend/db/transactions.py`：跨 cases、versions、reviews 的多集合写入必须显式进入该边界；
  若未来启用 Mongo session transaction，应优先在此处替换实现。
- `backend/app/domains/cases/processing.py`：案例自动处理、模板读取和关键词提取；如果后续替换为
  LLM 分类器，仍应从 case domain 编排进入 repository。
- `backend/app/domains/public/service.py`：只放 route-facing facade，避免 public route 回引旧
  top-level search module。
- `backend/app/domains/cases/serializers.py`：`serialize_case`、`serialize_public_case`、
  `serialize_version` 等响应序列化，公开字段白名单必须集中在这里；不再通过
  `backend/serializers.py` 兼容层导入。
- `backend/app/shared/constants.py`：只放 API-facing 标签常量，不放 Mongo 连接配置、数据库枚举或
  校验状态集合。
- `backend/app/api/routes/`：按 auth、cases、reviews、ai、public/search/statistics 承载路由；
  请求/响应字段继续由 domain schema 和 FastAPI 参数声明约束。后续继续拆兼容层时不应把
  数据库写入编排回流到路由层。

## 兼容迁移策略

1. DONE：已抽纯函数和序列化函数；根目录 dev seed 已改用 canonical db/repository import，
   旧 top-level database 兼容入口已移除。
2. DONE：已抽 repository 函数，保持函数签名、返回 dict/list 结构和 Mongo 查询条件不变。
3. DONE：已拆旧 main routers，`backend/app/main.py` 保留 `/openapi.json` 路径、方法、自定义
   requestBody 示例和 `HTTPBearer` security scheme。
4. DONE：`backend/app/main.py` 成为唯一 ASGI app 入口；旧 top-level main 兼容入口已移除；
   Compose、Dockerfile 和 `make run` 使用 `backend.app.main:app`。
5. DONE：`backend/app/api/routes/` 承载 route 实现；旧 `backend/routers/` 兼容导出已删除，
   tests/scripts/runtime 不再 import 旧 route/data/schema/search/prompt/case processor surface。
6. DONE：无内部调用方的旧 top-level security、dependency、schema、serializer、database、
   main 和 `backend/routers/*`
   兼容 facade 已删除。
7. 每个阶段至少运行 `backend/tests/integration/test_submit_flow.py` 覆盖提交、版本、AI 审核、人工审核和公开面。

## 文件边界 TODO

- DONE(case serializer domain): 将 `serialize_case`、`serialize_public_case`、
  `serialize_version` 和公开字段白名单迁到 case domain serializer；旧 serializer 兼容导出
  已在 alpha 清理中移除。
- DONE(`backend/services/reviews.py`): `split_paragraphs`、`normalize_paragraph_comments`、
  `normalize_structured_ai_review` 已迁到 `backend/app/domains/reviews/helpers.py`；
  旧 top-level database 兼容入口已在 alpha 清理中移除。
- DONE(version repository): 将 AI review 版本创建迁到 `backend/repositories/versions.py`。
- DONE(case and review repositories): 将 `create_case`、`update_case`、`delete_case`、
  浏览/点赞和列表 helper 迁到 `backend/repositories/cases.py`，将 `submit_for_review`、
  `review_case` 和审核记录查询迁到 `backend/repositories/reviews.py`。
- DONE(public service cache): 将 `get_statistics` 及统计缓存迁到 `backend/services/public.py`；
  缓存失效点要随案例状态、隐藏、删除、浏览和点赞写入一起迁移。
- DONE(app/router package migration): 旧 main router 和 helper surface 已迁入 `backend/app/main.py`、
  `backend/app/api/routes/*`、`backend/app/core/*` 和 domain service；测试与配置已改用
  canonical import，旧 top-level main 文件已移除。
- DONE(`backend/app/main.py`): canonical FastAPI app 已迁入 `backend/app` 包；`backend/app/api/router.py`
  聚合 API router；`backend/app/core/`、`backend/app/db/` 提供本轮 package import 包装。
- DONE(`backend/app/domains/cases/service.py`、`backend/app/domains/ai/service.py`): issue #168
  第一片已将 cases 和 AI 两个重 route 的非 HTTP 编排迁入 domain service。
- DONE(`backend/app/domains/*/schemas.py`、`backend/schemas.py`): issue #169 已将 Pydantic schema
  按 cases/reviews/users/public/ai 拆分；旧 `backend/schemas.py` 兼容导出已在 alpha 清理中移除。
- DONE(`backend/app/domains/cases/serializers.py`、`backend/serializers.py`): issue #169 已将 case
  serializer 实现迁入 case domain；旧 `backend/serializers.py` 兼容导出已在 alpha 清理中移除。
- DONE(`backend/app/shared/constants.py`、`backend/app/api/routes/public.py`): issue #169 已将
  `/api/constants` 的 API-facing 类型、主题和状态标签迁入 shared constants，响应结构不变。
- DONE(`backend/app/api/routes/*`、`backend/routers/*`): issue #170 已将 route 实现迁入
  canonical app routes；旧 `backend/routers/` 兼容导出已在 alpha 清理中移除。
- DONE(`backend/app/domains/cases/processing.py`): issue #170 已迁入 `auto_process` 相关行为并移除
  `backend/case_processor.py`。
- DONE(`backend/app/domains/public/service.py`): issue #170 已迁入公开搜索 facade 并移除
  `backend/search_engine.py`。
- DONE(`backend/app/domains/ai/prompts/`): 运行时 prompt 加载器和查询 API 已迁入 AI domain；
  旧 top-level prompt facade 和 registry package 均已移除。
- DONE(`backend/services/cache.py`、`backend/db/transactions.py`、`backend/services/abuse.py`):
  issue #171 已为公开读缓存、多集合写入和公开交互反滥用加入保守 seam；API 行为保持兼容。
