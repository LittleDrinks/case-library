# API 说明

当前 API 以 FastAPI 自动生成文档为准：

- Swagger：`http://127.0.0.1:8001/docs`
- OpenAPI JSON：`http://127.0.0.1:8001/openapi.json`

本文只维护人工索引和当前实现备注，不再维护长篇手写契约表。修改 API 时应同步更新
FastAPI schema、测试和本文。

## 全局约定

- 认证：登录后使用 `Authorization: Bearer <token>`。
- Token：HMAC-SHA256 签名，不是 JWT，默认有效期由 `AUTH_TOKEN_TTL` 控制。
- 成功响应通常包含 `success: true`。
- 错误响应由 FastAPI 返回 `detail`。
- 当前主键仍是自增整数 `id`。

## 当前端点索引

### 认证

- `POST /api/auth/login`：表单登录，返回用户信息和 token。
- `POST /api/auth/change-password`：用户名 + 旧密码 + 新密码修改密码。

### AI

- `GET /api/prompts`：列出服务端 prompt 元数据，需登录。
- `POST /api/ai/chat`：服务端渲染 prompt 并调用 OpenAI-compatible chat，需登录，
  受 `AI_REVIEW_ENABLED` 控制。保留为通用兼容端点。
- `POST /api/cases/{case_id}/ai-review`：教师侧提交前自查接口，需作者或管理员登录。
  服务端生成段落 ID，调用模型，校验 `{ comments, summary }` JSON，并创建只读版本快照。
  明确返回 `disabled`、`unconfigured`、`invalid_model`、`unavailable`、`parse_failed`
  或 `invalid_contract` 等状态。

### 案例

- `GET /api/cases`：案例列表。默认公开已通过案例；草稿、作者视图和管理视图需登录。
- `GET /api/cases/{case_id}`：案例详情。公开已通过案例可匿名查看。
- `POST /api/cases`：创建案例，需登录。支持 `auto_process=true`。
- `PUT /api/cases/{case_id}`：更新案例并在正文、来源材料等字段变更时写版本记录，需作者或管理员。
- `POST /api/cases/{case_id}`：兼容更新端点，同上。
- `DELETE /api/cases/{case_id}`：软删除案例，需作者或管理员。
- `POST /api/cases/{case_id}/submit`：提交人工审核，需作者或管理员；可用 `version_id`
  绑定提交版本。
- `POST /api/cases/{case_id}/like`：公开点赞。
- `POST /api/cases/{case_id}/unlike`：取消一次点赞。
- `POST /api/cases/{case_id}/visibility`：管理员隐藏/展示案例。

### 审核和历史

- `POST /api/reviews/{case_id}`：管理员审核，通过或退回；可传 `version_id` 和
  `paragraph_comments` 写入段落级人工批注。
- `GET /api/reviews/{case_id}`：查看人工审核记录，仅作者或管理员可见。
- `GET /api/versions/{case_id}`：查看版本记录，仅作者或管理员可见。版本快照包含标题、
  正文、来源材料、类型/主题、创建人、段落 ID、AI 批注和人工批注。

### 公开检索和统计

- `GET /api/search`：关键词搜索。
- `GET /api/search/advanced`：类型、主题、状态、关键词筛选。
- `GET /api/recommendations/{case_id}`：相关推荐。
- `GET /api/trending`：热门案例。
- `GET /api/latest`：最新案例。
- `GET /api/statistics`：公开统计。
- `GET /api/constants`：类型、主题、状态标签。

## 状态映射

当前案例状态：

- `draft`：草稿
- `pending_review`：待审核
- `approved`：已通过
- `needs_revision`：退回修改

历史兼容中，部分接口仍接受或映射 `rejected`，语义等同“退回修改”，不是永久拒绝。

## 公开字段边界

匿名公开列表、详情、搜索、推荐、热门和最新接口只返回已通过且未隐藏案例的公开字段：
正文、元数据、类型/主题、标签、来源材料、浏览和点赞计数。不返回 AI 批注、人工批注、
prompt、model 或版本内部字段。
