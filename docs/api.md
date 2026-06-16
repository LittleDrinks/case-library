# API 说明

当前 API 以 FastAPI 自动生成文档为准：

- Swagger：`http://127.0.0.1:8001/docs`
- OpenAPI JSON：`http://127.0.0.1:8001/openapi.json`

本文维护人工索引、前端 baseline 依赖的关键契约和当前实现备注。修改 API 时应同步更新
FastAPI schema、测试和本文。

## 全局约定

- 认证：登录后使用 `Authorization: Bearer <token>`。
- Token：HMAC-SHA256 签名，不是 JWT，默认有效期由 `AUTH_TOKEN_TTL` 控制；用户成功改密
  或管理员重置密码后，旧 token 会立即失效。
- 成功响应通常包含 `success: true`。
- 错误响应由 FastAPI 返回 `detail`。
- 当前主键仍是自增整数 `id`。

## 当前端点索引

### 认证

- `POST /api/auth/login`：表单登录，返回用户信息和 token。
- `POST /api/auth/change-password`：用户名 + 旧密码 + 新密码修改密码；成功后该用户旧 token
  立即失效。

### AI

- `GET /api/prompts`：列出服务端 prompt 元数据，需登录。
- `POST /api/ai/chat`：服务端渲染 prompt 并调用 OpenAI-compatible chat，需登录，
  受 `AI_REVIEW_ENABLED` 控制。保留为通用兼容端点。
- `POST /api/cases/{case_id}/ai-review`：教师侧提交前自查接口，需作者或管理员登录。
  服务端生成段落 ID，调用模型，校验 `{ comments, summary }` JSON，并创建只读版本快照。
  明确返回 `disabled`、`unconfigured`、`invalid_model`、`unavailable`、`parse_failed`
  或 `invalid_contract` 等状态。

### 案例

- `GET /api/cases`：案例列表。默认公开已通过案例；公开列表展示审核通过时绑定的版本快照；
  草稿、作者视图和管理视图需登录。
- `GET /api/cases/{case_id}`：案例详情。公开已通过案例可匿名查看；匿名公开详情展示审核通过
  时绑定的版本快照。
- `POST /api/cases`：创建案例，需登录。支持 `auto_process=true`。
- `PUT /api/cases/{case_id}`：更新案例并在正文、来源材料等字段变更时写版本记录，需作者或管理员；
  作者只能更新草稿或退回修改案例，待审核或已通过案例需先由管理员退回修改。
- `POST /api/cases/{case_id}`：兼容更新端点，同上。
- `DELETE /api/cases/{case_id}`：软删除案例，需作者或管理员。案例状态标记为
  `deleted` 并记录 `deleted_at`/`deleted_by`，不物理删除关联的 versions、reviews、
  deployments；普通列表和详情会自动过滤已删除案例，内部查询可通过
  `include_deleted=True` 或直接访问数据库获取。
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

## 提案：案例类型多选契约（issue #97，尚未实现）

当前实现仍以单字符串 `type` 作为案例类型字段。为满足 `docs/prd.md` 中“案例类型支持多选”的
产品要求，后续实现建议新增 `types: string[]` 作为规范字段，并在一个兼容窗口内保留 `type`
作为主类型/旧客户端回退字段。

- 写入契约：`POST /api/cases`、`PUT /api/cases/{case_id}` 和兼容 `POST /api/cases/{case_id}`
  接受 `types` 数组；表单提交可使用重复字段 `types=TYPE_A&types=TYPE_C`，也可在兼容期继续
  发送旧字段 `type=TYPE_A`。若同时传入二者，以 `types` 为准，`type` 自动取 `types[0]`。
- 读取契约：案例列表、详情、版本、公开搜索、推荐、热门、最新和统计响应均返回 `types`；
  兼容期继续返回 `type = types[0]`。历史仅含字符串 `type` 的数据读出时规范化为
  `types: [type]`。
- 校验契约：`types` 去重并保持用户选择顺序；只接受 `/api/constants.case_types` 中存在的
  类型码；空值回退到当前默认 `["TYPE_A"]`。
- 搜索契约：`/api/search/advanced?type=TYPE_A` 保持单类型过滤入口，语义改为命中
  `types` 中包含该值的案例（OR 语义）。
- 统计契约：`/api/statistics.data.by_type` 按每个类型标签计数；一个多类型案例会分别计入每个
  已选类型，`total_cases` 仍按案例数计数。
- 迁移策略：不需要阻塞式数据库迁移；在序列化读取、版本快照和写入路径中双写/规范化即可。
  可选的一次性后台修正脚本只用于把旧文档补齐 `types`，不改变公开 API 兼容语义。

## 前端 baseline 契约

以下字段是当前前端 baseline 依赖的后端契约。第一阶段后端拆分不得改变路径、请求字段、
响应字段名或 Mongo 文档语义。

### 案例列表和详情

- `GET /api/cases?status=approved` 可匿名访问，只返回已通过且未隐藏案例；`status=draft`、
  `pending_review`、`needs_revision`、`all` 或 `author=<username>` 视图需要登录并按作者/管理员
  权限过滤。
- 列表响应：`{ success, data, total }`；`data[]` 至少包含 `id`、`title`、`type`、`theme`、
  `author`、`department`、`status`、`created_at`、`updated_at`、`submitted_at`、`review_at`、
  `display_at`、`view_count`、`like_count`、`is_hidden`、`keywords`；列表项不返回大字段
  `content`、`source_material`。
- `GET /api/cases/{case_id}` 公开已通过案例可匿名访问；草稿、隐藏案例、未通过案例需要作者或
  管理员权限。公开读者看到的是公开字段白名单；作者/管理员看到内部字段。
- 已通过案例如果存在 `reviewed_version_id`，公开列表、公开详情、公开搜索、推荐、热门、最新和
  统计均以该审核通过版本快照的标题、正文、来源材料、类型/主题、作者、院系和关键词为准；
  其中公开列表只返回轻量元数据，不返回正文和来源材料。

### 我的提交

- 前端“我的提交”使用 `GET /api/cases?author=<当前用户名>&status=all` 读取作者视图。
- 作者可编辑 `draft` 和 `needs_revision`；作者不可编辑 `pending_review` 或 `approved`，
  这些状态需要管理员退回后才能修改。
- `POST /api/cases/{case_id}/submit` 接受可选表单字段 `version_id`；未传时绑定当前最新版本。
  成功后案例进入 `pending_review`，写入 `submitted_at` 和 `submitted_version_id`。

### 版本记录

- `GET /api/versions/{case_id}` 仅作者或管理员可见，响应 `data[]` 按 `version_number` 倒序。
- 版本项包含 `id`、`case_id`、`version_number`、`title`、`type`、`theme`、`content`、
  `source_material`、`author`、`department`、`keywords`、`owner_username`、`created_by`、
  `changed_by`、`change_reason`、`created_at`、`paragraphs`、`ai_review`、`admin_comments`。
- 正文、来源材料、标题、类型/主题、作者、院系或关键词变更会创建版本；AI review 也创建只读
  版本快照。

### AI 审核

- `POST /api/cases/{case_id}/ai-review` 需要作者或管理员登录。普通作者只能对 `draft` 或
  `needs_revision` 案例发起；`pending_review` 和 `approved` 会被锁定。
- 请求体是 JSON 对象，可选 `model` 字符串。服务端生成 `paragraphs[]`，调用后端配置的模型，
  校验 `{ comments, summary }` 结构，并创建版本快照。
- 成功响应：`{ success: true, status: "ok", data: { version, comments, summary } }`。
  `version.ai_review.comments` 与响应 `comments` 同源；`version.ai_review.summary` 与响应
  `summary` 同源；案例文档会更新 `latest_review_version_id` 和兼容字段 `ai_reviews`。
- 失败状态使用现有 `disabled`、`unconfigured`、`invalid_model`、`unavailable`、
  `parse_failed`、`invalid_contract`，前端按 `status` 和 `detail` 展示。

### 人工审核

- `POST /api/reviews/{case_id}` 仅管理员可用，表单字段为 `comment`、`status`、可选
  `version_id`、可选 `paragraph_comments` JSON 字符串。
- `status=approve/approved` 将案例置为 `approved`；`reject/rejected/needs_revision` 将案例置为
  `needs_revision`；历史兼容 `rejected` 映射到退回修改。
- 审核写入 `reviews` 记录，保留 `version_id` 和规范化后的 `paragraph_comments`；如果传入
  段落批注，也会追加到对应版本的 `admin_comments`。
- `GET /api/reviews/{case_id}` 仅作者或管理员可见。

### 公开字段白名单

匿名公开详情、搜索、推荐、热门和最新接口只返回以下公开字段：

- `id`
- `title`
- `type`
- `theme`
- `content`
- `source_material`
- `author`
- `department`
- `status`
- `created_at`
- `updated_at`
- `submitted_at`
- `review_at`
- `display_at`
- `view_count`
- `like_count`
- `is_hidden`
- `keywords`

公开接口不得返回 `ai_reviews`、`ai_review`、`admin_comments`、`paragraph_comments`、
`prompt`、`prompt_id`、`model`、`submitted_version_id`、`reviewed_version_id`、
`latest_review_version_id`、`owner_username` 等内部字段。
匿名公开列表同样遵循该内部字段边界，但列表项额外省略 `content` 和 `source_material`。

## 公开字段边界

匿名公开详情、搜索、推荐、热门和最新接口只返回已通过且未隐藏案例的公开字段：
正文、元数据、类型/主题、标签、来源材料、浏览和点赞计数。不返回 AI 批注、人工批注、
prompt、model 或版本内部字段。匿名公开列表返回同一批案例的轻量元数据，省略正文和来源材料。
