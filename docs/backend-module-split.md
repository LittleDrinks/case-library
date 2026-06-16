# 后端模块拆分边界草案

本文是 issue #158 的第一阶段记录：先明确边界和迁移顺序，不在当前切片中改变 API、
Mongo 文档结构或前端依赖字段。

## 当前职责盘点

- `backend/main.py`：FastAPI app、CORS、OpenAPI 示例、路由装配和静态资源装配。
- `backend/security.py`、`backend/dependencies.py`：认证 token helper、当前用户解析和 FastAPI
  bearer 依赖。
- `backend/routers/`：按 auth、ai、cases、reviews、public、static 拆分 API 和前端 fallback 路由。
- `backend/database.py`：兼容导出层，继续提供旧调用方依赖的同名函数、常量和 `__main__`
  初始化入口。
- `backend/db/`：Mongo 连接、索引、计数器、时间格式化、常量和输入校验。
- `backend/serializers.py`：Mongo 文档和公开案例响应序列化。
- `backend/repositories/`：用户、案例、版本和审核 Mongo 读写 helper。
- `backend/services/public.py`：公开检索、推荐、热门、最新和统计缓存。
- `backend/schemas.py`：响应模型和 OpenAPI schema 约束。
- `backend/ai_client.py`、`backend/prompts.py`：AI 配置、模型调用和 prompt 元数据。
- `backend/search_engine.py`：公开搜索、推荐、热门和最新案例的薄封装。

## 目标边界

- `backend/db/connection.py`：Mongo client、database getter、index init。
- `backend/db/counters.py`：自增整数 `id` 计数器同步和分配。
- `backend/db/datetime.py`、`backend/db/validators.py`：时间格式化、输入校验和字段规范化。
- `backend/repositories/`：只放 Mongo collection 读写；保持自增整数 `id` 和现有文档字段。
- `backend/repositories/cases.py`：案例创建、更新、软删除、列表、隐藏和浏览/点赞计数写入。
- `backend/repositories/versions.py`：版本列表、最新版本查找和 AI review 版本创建。
- `backend/repositories/reviews.py`：提交审核、人工审核和审核记录查询。
- `backend/repositories/users.py`：认证用户、密码、用户状态和公开用户序列化。
- `backend/services/reviews.py`：无数据库副作用的 AI review/段落批注规范化 helper。
- `backend/services/public.py`：公开查询、推荐、热门、最新和统计缓存；统计缓存失效由会改变
  公开案例状态或公开计数的 repository 写入点调用。
- `backend/serializers.py`：`serialize_case`、`serialize_public_case`、`serialize_version` 等响应
  序列化，公开字段白名单必须集中在这里。
- `backend/routers/`：按 auth、cases、reviews、ai、public/search/statistics 拆路由；请求/响应
  字段继续由 `schemas.py` 和 FastAPI 参数声明约束。当前已完成 `backend/main.py` 的路由拆分，
  后续继续拆 `backend/database.py` 时不应把数据库写入编排回流到路由层。

## 兼容迁移策略

1. DONE：已抽纯函数和序列化函数，`backend/database.py` 保留同名导入，避免破坏现有脚本。
2. DONE：已抽 repository 函数，保持函数签名、返回 dict/list 结构和 Mongo 查询条件不变。
3. DONE：已拆 `backend/main.py` routers，保留 `/openapi.json` 路径、方法、自定义 requestBody
   示例和 `HTTPBearer` security scheme。
4. 每个阶段至少运行 `backend/tests/integration/test_submit_flow.py` 覆盖提交、版本、AI 审核、人工审核和公开面。

## 文件边界 TODO

- DONE(`backend/database.py`): 将 `serialize_case`、`serialize_public_case`、
  `serialize_version`、公开字段白名单迁到 `backend/serializers.py`，保留兼容导出。
- DONE(`backend/services/reviews.py`): `split_paragraphs`、`normalize_paragraph_comments`、
  `normalize_structured_ai_review` 已迁出并由 `backend/database.py` 兼容导出。
- DONE(`backend/database.py`): 将 AI review 版本创建迁到 `backend/repositories/versions.py`。
- DONE(`backend/database.py`): 将 `create_case`、`update_case`、`delete_case`、
  浏览/点赞和列表 helper 迁到 `backend/repositories/cases.py`，将 `submit_for_review`、
  `review_case` 和审核记录查询迁到 `backend/repositories/reviews.py`。
- DONE(`backend/database.py`): 将 `get_statistics` 及统计缓存迁到 `backend/services/public.py`；
  缓存失效点要随案例状态、隐藏、删除、浏览和点赞写入一起迁移。
- DONE(`backend/main.py`): 已拆到 `backend/routers/auth.py`、`ai.py`、`cases.py`、`reviews.py`、
  `public.py`、`static.py`，并保留 `main.create_auth_token`、`main.verify_auth_token`、
  `main.get_current_user`、`main.render_prompt`、`main._build_paragraph_review_prompt` 兼容导出。
