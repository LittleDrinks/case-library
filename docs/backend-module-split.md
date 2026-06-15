# 后端模块拆分边界草案

本文是 issue #158 的第一阶段记录：先明确边界和迁移顺序，不在当前切片中改变 API、
Mongo 文档结构或前端依赖字段。

## 当前职责盘点

- `backend/main.py`：FastAPI app、CORS、认证依赖、OpenAPI 示例、路由函数和少量业务编排。
- `backend/database.py`：Mongo 连接、索引、序列化、校验、用户、案例、版本、AI 审核、
  人工审核、公开检索辅助、统计聚合和兼容函数。
- `backend/schemas.py`：响应模型和 OpenAPI schema 约束。
- `backend/ai_client.py`、`backend/prompts.py`：AI 配置、模型调用和 prompt 元数据。
- `backend/search_engine.py`：公开搜索、推荐、热门和最新案例的薄封装。

## 目标边界

- `backend/db/connection.py`：Mongo client、database getter、counter sync、index init。
- `backend/repositories/`：只放 Mongo collection 读写；保持自增整数 `id` 和现有文档字段。
- `backend/services/cases.py`：案例状态流转、提交、公开快照和软删除编排。
- `backend/services/reviews.py`：AI review 版本快照、人工审核、段落批注校验。
- `backend/services/users.py`：认证用户、密码、用户状态和公开用户序列化。
- `backend/serializers.py`：`serialize_case`、`serialize_public_case`、`serialize_version` 等响应
  序列化，公开字段白名单必须集中在这里。
- `backend/routers/`：按 auth、cases、reviews、ai、public/search/statistics 拆路由；请求/响应
  字段继续由 `schemas.py` 和 FastAPI 参数声明约束。

## 兼容迁移策略

1. 先抽纯函数和序列化函数，`backend/database.py` 保留同名导入或 wrapper，避免破坏现有脚本。
2. 再抽 repository 函数，保持函数签名、返回 dict/list 结构和 Mongo 查询条件不变。
3. 最后拆 `backend/main.py` routers；每一步都对比 `/openapi.json`，确保路径、方法、参数和
   schema 名称不变。
4. 每个阶段至少运行 `backend/test_submit_flow.py` 覆盖提交、版本、AI 审核、人工审核和公开面。

## 文件边界 TODO

- TODO(`backend/database.py`): 将 `serialize_case`、`serialize_public_case`、
  `serialize_version`、公开字段白名单迁到 `backend/serializers.py`，保留兼容导出。
- TODO(`backend/database.py`): 将 `normalize_paragraph_comments`、
  `normalize_structured_ai_review` 和 AI review 版本创建迁到 `backend/services/reviews.py`。
- TODO(`backend/database.py`): 将 `create_case`、`update_case`、`submit_for_review`、
  `delete_case` 迁到 `backend/services/cases.py`，底层 Mongo 写入由 repository 承接。
- TODO(`backend/database.py`): 将 `get_statistics` 及统计缓存迁到 public/statistics service；
  缓存失效点要随案例状态、隐藏、删除、浏览和点赞写入一起迁移。
- TODO(`backend/main.py`): 拆分 routers 时先移动无状态公开端点，再移动需要权限判断的提交和审核
  端点；每次移动后对比 OpenAPI。
