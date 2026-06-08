<!--
Migrated on 2026-06-06 from recovered WeChat attachment:
E:\xwechat_files\wxid_x6e64hefjyox12_ba3b\msg\attach\e94fbe1ac58d09c830a799592fea2f62\2026-05\Rec\efe0cc6fcce98913\F\2\API-CONTRACT.md
This is recovered target-state design material. The current implementation
reference is generated from FastAPI at /docs and /openapi.json.
-->

# API Contract v1.1 (Alpha Target Reference)

> 本文档是从历史设计稿恢复的目标态 API 参考，不是当前实现自动生成的
> API 文档。当前实现以 FastAPI Swagger `/docs` 和 OpenAPI
> `/openapi.json` 为准；当两者不一致时，先以当前实现和 GitHub issue
> 验收条件推进，再更新目标契约或后端实现。

> 生成日期: 2026-05-25
> 基于 Phase 4-9 设计文档
> 适用分支: feature/rewrite-ai
> **注意:** 本文档为"目标态"契约，标注 [已实现] 的端点已存在于当前代码，未标注的端点需在对应 Phase 中实现

---

## 全局约定

### 认证

| 端点 | 是否需要认证 |
|------|-------------|
| `POST /api/auth/login` | 否 |
| `POST /api/auth/change-password` | 否（但须提供正确旧密码） |
| `GET /api/cases` | 公开列表不需要；查看 draft/他人案例需要 |
| `GET /api/cases/:id` | 公开详情不需要；查看 draft 需要 |
| `GET /api/search` | 否 |
| `GET /api/search/advanced` | 否 |
| `GET /api/statistics` | 否 |
| `GET /api/constants` | 否 |
| `GET /api/recommendations/:id` | 否 |
| `GET /api/trending` | 否 |
| `GET /api/latest` | 否 |
| 其余所有端点 | **需要** `Authorization: Bearer <token>` |

Token 格式为 HMAC-SHA256 签名（非 JWT），有效期 7 天。

### 统一响应格式

**成功:**
```json
{
  "success": true,
  "data": { ... },
  "message": "可选描述"
}
```

**错误:**
```json
{
  "success": false,
  "detail": "错误信息"
}
```

### 通用错误码

| 状态码 | 含义 | 触发场景 |
|--------|------|----------|
| 400 | 请求参数错误 | 缺少必填字段、字段类型错误、非法状态值 |
| 401 | 未认证 | 缺少 Token、Token 过期、Token 无效 |
| 403 | 无权访问 | 非管理员访问管理端点、非作者修改他人草稿 |
| 404 | 资源不存在 | 案例/Prompt/用户不存在 |
| 409 | 状态冲突 | 草稿已提交后重复提交、点赞已点重复点赞 |
| 429 | 请求过于频繁 | 触发限流（Alpha 阶段暂不实现） |
| 503 | 服务不可用 | LLM 调用失败、外部服务异常 |

### 数据类型

- `id`: 整数（当前实现使用自增整数）
- `datetime`: ISO 8601 格式字符串（如 `2026-05-25T10:00:00Z`）
- 所有枚举字段均为字符串，大小写敏感

### 状态枚举

案例状态：`draft` | `pending_review` | `approved` | `rejected`

状态转换规则：
- `draft` → `pending_review`（作者提交）
- `pending_review` → `approved`（管理员通过）
- `pending_review` → `rejected`（管理员退回修改）
- `rejected` → `pending_review`（作者修改后重新提交）

**注意:** 状态名 `rejected` 的语义为"退回修改"（作者可重新提交），而非"彻底拒绝"。

---

## 认证 (Auth)

### POST /api/auth/login

**描述:** 用户登录，获取访问令牌

**认证:** 不需要

**Content-Type:** `application/x-www-form-urlencoded`

**请求参数:**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| username | string | 是 | 用户名 |
| password | string | 是 | 密码 |

**成功响应 (200):**
```json
{
  "success": true,
  "data": {
    "id": 1,
    "username": "string",
    "role": "normal | admin",
    "nickname": "string",
    "must_change_password": false,
    "status": "active",
    "token": "string"
  }
}
```

**错误响应:**
- 401: 用户名或密码错误
- 400: 缺少 username 或 password 字段

---

### POST /api/auth/change-password [已实现，与目标态有差异]

**描述:** 修改密码

**认证:** 不需要（通过 username + old_password 校验身份）

**Content-Type:** `application/x-www-form-urlencoded`

**请求参数:**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| username | string | 是 | 用户名 |
| old_password | string | 是 | 原密码 |
| new_password | string | 是 | 新密码（至少 8 位） |

**成功响应 (200):**

目标态：
```json
{
  "success": true
}
```

当前代码额外返回 `message` 字段。

**错误响应:**
- 400: 新密码长度少于 8 位
- 400: 用户名或原密码错误

---

## 案例 (Cases)

### POST /api/cases [已实现，与目标态有差异]

**描述:** 创建新案例

**认证:** 需要

**Content-Type:** `application/x-www-form-urlencoded`

**请求参数:**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| title | string | 否 | 案例标题，默认为空字符串 |
| content | string | 否 | 内容，默认为空字符串 |
| department | string | 否 | 所属单位，默认为空字符串 |
| type | string | 否 | 案例类型，当前代码默认 `TYPE_A`；目标态默认空字符串（用户后续选择） |
| theme | string | 否 | 主题，当前代码默认 `铸魂育人`；目标态默认空字符串（用户后续选择） |
| status | string | 否 | 初始状态，当前代码默认 `pending_review`；目标态默认 `draft` |

**成功响应 (200):**

当前代码返回：
```json
{
  "success": true,
  "case_id": 1
}
```

目标态（Phase 5）统一为：
```json
{
  "success": true,
  "id": 1
}
```

**错误响应:**
- 401: 未认证
- 400: status 不是 `draft` 或 `pending_review`（当前代码允许两者）

---

### GET /api/cases [已实现]

**描述:** 获取案例列表，支持筛选和分页

**认证:** 公开列表不需要；查看 draft/他人案例需要

**查询参数:**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| status | string | 否 | 状态筛选，默认 `approved` |
| offset | integer | 否 | 分页偏移，默认 0 |
| limit | integer | 否 | 每页数量，默认 50，最大 100 |
| author | string | 否 | 按作者筛选 |
| q | string | 否 | 全文搜索关键词 |
| type | string | 否 | 按类型筛选 |
| theme | string | 否 | 按主题筛选 |

**成功响应 (200):**
```json
{
  "success": true,
  "data": [
    {
      "id": 1,
      "title": "string",
      "content": "string",
      "author": "string",
      "department": "string",
      "type": "string",
      "theme": "string",
      "status": "draft | pending_review | approved | rejected",
      "created_at": "2026-05-25T10:00:00Z",
      "updated_at": "2026-05-25T10:00:00Z",
      "view_count": 0,
      "likes": 0,
      "is_hidden": false
    }
  ],
  "total": 100
}
```

**错误响应:**
- 401: 查看 `status=draft` 且无 author 参数时未登录
- 401: 按 author 筛选时未登录
- 403: 非管理员查看他人案例
- 403: 查看非自己的草稿

**特殊规则:**
- `status=draft` 且未指定 `author` 时，自动使用当前登录用户作为 author
- 管理员可查看所有案例（包括 hidden）
- 普通用户只能查看 `approved` 状态且未 hidden 的案例，或自己的案例

---

### GET /api/cases/:id [已实现]

**描述:** 获取单个案例详情

**认证:** 公开详情不需要；查看 draft 需要

**路径参数:**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| id | integer | 是 | 案例 ID |

**查询参数:**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| increment_view | boolean | 否 | 是否增加浏览量，默认 `true` |

**成功响应 (200):**
```json
{
  "success": true,
  "data": {
    "id": 1,
    "title": "string",
    "content": "string",
    "author": "string",
    "owner_username": "string",
    "department": "string",
    "type": "string",
    "theme": "string",
    "status": "string",
    "created_at": "2026-05-25T10:00:00Z",
    "updated_at": "2026-05-25T10:00:00Z",
    "view_count": 0,
    "likes": 0,
    "ai_reviews": [
      {
        "reviewed_at": "2026-05-25T10:00:00Z",
        "steps": [
          {
            "step": 1,
            "name": "完整性检查",
            "passed": true,
            "feedback": "string",
            "score": null,
            "dimensions": null
          },
          {
            "step": 2,
            "name": "分类检查",
            "passed": true,
            "feedback": "string",
            "score": null,
            "dimensions": null
          },
          {
            "step": 3,
            "name": "表达检查",
            "passed": true,
            "feedback": "string",
            "score": null,
            "dimensions": null
          },
          {
            "step": 4,
            "name": "评分",
            "passed": null,
            "feedback": "string",
            "score": 85,
            "dimensions": [
              {"name": "选题", "score": 90},
              {"name": "内容", "score": 85},
              {"name": "结构", "score": 80},
              {"name": "语言", "score": 85}
            ]
          }
        ],
        "overall_score": 82,
        "summary": "string"
      }
    ],
    "versions": null,
    "is_hidden": false
  }
}
```

**错误响应:**
- 404: 案例不存在
- 403: 无权查看该草稿（非草稿作者）
- 403: 案例已隐藏且非管理员/作者

**约束:**
- `ai_reviews` 最多保留 3 条（FIFO），按 `reviewed_at` 倒序
- `steps` 数量不固定，由 prompt 文件定义
- `dimensions` 为灵活数组，`name` 不限制（由具体 prompt 决定）
- `overall_score` 为独立评分，不直接等于某个 step 的 `score`

---

### PUT /api/cases/:id [已实现，与目标态有差异]

**描述:** 更新案例（用于自动保存和提交审核）

**认证:** 需要

**Content-Type:** `application/x-www-form-urlencoded`

**路径参数:**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| id | integer | 是 | 案例 ID |

**请求参数:**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| title | string | 否 | 标题 |
| content | string | 否 | 内容 |
| author | string | 否 | 作者 |
| department | string | 否 | 单位 |
| type | string | 否 | 类型 |
| theme | string | 否 | 主题 |
| status | string | 否 | 状态，允许 `draft` → `pending_review` |
| change_reason | string | 否 | 修改原因 |
| ai_reviews | array | 否 | AI 审核记录数组（见下方结构），最多 3 条 |

**注意:** 当前代码接收的是 `ai_review` 字符串字段，而非 `ai_reviews` 数组。

**ai_reviews 数组元素结构:**
```json
{
  "reviewed_at": "2026-05-25T10:00:00Z",
  "steps": [
    {
      "step": 1,
      "name": "完整性检查",
      "passed": true,
      "feedback": "string",
      "score": null,
      "dimensions": null
    }
  ],
  "overall_score": 85,
  "summary": "string"
}
```

**成功响应 (200):**
```json
{
  "success": true
}
```

**错误响应:**
- 401: 未认证
- 403: 无权修改该案例（非作者/非管理员）
- 403: 无权修改该草稿（非草稿作者）
- 404: 案例不存在
- 400: 案例没有实际变更
- 400: ai_reviews 条目超过 3 条

**核心流程:**
前端创建案例流程：`POST /api/cases`（创建 draft）→ 多次 `PUT /api/cases/:id`（自动保存）→ `PUT /api/cases/:id`（`status=pending_review`，提交）

---

### POST /api/cases/:id [已实现]

**描述:** 更新案例（POST 兼容版本，参数与 PUT 完全相同）

**认证:** 需要

**请求/响应:** 同 `PUT /api/cases/:id`

---

### DELETE /api/cases/:id [已实现，与目标态有差异]

**描述:** 删除案例

**认证:** 需要

**路径参数:**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| id | integer | 是 | 案例 ID |

**成功响应 (200):**

目标态：
```json
{
  "success": true
}
```

当前代码额外返回 `message` 和 `deleted_stats` 字段。

**错误响应:**
- 401: 未认证
- 403: 无权删除该案例
- 403: 无权删除该草稿（非草稿作者）
- 404: 案例不存在

---

### POST /api/cases/:id/like [已实现，WR-02 待修复]

**描述:** 点赞案例

**认证:** 当前代码未检查认证；目标态需要（WR-02）

**路径参数:**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| id | integer | 是 | 案例 ID |

**成功响应 (200):**

当前代码返回：
```json
{
  "success": true
}
```

目标态返回：
```json
{
  "success": true,
  "likes": 1
}
```

**错误响应:**
- 401: 未认证（WR-02 修复后）
- 404: 案例不存在

**约束:**
- 幂等操作：重复点赞不报错，点赞数不重复增加

---

### POST /api/cases/:id/unlike [已实现，WR-02 待修复]

**描述:** 取消点赞

**认证:** 当前代码未检查认证；目标态需要（WR-02）

**路径参数:**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| id | integer | 是 | 案例 ID |

**成功响应 (200):**

当前代码返回：
```json
{
  "success": true
}
```

目标态返回：
```json
{
  "success": true,
  "likes": 0
}
```

**错误响应:**
- 401: 未认证（WR-02 修复后）
- 400: 点赞数已经为 0
- 404: 案例不存在

**约束:**
- 幂等操作：重复取消点赞不报错

---

### POST /api/cases/:id/submit [已实现，与目标态有差异]

**描述:** 将草稿案例提交审核（状态变更为 `pending_review`）

**认证:** 需要

**路径参数:**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| id | integer | 是 | 案例 ID |

**成功响应 (200):**
```json
{
  "success": true
}
```

**错误响应:**
- 401: 未认证
- 403: 无权提交该案例（非作者/非管理员）
- 404: 案例不存在
- 400: 案例状态不允许提交审核（非 draft/rejected 状态）

**注意:** 提交审核也可以通过 `PUT /api/cases/:id` 传 `status=pending_review` 完成。`/submit` 为便捷端点，两者等价。

---

### POST /api/cases/:id/visibility [已实现]

**描述:** 隐藏或展示案例（仅管理员）

**认证:** 需要（管理员）

**路径参数:**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| id | integer | 是 | 案例 ID |

**请求参数:**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| hidden | boolean | 是 | `true` 隐藏，`false` 展示 |

**成功响应 (200):**
```json
{
  "success": true,
  "is_hidden": true
}
```

**错误响应:**
- 403: 仅管理员可以隐藏或展示案例
- 404: 案例不存在
- 400: 操作失败

---

## AI (AI Assistant)

> **注意:** 以下 AI 端点为 Phase 4 目标态。当前代码仍保留旧端点（`/review`、`/polish`、`/outline`、`/review-step`、`/assist`），Phase 4 完成后旧端点将返回 404。

### POST /api/ai/chat [Phase 4 目标态，当前未实现]

**描述:** 统一的 AI 交互端点（替代所有旧 AI 端点）

**认证:** 需要

**Content-Type:** `application/json`

**请求体:**
```json
{
  "prompt_id": "string (required)",
  "variables": {
    "key": "value"
  }
}
```

**成功响应 (200):**
```json
{
  "success": true,
  "answer": "raw LLM output",
  "parsed": {
    "pass": true,
    "detail": "..."
  },
  "parse_error": null
}
```

**`parsed` 字段规则:**
- 仅当 prompt 声明 `output_schema: json` 时返回 `parsed`（workflow prompt）
- 当 prompt 未声明 `output_schema` 时，`parsed` 为 `null`（skills prompt）
- `parse_error` 包含 JSON 提取或 schema 校验失败的错误详情
- 解析失败时 `parsed` 为 `null`，`parse_error` 为错误字符串

**错误响应:**
- 401: 未认证
- 404: Prompt 不存在
- 400: 缺少必填变量
- 503: LLM 调用失败

**内容长度限制:** 单个请求内容最大 100,000 字符

---

### GET /api/prompts [Phase 4 目标态，当前未实现]

**描述:** 获取 Prompt 元数据列表（不包含完整 prompt 内容）

**认证:** 需要

**查询参数:**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| category | string | 否 | 分类筛选：`workflow` 或 `skills` |

**成功响应 (200):**

`GET /api/prompts?category=workflow`:
```json
{
  "success": true,
  "data": [
    {
      "id": "workflow/completeness",
      "name": "完整性检查",
      "description": "检查案例是否包含关键板块",
      "category": "workflow",
      "variables": ["title", "content"],
      "output_schema": "json"
    }
  ]
}
```

`GET /api/prompts?category=skills`:
```json
{
  "success": true,
  "data": [
    {
      "id": "polish",
      "name": "文本润色",
      "description": "将文本润色为更专业的表达",
      "category": "skills",
      "variables": ["text", "tone"]
    }
  ]
}
```

**错误响应:**
- 401: 未认证

**注意:** 不传 category 参数时返回空数组 `[]`

**约束:**
- 接口永远**不返回** prompt 的完整 `content` 字段
- 未知 category 返回空数组 `[]` 或 400 错误
- category 不限制为 `workflow`/`skills`，支持任意已注册 category

---

## 旧 AI 端点（Phase 4 完成后返回 404）

以下端点在 Phase 4 中将被删除，客户端应迁移到 `POST /api/ai/chat`：

| 旧端点 | 旧参数 | 替代方式 |
|--------|--------|----------|
| `POST /api/ai/polish` | `content` | `POST /api/ai/chat` with `prompt_id: "polish"`, `variables: {text: content}` |
| `POST /api/ai/outline` | `topic` | `POST /api/ai/chat` with `prompt_id: "outline"`, `variables: {text: topic}` |
| `POST /api/ai/assist` | `question` | `POST /api/ai/chat` with `prompt_id: "assist"`, `variables: {text: question}` |
| `POST /api/ai/review` | `content` | `POST /api/ai/chat` with `prompt_id: "workflow/completeness"`, `variables: {title, content}` 等 |
| `POST /api/ai/review-step` | `content`, `step` | 见下方 step 映射表 |

**旧 `review-step` 的 `step` 参数映射到新 `prompt_id`:**

| 旧 step 值 | 新 prompt_id |
|-----------|-------------|
| `completeness` | `workflow/completeness` |
| `categorization` | `workflow/categorization` |
| `expression` | `workflow/expression` |
| `score` | `workflow/score` |

**prompt_id 命名规范:**
- Workflow prompts: `workflow/completeness`, `workflow/categorization`, `workflow/expression`, `workflow/score`
- Skills prompts: `polish`, `outline`, `check-integrity`, `assist`

**注意:** 当前代码中这些端点仍可访问。Phase 4 完成后将统一返回 404。

---

## 管理审核 (Admin Review)

### POST /api/reviews/:case_id [已实现]

**描述:** 管理员审核案例（通过/驳回/要求修改）

**认证:** 需要（管理员）

**Content-Type:** `application/x-www-form-urlencoded`

**路径参数:**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| case_id | integer | 是 | 案例 ID |

**请求参数:**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| comment | string | 是 | 审核意见 |
| status | string | 是 | 审核结果：`approved` / `rejected` |

**成功响应 (200):**
```json
{
  "success": true
}
```

**错误响应:**
- 403: 仅管理员可以审核案例
- 404: 案例不存在
- 400: 审核失败（状态不允许）

---

### GET /api/reviews/:case_id [已实现]

**描述:** 获取案例的审核历史

**认证:** 需要（案例作者或管理员可见）

**路径参数:**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| case_id | integer | 是 | 案例 ID |

**成功响应 (200):**
```json
{
  "success": true,
  "data": [
    {
      "reviewer": "admin",
      "comment": "审核意见",
      "status": "approved",
      "reviewed_at": "2026-05-25T10:00:00Z"
    }
  ]
}
```

**错误响应:**
- 404: 案例不存在
- 403: 无权查看该案例的历史记录

---

## 搜索 (Search)

### GET /api/search [已实现]

**描述:** 全文搜索案例

**认证:** 不需要

**查询参数:**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| q | string | 是 | 搜索关键词 |
| status | string | 否 | 状态筛选，默认 `approved` |

**成功响应 (200):**
```json
{
  "success": true,
  "data": [ ...cases... ],
  "query": "搜索关键词"
}
```

---

### GET /api/search/advanced [已实现]

**描述:** 高级筛选搜索

**认证:** 不需要

**查询参数:**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| type | string | 否 | 按类型筛选 |
| theme | string | 否 | 按主题筛选 |
| status | string | 否 | 状态筛选，默认 `approved` |
| keyword | string | 否 | 关键词 |
| limit | integer | 否 | 数量限制，默认 50 |

**成功响应 (200):**
```json
{
  "success": true,
  "data": [ ...cases... ]
}
```

---

## 推荐与趋势

### GET /api/recommendations/:case_id [已实现]

**描述:** 获取相关推荐案例

**认证:** 不需要

**路径参数:**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| case_id | integer | 是 | 案例 ID |

**查询参数:**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| limit | integer | 否 | 数量限制，默认 5 |

**成功响应 (200):**
```json
{
  "success": true,
  "data": [ ...cases... ]
}
```

---

### GET /api/trending [已实现]

**描述:** 获取热门案例

**认证:** 不需要

**查询参数:**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| limit | integer | 否 | 数量限制，默认 10 |

**成功响应 (200):**
```json
{
  "success": true,
  "data": [ ...cases... ]
}
```

---

### GET /api/latest [已实现]

**描述:** 获取最新案例

**认证:** 不需要

**查询参数:**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| limit | integer | 否 | 数量限制，默认 10 |

**成功响应 (200):**
```json
{
  "success": true,
  "data": [ ...cases... ]
}
```

---

## 版本历史

### GET /api/versions/:case_id [已实现]

**描述:** 获取案例的版本历史

**认证:** 需要（案例作者或管理员可见）

**路径参数:**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| case_id | integer | 是 | 案例 ID |

**成功响应 (200):**
```json
{
  "success": true,
  "data": [ ...version records... ]
}
```

**错误响应:**
- 404: 案例不存在
- 403: 无权查看该案例的历史记录

---

## 统计与常量

### GET /api/statistics [已实现]

**描述:** 获取平台统计数据

**认证:** 不需要

**成功响应 (200):**
```json
{
  "success": true,
  "data": {
    "total_cases": 100,
    "approved_cases": 80,
    "pending_cases": 15,
    "total_views": 5000,
    "total_likes": 300
  }
}
```

---

### GET /api/constants [已实现]

**描述:** 获取系统常量（案例类型、主题、状态等）

**认证:** 不需要

**成功响应 (200):**
```json
{
  "success": true,
  "data": {
    "case_types": {
      "TYPE_A": "思政课教学案例",
      "TYPE_B": "课程思政共享资源案例",
      "TYPE_C": "实践育人案例"
    },
    "themes": ["强国建设", "实践育人", "数字赋能", "铸魂育人"],
    "statuses": {
      "draft": "草稿",
      "pending_review": "待审核",
      "approved": "已通过",
      "rejected": "退回修改"
    }
  }
}
```

---

## 约束条件汇总

1. **认证:** 逐端点认证要求见"全局约定 > 认证"表格
2. **Token 格式:** HMAC-SHA256 签名（非 JWT），有效期 7 天
3. **ID 类型:** 整数（当前实现使用自增整数）
4. **状态枚举:** `draft` | `pending_review` | `approved` | `rejected`（语义为"退回修改"）
5. **ai_reviews 上限:** 每个 case 最多保留 3 条（FIFO）
6. **parsed 字段:** 只有 workflow prompt 返回 `parsed`，skills 不返回
7. **错误格式统一:** `{ "success": false, "detail": "错误信息" }`
8. **内容长度限制:** AI 请求内容最大 100,000 字符
9. **Prompt 内容保护:** `GET /api/prompts` 永远不返回 prompt 的完整 `content`
10. **点赞幂等:** 重复 like/unlike 不报错、不重复计数

---

## 前端核心流程

### 案例创建完整流程

```
1. POST /api/cases (status: "draft")
   → 获取 id

2. [自动保存] PUT /api/cases/:id
   → 保存 title, content, author, department, type, theme
   → 每次字段变更后 2s 防抖发送

3. [AI 审核] POST /api/ai/chat
   → Step 1: prompt_id="workflow/completeness", variables={title, content}
   → Step 2: prompt_id="workflow/categorization", variables={title, content, type, theme}
   → Step 3: prompt_id="workflow/expression", variables={content}
   → Step 4: prompt_id="workflow/score", variables={title, content}
   → 每个步骤读取 response.parsed
   → 收集所有步骤结果到 ai_reviews 数组

4. [提交审核] PUT /api/cases/:id
   → status: "pending_review"
   → ai_reviews: [完整审核记录]
```

### AI 浮窗技能加载流程

```
1. GET /api/prompts?category=skills
   → 获取 [{id, name, description, variables}]

2. 用户选择技能 → 填充输入框（不自动发送）

3. POST /api/ai/chat {prompt_id, variables}
   → 显示 answer（纯文本）
```

---

*文档版本: v1.1-alpha*
*最后更新: 2026-05-25*
