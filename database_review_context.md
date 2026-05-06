# 数据库与接口上下文梳理

> 用途：为后续对当前项目数据库接口进行对抗性安全审查（adversarial review）提供事实性上下文。
> 范围：仅基于本仓库当前代码事实，不涉及修改建议落地，仅做观察。
> 备注：根目录 `CLAUDE.md` 中描述的“SQLite + `cases.db`”已经过时——`backend/database.py` 实际已经迁移到 MongoDB。`CLAUDE.md` 中的 `/api/auth/register`、`/api/cases/{id}/mark-in-library`、`/api/cases/batch-mark-in-library`、`/api/sync/sql` 等接口在 `backend/main.py` 中**不存在**。本文档以代码事实为准。

---

## 1. 数据库技术栈

- **数据库类型**：MongoDB（实际生产）。`data/cases.db` 是历史 SQLite 文件，仅由 `backend/migrate_sqlite_to_mongo.py` 一次性迁移读取，运行期不再使用。
- **访问库**：`pymongo`（`MongoClient`、`ReturnDocument`、`ASCENDING/DESCENDING/TEXT`、`DuplicateKeyError`），密码哈希用 `bcrypt`，`bson.ObjectId` 用于序列化。
- **连接入口文件**：`backend/database.py`
  - `get_mongo_client()`（第 45–49 行）持有进程级单例 `MongoClient`。
  - `get_db_connection()` / `get_db()`（第 52–58 行）返回 MongoDB 数据库对象。
- **配置 / 环境变量**（在 `backend/database.py` 第 18–26 行通过 `dotenv.load_dotenv()` 装载）：
  - `MONGODB_URI`（默认 `mongodb://localhost:27017`）
  - `MONGODB_DB_NAME`（默认 `case_library`）
  - `MONGODB_TIMEOUT_MS`（默认 `5000`）
  - `SQLITE_DB_PATH`（默认 `<repo>/data/cases.db`，仅用于迁移脚本）
  - 仓库中未提供 `.env` 模板文件，需进一步确认。
- **初始化 / 索引 / 默认数据**：
  - `init_db()`（`backend/database.py` 第 284–322 行）：`ping` MongoDB、建索引、`sync_all_counters()`、`backfill_owner_username()`。`init_db()` 在 `backend/main.py` 第 78 行模块加载时被无条件调用。
  - `init_users.py`：当 users 集合为空时插入 3 个默认账号。
  - `demo.py`：当 cases 集合为空时插入 3 条 demo 案例并直接置为 `approved`。
  - `migrate_sqlite_to_mongo.py`：从 SQLite 一次性迁移到 MongoDB（不破坏已有数据）。
  - `migrate_timestamps.py`、`smoke_test_mongo.py`、`test_submit_flow.py`：维护 / 测试脚本。

---

## 2. 数据模型 / 集合梳理

代码中实际涉及的集合：`users`、`cases`、`reviews`、`versions`、`deployments`、`counters`。
所有以下字段类型均**根据代码推断**（MongoDB 是 schemaless，没有显式 schema 声明）。

### 2.1 `users`
位置：`backend/database.py` `create_user`（第 336–362 行）、`init_db`（第 296–298 行）。

| 字段 | 推断类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `_id` | ObjectId | 自动 | – | Mongo 内置 |
| `id` | int | 是 | `next_sequence("users")` 自增 | **唯一索引** |
| `username` | string | 是 | – | **唯一索引**；登录主键 |
| `password` | string (bcrypt hash) | 是 | – | **敏感字段**；`hash_password` 写入 |
| `role` | string enum | 否 | `"normal"` | 取值：`normal` / `admin`；遗留 `"user"` 在读时被 `_normalize_user_role` 归一为 `normal` |
| `nickname` | string | 否 | `""` | 案例 author 字段会展示 nickname |
| `must_change_password` | bool | 否 | `True` | 强制改密标记 |
| `status` | string enum | 否 | `"active"` | 取值：`active` / `no_active`；`no_active` 不能登录 |
| `created_at` | string `YYYY-MM-DD HH:MM:SS`（北京时） | 是 | `_now()` | 字符串日期，非 BSON Date |
| `updated_at` | string | 是 | `_now()` | 同上 |

索引：
- `id` unique
- `username` unique
- `(role, status)` 复合索引

### 2.2 `cases`
位置：`backend/database.py` `create_case`（第 479–519 行）、`update_case`（第 635–694 行）。

| 字段 | 推断类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `_id` | ObjectId | 自动 | – | – |
| `id` | int | 是 | `next_sequence("cases")` 自增 | **唯一索引**；对外主键 |
| `title` | string | 否 | `""` | 文本索引 |
| `type` | string enum | 否 | `""` | 取值常量见 `/api/constants`：`TYPE_A` / `TYPE_B` / `TYPE_C`（`create_case` 默认 `""`，但路由处默认 `TYPE_A`） |
| `theme` | string | 否 | `""` | 路由处默认 `"铸魂育人"` |
| `content` | string | 否 | `""` | 全文 |
| `status` | string enum | 是 | `"draft"` | 合法值：`draft`、`pending_review`、`approved`、`needs_revision`（`CASE_STATUSES`，第 28–33 行）。代码中还出现 `"deleted"` 软删除值，但**未列入 `CASE_STATUSES`**；`delete_case` 实际是硬删除，因此 `deleted` 是历史/防御性写法 |
| `author` | string | 否 | `""` | 显示用，可能存 nickname 或 username（历史数据混杂） |
| `owner_username` | string | 否 | `""` | 真实归属用户名；权限判断核心字段；`backfill_owner_username` 用于修复历史数据 |
| `department` | string | 否 | `""` | – |
| `keywords` | List[string] | 否 | `[]` | `_normalize_keywords` 兼容 JSON 字符串 |
| `created_at` | string | 是 | `_now()` | 字符串日期 |
| `updated_at` | string | 是 | `_now()` | – |
| `submitted_at` | string | 否 | – | `submit_for_review` 时写入 |
| `is_approved` | bool | 否 | `False` | `review_case` 写入 |
| `is_in_library` | bool | 否 | `False` | `review_case` 写入 |
| `is_hidden` | bool | 否 | `False` | 仅管理员可切换 |
| `view_count` | int | 否 | `0` | `$inc` |
| `like_count` | int | 否 | `0` | `$inc` |
| `deployed_at` | string | 否 | – | `create_case` 可选透传，**当前无任何接口写它**（`deployments` 集合也没有写入路径） |
| `deployed_by` | string | 否 | – | 同上 |

索引：
- `id` unique
- `(status, created_at desc)`
- `(author, status, created_at desc)`
- `(owner_username, status, created_at desc)`
- `(type, theme)`
- `cases_text_idx`：`title` + `content` + `keywords` 的 TEXT 索引（`default_language="none"`），但搜索代码 `search_cases` / `filter_cases` 实际使用 `$regex`，**没有真正使用 TEXT 索引**——需要进一步确认是否冗余。

### 2.3 `reviews`
位置：`submit_for_review`（第 726–749 行）、`review_case`（第 752–793 行）。

| 字段 | 推断类型 | 必填 | 说明 |
|---|---|---|---|
| `_id` | ObjectId | 自动 | – |
| `id` | int | 是 | 自增 |
| `case_id` | int | 是 | 关联 `cases.id` |
| `reviewer` | string | 是 | 写入时直接来自接口 `Form` 字段，**未做归一/校验**（详见第 7 节） |
| `comment` | string | 是 | 同上，无长度/内容校验 |
| `status` | string enum | 是 | 经 `_normalize_review_status` 归一为 `approved` / `rejected` / `pending` |
| `review_at` | string | 是 | `_now()` |

索引：`id` unique、`(case_id, review_at desc)`。

### 2.4 `versions`
位置：`create_case`、`update_case`（仅在 `VERSIONED_FIELDS` 中字段变化时写入）。

| 字段 | 推断类型 | 说明 |
|---|---|---|
| `_id` | ObjectId | – |
| `id` | int | 自增 |
| `case_id` | int | 关联 `cases.id` |
| `version_number` | int | 单 case 自增 1 |
| `content` | string | 当前版本内容快照 |
| `changed_by` | string | 来自 `update_case` 的 `updated_by` 参数；接口允许前端通过 `Form` 直接传入 |
| `change_reason` | string | 同上 |
| `created_at` | string | – |

索引：`id` unique、`(case_id, version_number desc)`。

### 2.5 `deployments`
仅在 `init_db` 创建索引、`delete_case` 中删除。
**当前代码中没有任何写入路径** —— 是为后续/迁移留的占位集合。需要进一步确认是否还有计划。

| 字段（推断） | 来源 |
|---|---|
| `id` int | 索引声明 |
| `case_id` int | 索引声明 |
| `deployed_at` | 索引声明 |

索引：`id` unique、`(case_id, deployed_at desc)`。

### 2.6 `counters`
位置：`sync_counter`、`next_sequence`（第 234–272 行）。
- `_id`：集合名（`users` / `cases` / `reviews` / `versions` / `deployments`）
- `seq`：当前最大整数 id

---

## 3. 数据库访问层梳理

直接访问数据库的文件：
- `backend/database.py`（绝大部分访问集中于此）
- `backend/case_processor.py`（仅通过 `database.py` 提供的函数；其本身不直接访问 mongo）
- `backend/search_engine.py`（同上，纯包装）
- `backend/init_users.py`、`backend/demo.py`、`backend/account_admin.py`、`backend/migrate_sqlite_to_mongo.py`、`backend/migrate_timestamps.py`、`backend/smoke_test_mongo.py`、`backend/test_submit_flow.py`（一次性脚本）

下表只列出 `database.py` 中作为接口层调用入口的函数（运行期热路径）：

| 函数 | 文件 | 读/写 | 集合 | 关键查询条件 / 写入字段 | 事务 | 异常处理 | 是否能直接吞 req.body |
|---|---|---|---|---|---|---|---|
| `get_user_by_username` | database.py | 读 | users | `{username}` | – | – | – |
| `create_user` | database.py | 写 | users + counters | 写整条用户记录；`DuplicateKeyError` → `ValueError` | 否 | 是（DuplicateKeyError）| 否（参数受控） |
| `authenticate_user` | database.py | 读 | users | `{username}`，校验 `status==active` 与 bcrypt | – | – | – |
| `set_user_password` / `change_user_password` | database.py | 写 | users | 改 `password`、`must_change_password`、`updated_at` | 否 | – | – |
| `update_user_fields` | database.py | 写 | users | 仅 `role` / `nickname` / `status` 经枚举校验 | 否 | – | 否（白名单） |
| `rename_user` / `delete_user` / `clear_users` | database.py | 写 | users / counters | 整条改名 / 删除 / 清空 | 否 | DuplicateKeyError 等 | 否 |
| `list_users` / `get_users_count` | database.py | 读 | users | – | – | – | – |
| `create_case` | database.py | 写 | cases + versions + counters | 调用方传入字典；写入字段为白名单（见第 2.2 节）；同步写入 version 1 | 否（**两次独立 insert，可能不一致**） | – | **半是**：上层路由不会原样转发整个 body；但 `case_processor.process_new_case` / `enhance_case` 由代码组装 |
| `get_case` / `get_all_cases` / `count_cases` | database.py | 读 | cases | `_case_list_filter` 处理 author/status/include_hidden | – | – | – |
| `update_case` | database.py | 写 | cases + versions | **白名单**字段：`title/type/theme/content/author/department/status/is_approved/is_in_library/keywords`；如果 VERSIONED 字段变化则插 versions；调用方可以通过传入 `is_approved` / `is_in_library` 直接改库标志（见第 7 节） | 否 | `_validate_case_status` | 部分受白名单约束，但接口层 `_update_existing_case_impl` 没传这些标志 |
| `delete_case` | database.py | 写 | cases + reviews + versions + deployments | 物理删除；同时清理三类附属集合 | 否（多次独立 delete_many） | – | 否 |
| `submit_for_review` | database.py | 写 | cases + reviews | 仅在 `status ∈ {draft, needs_revision}` 时改为 `pending_review`；插一条 reviewer="system" 的 review | 否 | – | 否 |
| `review_case` | database.py | 写 | cases + reviews | 把 cases 状态改为 approved/needs_revision/pending_review，并写 review；`reviewer` / `comment` 从外部传入 | 否 | `_normalize_review_status` | **是**：接口直接拿 Form 写入 |
| `set_case_hidden` | database.py | 写 | cases | `is_hidden` | 否 | – | 否 |
| `increment_view_count` / `increment_like_count` / `decrement_like_count` | database.py | 写 | cases | `$inc` view_count / like_count；decrement 有兜底 | 否 | – | – |
| `search_cases` / `filter_cases` | database.py | 读 | cases | `$regex` 拼装；`re.escape` 已转义；强制 `is_hidden!=true` | – | – | – |
| `get_recommendation_candidates` / `get_trending_cases` / `get_latest_cases` | database.py | 读 | cases | 仅 `approved` + 非隐藏 | – | – | – |
| `get_case_versions` / `get_reviews` | database.py | 读 | versions / reviews | 按 case_id | – | – | – |
| `get_statistics` | database.py | 读（aggregate） | cases | only `status==approved` | – | – | – |
| `backfill_owner_username` | database.py | 写 | users（读） + cases（写） | 仅在 owner_username 缺失时回填 | 否 | – | 否 |
| `next_sequence` / `sync_counter` | database.py | 写 | counters | `find_one_and_update($inc seq, upsert)` + `$max` | 否（FindAndModify 原子） | RuntimeError | – |

**总体观察**：
- 所有写操作都是单文档原子，但跨集合的复合写（create_case 同时写 cases + versions、submit_for_review 同时写 cases + reviews、delete_case 同时清理 4 个集合）**没有事务**——MongoDB 单机部署默认也不支持事务，需要进一步确认部署形态（standalone vs replica set）。
- 字符串日期 `_now()` 写入会触发任意时区误差，但 `serialize_doc` 在读时再统一格式化。日期不是 BSON Date，**无法用 Mongo 比较运算符按时间区间查询**——业务侧暂未做时间区间查询，但需提示。
- `create_user` 的 `DuplicateKeyError` 转 `ValueError` 后由 FastAPI 全局 handler 转 400，OK；其它 `DuplicateKeyError`、`ServerSelectionTimeoutError` 没有明确捕获。

---

## 4. 后端接口与数据库读写关系

下表覆盖 `backend/main.py` 中所有路由（前端静态文件挂载除外）。**“风险备注”仅做事实观察**。

| 方法 | 路径 | 文件 | 数据库操作 | 登录要求 | 权限要求 | 风险备注 |
|---|---|---|---|---|---|---|
| POST | `/api/auth/login` | main.py:87 | 读 users（`authenticate_user`） | 否 | – | 自制 token=`username_timestamp`，**无签名/过期校验**（见第 5 节） |
| POST | `/api/auth/change-password` | main.py:108 | 写 users（`change_user_password`） | 否（用旧密码兑现） | – | username 来自 Form，没有限制只能改自己；但需要旧密码，相对受控 |
| GET | `/api/cases` | main.py:121 | 读 cases | 视情况 | 普通用户只能查自己的 author/draft；admin 能查任何作者 | 当 `status=draft` 但未传 `author`，会取当前用户名；逻辑较复杂 |
| GET | `/api/cases/{id}` | main.py:157 | 读 cases + 写 cases (`view_count`) | 否（公开案例） | 草稿仅 owner；hidden 仅 admin/owner | `increment_view`默认 True，匿名访问也会自增 view_count，**未做防刷**；`view_count` 失败返回 404 |
| POST | `/api/cases` | main.py:181 | 写 cases + versions（`create_case`），或 `process_new_case` | 否（除非 status=draft） | 任意已登录用户都能创建 | **未登录用户也能创建非草稿案例**；author/department/type/theme 全是 Form，可任意填；`auto_process=true` 走 `case_processor.process_new_case`，强制状态 `pending_review` |
| PUT | `/api/cases/{id}` | main.py:272 | 读 cases + 写 cases + 可能写 versions | 是 | 仅 owner 或 admin | `updated_by` / `change_reason` 由 Form 直接接收，写入 versions，可被前端伪造 |
| POST | `/api/cases/{id}` | main.py:292 | 同上 | 是 | 同上 | PUT 的兼容别名 |
| DELETE | `/api/cases/{id}` | main.py:312 | 写 cases / reviews / versions / deployments（物理删除） | 是 | 仅 owner 或 admin | 物理删除而非软删除；级联 4 个集合无事务 |
| POST | `/api/cases/{id}/submit` | main.py:344 | 写 cases + reviews | 是 | 仅 owner 或 admin | 取 `include_deleted=True` 查 case，但 `submit_for_review` 内部要求状态为 draft/needs_revision，OK |
| POST | `/api/cases/{id}/like` | main.py:363 | 写 cases (`like_count++`) | 否 | – | **无身份校验、无限刷**；可重复点赞 |
| POST | `/api/cases/{id}/unlike` | main.py:370 | 写 cases (`like_count--`) | 否 | – | 同上；有 `>0` 兜底防负 |
| GET | `/api/search` | main.py:379 | 读 cases | 否 | – | 强制 `is_hidden!=true`；`re.escape` 已转义 |
| GET | `/api/search/advanced` | main.py:384 | 读 cases | 否 | – | 同上；`limit` 来自 query，默认 50，无上限 |
| GET | `/api/recommendations/{id}` | main.py:404 | 读 cases | 否 | – | 仅 approved 范围 |
| GET | `/api/trending` | main.py:409 | 读 cases | 否 | – | – |
| GET | `/api/latest` | main.py:414 | 读 cases | 否 | – | – |
| POST | `/api/cases/{id}/visibility` | main.py:419 | 写 cases (`is_hidden`) | 是 | **仅 admin** | 严格检查 |
| POST | `/api/reviews/{id}` | main.py:442 | 写 cases + reviews | 是 | **仅 admin** | `reviewer` / `comment` 从 Form 来，**`reviewer` 可能与当前登录管理员不同名**（前端可填别人的名字进 reviews 表） |
| GET | `/api/reviews/{id}` | main.py:458 | 读 reviews | 否 | – | **公开** —— 任何人都能看任意案例的全部审核记录与 reviewer 名字 |
| GET | `/api/versions/{id}` | main.py:463 | 读 versions | 否 | – | **公开** —— 即使是草稿/被驳回案例的历史版本内容也可被未登录用户读取，需要进一步确认是否预期 |
| GET | `/api/statistics` | main.py:468 | 读 cases (aggregate) | 否 | – | 仅汇总 approved |
| GET | `/api/constants` | main.py:473 | – | 否 | – | 无 DB |
| GET | `/` 与 `GET /{path:path}` | main.py:497, 502 | – | 否 | – | 静态文件 catch-all |

**`CLAUDE.md` 中提到、但代码里没有的接口**（已核实 grep 不命中）：
- `POST /api/auth/register`
- `POST /api/cases/{id}/mark-in-library`
- `POST /api/cases/batch-mark-in-library`
- `GET /api/sync/sql`

如果对抗审查需要覆盖这些接口，需要先确认它们是否被外部依赖、是否计划新增。

---

## 5. 认证与权限逻辑

### 5.1 登录与会话
- 登录入口：`POST /api/auth/login`（`backend/main.py:87`）→ `authenticate_user`（`backend/database.py:386`）。
  - 校验：用户存在 + `status=='active'` + bcrypt `verify_password`。
- Token 生成：`backend/main.py:93`
  ```python
  token = f"{user['username']}_{int(time.time())}"
  ```
  - **未签名、未加密、无过期、无服务器侧存储**——token 只是“用户名 + 时间戳”的拼接。
- Token 校验：`get_current_user(headers)`（`backend/main.py:57–71`）
  ```python
  token = auth_header.replace("Bearer ", "")
  username = token.split("_")[0]
  user = get_user_by_username(username)
  ```
  - **没有任何签名验证**：客户端只要发送 `Authorization: Bearer <任意已知用户名>_<任意数字>` 即被认证为该用户。
  - 唯一兜底：`status != "active"` 的用户被拒。但这不能阻止伪造任何 active 用户（包括 admin）。
  - 这是当前代码最大的一处认证缺陷，**强烈建议作为对抗审查头号议题**。

### 5.2 权限模型
- 用户角色字段：`users.role ∈ {"normal", "admin"}`（遗留 `"user"` 在读取时归一化为 `"normal"`）。
- 用户状态：`users.status ∈ {"active", "no_active"}`，`no_active` 不能登录、token 也不识别。
- 没有 FastAPI 依赖项（`Depends`）层面的权限中间件 —— 每个需要权限的路由都在函数体内显式重复以下模式：
  ```python
  current_user = get_current_user(dict(request.headers))
  if not current_user: raise 401
  if current_user.get("role") != "admin" and current_user.get("username") != owner_username: raise 403
  ```
  集中位置：
  - `list_cases`（main.py:129–142）
  - `get_case_detail`（main.py:163–173）
  - `_update_existing_case_impl`（main.py:239–249）
  - `delete_case_endpoint`（main.py:314–325）
  - `submit_case_for_review`（main.py:346–356）
  - `toggle_case_visibility`（main.py:425–427，仅 admin）
  - `review_case_endpoint`（main.py:450–452，仅 admin）

### 5.3 接口里直接信任前端字段的情况
- `POST /api/cases`：`author`、`department`、`type`、`theme`、`status` 都来自 Form，未与登录用户绑定校验；`owner_username` 由后端按当前 user 设置，是良好的（main.py:194–202）。
- `POST /api/cases/{id}` / `PUT /api/cases/{id}`：`updated_by` / `change_reason` 由 Form 直接进入 versions 表，前端可任意伪造。
- `POST /api/reviews/{id}`：`reviewer` 由 Form 直接传，并不强制等于 `current_user.username`，**管理员可冒名审核**。
- `POST /api/auth/change-password`：`username` 来自 Form 而不是 token；理论上需要旧密码兑现，可控；但仍允许“用合法旧密码改任意用户密码”，这等同于自助改密+无 Cookie 绑定，实际不构成越权（旧密码是凭据），但与 token 体系断开是一处不优雅。
- `POST /api/cases/{id}/like`、`/unlike`：完全无身份。

---

## 6. 关键业务数据流

### 6.1 用户创建 / 登录 / 改密
- **创建**：仅通过 CLI `backend/account_admin.py` 或 `backend/init_users.py`（默认账号）。**没有公开注册接口**。`role` / `status` / `must_change_password` 全部由 CLI 决定。
- **登录**：`/api/auth/login` → `authenticate_user` 读 `users`；返回伪造易破的 token（见 5.1）。
- **改密**：`/api/auth/change-password` → `change_user_password` 写 `users.password / must_change_password / updated_at`；要求旧密码。
- **后台改密 / 重置 / 改角色 / 改状态**：仅 `account_admin.py` CLI（`set_user_password`、`update_user_fields`、`rename_user`、`delete_user`、`clear_users`）。前端无入口。

### 6.2 案例创建
1. 入口：`POST /api/cases`。
2. 当前登录用户写 `owner_username`（main.py:194–200）；若未登录但 status≠draft，仍允许创建 —— `owner_username` 为空字符串。
3. `create_case`（database.py:479）：写 `cases` 一条 + `versions` 一条 v1 快照，`counters` 自增。

### 6.3 案例修改
1. 入口：`PUT /api/cases/{id}` 或 `POST /api/cases/{id}`。
2. 必登录；权限：admin 或 `current_user.username == owner_username`（**注意**：判断的是 `get_case_owner_username(case)` = `case.owner_username or case.author`，所以历史数据中 owner_username 为空、author 为 nickname/username 时，校验会回退到 author 比较；这是 5.2 中权限检查的隐含弱点之一）。
3. `update_case`：白名单字段；只在 `VERSIONED_FIELDS` 改变时多写一条 versions。`updated_by` / `change_reason` 来自 Form。

### 6.4 案例查询
- 列表：`GET /api/cases`，普通用户能且只能查自己；admin 任意。匿名只能看默认 `status="approved"` 的公开列表。
- 详情：`GET /api/cases/{id}`，匿名可看 approved；草稿仅 owner；隐藏仅 admin/owner。
- 公开搜索 / 推荐 / 热门 / 最新 / 统计：完全匿名；强制 `status==approved` 且 `is_hidden!=true`。

### 6.5 案例删除
- `DELETE /api/cases/{id}`：必登录；admin 或 owner；**物理删除** cases，并清理 reviews / versions / deployments（无事务）。
- 草稿删除规则：`current_user.username != owner_username` 时禁止——admin 也会被这条挡掉？看代码 main.py:322–325，`if status==draft and not owner` 拒绝；admin 此时 `current_user.username != owner_username`，会被禁止删除别人草稿——这是预期还是 bug，需要进一步确认。

### 6.6 审核 / 状态变更
- 提交：`POST /api/cases/{id}/submit`：必登录；admin 或 owner；`submit_for_review` 把 cases.status 由 draft/needs_revision → pending_review，并写一条 reviewer="system" 的 review。
- 审核：`POST /api/reviews/{id}`：必登录且必 admin；`review_case` 把 cases.status 改为 approved 或 needs_revision（视 `_normalize_review_status`），同时设置 `is_approved` / `is_in_library`。`comment` / `reviewer` 直进数据库。
- 隐藏 / 展示：`POST /api/cases/{id}/visibility`：必 admin；只动 `is_hidden`。

### 6.7 文件上传
- 后端在启动时 `os.makedirs(UPLOAD_DIR)` 创建 `data/uploads/` 目录，但 **`backend/main.py` 没有任何上传/下载路由**。
- 也没有数据库字段记录附件路径（cases 没有 attachments 字段）。
- 需要进一步确认：是否有计划但尚未实现，还是已经废弃。

### 6.8 管理员相关
- 仅 admin：`/api/cases/{id}/visibility`、`/api/reviews/{id}`、跨用户访问 `/api/cases?author=...`。
- admin 没有“封禁用户”、“调整角色”等接口；管理用户必须用 CLI。

---

## 7. 当前代码中已经发现的明显风险点（事实观察）

> 仅限事实观察，未尝试编造或主观放大。

1. **token 完全可伪造**（main.py:57–71）：任何人都可以用 `Authorization: Bearer admin_1` 之类的字符串冒充任意 active 用户（包括 admin），**对抗审查必须最先关注**。
2. **`POST /api/cases/{id}/like` / `/unlike` 无身份**（main.py:363, 370）：可被脚本无限刷点赞。
3. **`POST /api/cases` 不强制登录**（main.py:181）：当 `status != "draft"` 时，允许匿名直接创建非草稿案例（虽然走 `pending_review`，但 author/department 完全可控，会污染待审队列）。
4. **`POST /api/reviews/{id}` 信任 Form `reviewer`**（main.py:442–453）：管理员可以以任意名字落审核记录，导致问责困难。
5. **`PUT/POST /api/cases/{id}` 信任 Form `updated_by` / `change_reason`**（main.py:272–309）：直接进 versions 表，前端可任意伪造修订人。
6. **`GET /api/reviews/{id}` 与 `GET /api/versions/{id}` 完全公开**（main.py:458, 463）：未登录用户即可读取任意案例（包括草稿）的版本历史和审核意见。
7. **`GET /api/cases/{id}` 默认 increment_view，未做防刷**（main.py:175）：匿名也能刷高 view_count；同时 view 失败返回 404，可被用作存在性探测。
8. **`/api/cases/{id}` 详情查询若 `is_hidden=true` 且非 admin/owner，返回 404**（main.py:172）：信息泄露较小，但与 `increment_view_count` 的检查顺序导致：先因 hidden 而 404 → 不会自增；OK。但若改为 admin 隐藏的案例，view_count 仍可被 admin 自己访问时计数，需要进一步确认是否预期。
9. **物理删除案例无事务**（database.py:710–714）：删除 cases 后才删除 reviews/versions/deployments，若中途异常会留孤儿数据；同样适用 `create_case`（先 cases 再 versions）。需要进一步确认 MongoDB 部署是否 replica set（standalone 不支持事务）。
10. **`update_case` 白名单包含 `is_approved` / `is_in_library` / `status`**（database.py:644–654）：路由层（`_update_existing_case_impl` main.py:251–263）只把 `title/content/author/department/type/theme/status` 透传，**没有 is_approved/is_in_library**，因此目前安全。但函数本身允许传入这些字段，未来如果有任何调用方直接转发 body，会绕过审核流程。
11. **`update_case` 允许任意已登录 owner 修改 `status`**（main.py:282 → database.py:644 列表中包含 `status`）：owner 可把案例从 `pending_review` 改回 `draft` 或直接改成 `approved`！下游 `_validate_case_status` 只检查枚举值合法，**不检查状态机迁移**。这是越权风险点，需要进一步确认是否预期。
12. **`delete_case` 物理删除**：与上面的 `is_in_library` 标记化设计相矛盾——已部署案例若被 owner 删除，无回收站。owner 可删除已通过审核的案例。
13. **`POST /api/cases` 中 owner_username 绑定不够严**：未登录时 `owner_username=""`，案例完全无主，后续没有人能再修改/删除（除 admin），且 `_case_list_filter` 在 author 模式下匹配不到，会变成“悬浮数据”。
14. **bcrypt rounds 使用默认值**：`bcrypt.gensalt()` 默认 12 轮，OK；但密码最小长度仅在 `change_password` 路由层校验（≥8），CLI 创建时没强制（会留低强度密码）。
15. **CORS 全开**：`allow_origins=["*"]` + `allow_credentials=True`（main.py:43–49）。在浏览器规范下 `*` 与 credentials 不能共存，浏览器会拒绝；但仍是一处坏味道，且对非浏览器客户端等同于无 origin 限制。
16. **没有登录次数 / 速率限制**：`/api/auth/login` 可被暴力破解；`/api/cases/{id}/like` 可被刷。
17. **唯一约束覆盖不全**：`reviews`、`versions`、`deployments` 没有任何唯一约束保护“同一 case 同一 version_number”等业务唯一性；`update_case` 中通过查询最大 version_number + 1，**并发情况下可能产生重复 version_number**（无原子保障）。需要进一步确认是否预期。
18. **`view_count` / `like_count` 用 `$inc` 是原子的**，但 `decrement_like_count` 的兜底路径在并发下仍可能走 `correction` 分支，存在轻微脏数据风险，但已尽力。
19. **`search_cases` / `filter_cases` 已 `re.escape`**：基本无 ReDoS / 注入；但 `limit` / `offset` 来自 query 且无上限，可能触发大查询/大返回。
20. **日期为字符串**：所有 `*_at` 字段是 `YYYY-MM-DD HH:MM:SS` 字符串而非 BSON Date。索引可工作（字典序与时间序一致），但任何带时区/夏令时/异常值的输入都可能破坏排序；当前代码只会自己写入 `_now()`，外部输入无法直接污染（除非通过迁移脚本）。
21. **`get_user_by_username` 等读用户接口没有去敏**：序列化用户出 `password` 哈希时仅在 `serialize_user_public` 中 pop，但 `authenticate_user` 返回的 dict 仍可能在主流程被 `print` 等记录。需要进一步确认日志策略。
22. **`get_current_user` 异常吞噬**（main.py:69–71）：`except Exception` 把所有异常打印 `print` 后返回 None；`print` 进 stdout，可能遗漏到日志监控外。
23. **`CLAUDE.md` 文档与代码不同步**：`/api/auth/register`、`mark-in-library`、`/api/sync/sql` 等接口在文档中存在但代码中没有，可能误导审查者；同时 `data/cases.db` SQLite 文件还在仓库里，但运行期已不使用，**`backend/main.py` 启动时不会读它**——需要确认是否还有外部消费者。

---

## 8. 后续对抗性审查建议重点

> 直接给 Codex / 人工审查的优先级清单。

1. **【最高】认证体系**：`get_current_user` 的 token 完全可伪造，相当于无认证。任何看似有权限校验的接口都被这一处穿透。建议优先评估替换成 JWT/Session 的迁移风险与破坏性。
2. **【高】`POST /api/reviews/{id}`**：admin 可以伪造 reviewer 字段；同时审核流程把 case.status / is_approved / is_in_library 一次写入。重点审查写一致性、伪造性、以及非 admin 触达此路由的可能性。
3. **【高】`PUT/POST /api/cases/{id}` 中 `status` 在 owner 白名单里**：owner 可改自己案例的状态字段，绕开 `submit_for_review` / `review_case` 状态机。需要确认是否实际可被绕过到 `approved`。
4. **【高】`POST /api/cases` 未登录创建非草稿案例**：审核队列污染、`owner_username` 为空、author 任意；考虑是否需要强制登录。
5. **【中】公开历史接口**：`GET /api/reviews/{id}` 和 `GET /api/versions/{id}` 完全匿名，可读出草稿/被驳回案例内容。审查应包括对私有内容是否经此泄露的实际验证。
6. **【中】`like` / `unlike` / `view_count` 防刷**：是否需要按用户/IP 限频。
7. **【中】跨集合写入无事务**：`create_case`、`delete_case`、`submit_for_review`、`review_case` 是否需要 replica set + 事务包裹；评估当前部署形态。
8. **【中】`update_case` 白名单中的 `is_approved` / `is_in_library`**：现在没有路由透传，但这是潜在地雷；任何新增 case 写入接口都可能踩中。
9. **【中】并发风险**：`versions.version_number` 通过“查最大值+1”手工生成，并发下可能撞号；`counters` 集合没有索引。
10. **【低】CORS 全开 + `allow_credentials=True`** 的配置矛盾。
11. **【低】CLI 创建用户缺密码强度校验**。
12. **需要进一步确认（人工）**：
    - 部署是 standalone MongoDB 还是 replica set？
    - `data/cases.db` 是否还有外部消费者？是否可以删除？
    - `deployments` 集合规划用途；`view_count` 是否被业务统计依赖。
    - `delete_case` 对 admin 删除别人草稿的禁止是预期还是 bug。
    - 是否真的需要让 view_count 自增对匿名开放。
13. **建议补测试**：
    - 单元测试覆盖 `update_case` 白名单与状态机交互。
    - 集成测试覆盖完整审核流程（draft → pending → approved/needs_revision → 再提交）。
    - 鉴权穿透测试（伪造 token、无 token、过期 token）。
    - 并发 versions / counters 的稳定性测试。
