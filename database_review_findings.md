# 数据库与接口对抗性审查结果

> 来源：Codex `/codex:adversarial-review`（后台运行，task id `bz2s3n061`）。
> 审查范围：除 `CLAUDE.md` 之外的全部数据库相关代码、后端接口、配置、脚本和测试。
> 审查依据：当前代码事实 + `database_review_context.md`。
> Verdict：**needs-attention（No-ship）**。运行中后端存在直接的认证绕过、审核流程绕过、匿名写库、以及公开的审计/历史泄露。`database_review_context.md` 与代码在主要风险点上一致；`CLAUDE.md` 已按要求跳过。

---

## A. 最高风险问题（Critical / High）

### A1. [Critical] Bearer token 完全可伪造，所有权限校验形同虚设
- **涉及文件 / 函数**：`backend/main.py:57-93`（`get_current_user`、`login`）
- **涉及接口**：所有需要登录或管理员权限的路由，包括
  - `PUT/POST/DELETE /api/cases/{id}`
  - `POST /api/cases/{id}/submit`
  - `POST /api/reviews/{id}`
  - `POST /api/cases/{id}/visibility`
- **触发条件**：发送 `Authorization: Bearer <active_username>_<任意字符串>`，例如已知的 admin 用户名。
- **攻击路径**：登录接口签发的 token 形如 `username_timestamp`；`get_current_user` 仅按 `_` 拆分取出 username 后查库。无签名、无过期校验、无服务端 session、无 nonce、无密码绑定。
- **可能后果**：攻击者只要知道一个 active admin 用户名即可：审核/驳回案例、隐藏案例、删除数据、读取仅管理员可见的列表、冒充任意 owner 修改/删除其案例。现有测试 helper 会直接伪造 token，等于把这个错误契约固化进了测试，无法发现该漏洞。
- **证据代码位置**：`backend/main.py:57-71`、`backend/main.py:87-105`
- **最小修复方向**：替换为带签名与过期时间的 JWT，或改为服务端不透明 session；每次请求验证 issuer / expiry / signature。
- **必须补充的测试**：发送 `Authorization: Bearer 10000002_anything` 必须被拒绝。

### A2. [High] Owner 可直接把 status 改为 approved，绕过审核流程
- **涉及文件 / 函数**：`backend/main.py:226-264`（`_update_existing_case_impl`）；`backend/database.py` `update_case`
- **涉及接口**：`PUT /api/cases/{id}`、`POST /api/cases/{id}`
- **触发条件**：已登录 owner 在表单里直接传 `status=approved`。
- **攻击路径**：路由层只校验 “admin 或 owner”，并把 Form 中的 `status` 透传到 `case_data`；`update_case` 仅做 `CASE_STATUSES` 枚举校验，无状态机迁移检查。公开列表 / 搜索把 `status=approved` 视为已入库可见，即使 `is_approved` / `is_in_library` 为 false。
- **可能后果**：普通用户跳过审核直接发布；或把 `pending_review` 改回 `draft` / `needs_revision`，扰乱审核队列。
- **证据代码位置**：`backend/main.py:251-264`、`backend/database.py:644-672`
- **最小修复方向**：从普通更新表单中移除 `status` 白名单；状态变更只允许通过 `submit_for_review` / `review_case`，且强制校验角色与当前状态。
- **必须补充的测试**：owner `PUT status=approved`、`pending_review→draft`、`needs_revision→approved` 都应返回 403/400。

### A3. [High] 匿名用户可以创建 pending_review 案例，污染数据库
- **涉及文件 / 函数**：`backend/main.py:181-221`（`create_new_case`）
- **涉及接口**：`POST /api/cases`
- **触发条件**：不带 Authorization 头，使用默认 `status=pending_review`，或显式 `status=approved` / `needs_revision`。
- **攻击路径**：路由仅在 `status == draft` 时强制要求登录，其余情况下 `owner_username` 写空字符串，`author / department / type / theme / status / content` 全部由前端控制，传入 `create_case`。
- **可能后果**：匿名客户端可大量灌入无主审核记录、伪造作者元数据、产出只能由 admin 清理的孤儿案例；由于 `create_case` 只做枚举校验，理论上还可能直接落 `approved`。
- **证据代码位置**：`backend/main.py:193-222`、`backend/database.py:479-519`
- **最小修复方向**：所有案例创建路径都强制登录；`owner_username` 与 `author` 一律由 `current_user` 派生；忽略客户端传入的 `status`，仅在受控规则下允许 `draft` / `pending_review`。
- **必须补充的测试**：无 token `POST /api/cases`、无 token `status=approved` 都应被拒绝。

### A4. [High] 公开的审核与版本接口泄露草稿 / 隐藏案例的私有历史
- **涉及文件 / 函数**：`backend/main.py:458-465`（`get_case_reviews`、`get_case_version_history`）
- **涉及接口**：`GET /api/reviews/{case_id}`、`GET /api/versions/{case_id}`
- **触发条件**：任何未登录调用方知道或猜到 case id 即可访问。
- **攻击路径**：两条路由直接调用 `get_reviews` / `get_case_versions`，未做 `get_current_user`、案例存在性、状态、隐藏、归属、admin 等任何校验。数据库函数会返回该 case 的全部审核评论与版本快照。
- **可能后果**：草稿 / 被驳回 / 隐藏案例的内容与审核意见被绕过 `GET /api/cases/{id}` 的访问控制流出。
- **证据代码位置**：`backend/main.py:458-465`、`backend/database.py:839-846`
- **最小修复方向**：与案例详情同等的可见性策略 —— 业务允许时仅对 approved 且非隐藏案例公开，否则仅 owner / admin。
- **必须补充的测试**：无 token 访问 `draft`、`needs_revision`、隐藏的 approved 案例的 reviews / versions，均应被拒绝。

### A5. [High] 审计字段 reviewer 与 changed_by 完全信任前端
- **涉及文件 / 函数**：`backend/main.py:272-453`（`_update_existing_case_impl`、`review_case_endpoint`）；`backend/database.py` `review_case` / `update_case`
- **涉及接口**：`POST /api/reviews/{id}`、`PUT/POST /api/cases/{id}`
- **触发条件**：admin 在审核时传入 `reviewer=someone_else`；修改者在更新时传入 `updated_by=someone_else`。
- **攻击路径**：`review_case_endpoint` 把 Form 中的 `reviewer` 直接写入 `reviews`；更新接口把 Form 的 `updated_by / change_reason` 直接写入 `versions.changed_by / change_reason`。两处都没有与 `current_user` 比较。
- **可能后果**：审计轨迹与问责机制可被伪造；当 `reviews` / `versions` 被用于合规或争议处理时影响严重。
- **证据代码位置**：`backend/main.py:283-309`、`backend/main.py:442-455`、`backend/database.py:684-792`
- **最小修复方向**：`reviewer` 与 `updated_by` 一律由 `current_user.username` 或不可变的 user id 派生；`change_reason` 才视为用户文本。
- **必须补充的测试**：传入伪造的 `reviewer` / `updated_by` 时，被忽略并以认证用户身份落库。

---

## B. 中低风险问题（Medium / Low）

### B1. [Medium] 跨集合写入在部分失败时会留下不一致数据
- **涉及文件 / 函数**：`backend/database.py:508-792`
- **涉及操作**：`create_case`（cases → versions）、`submit_for_review`（cases → reviews）、`review_case`（cases → reviews）、`delete_case`（cases → reviews / versions / deployments）
- **触发条件**：MongoDB / 网络异常或进程在第一次写入后崩溃。
- **故障路径**：多次独立写入，没有 session transaction、重试、幂等键或补偿机制。
- **可能后果**：案例没有初始版本；pending / approved 案例没有审核记录；删除后 reviews / versions / deployments 残留为孤儿数据。**部署形态（standalone vs replica set）会决定是否能用事务**。
- **最小修复方向**：在支持事务的部署上用 MongoDB transactions 包住多集合变更；否则重排写入顺序以利于恢复，并加对账任务 / 模拟二次写入失败的测试。

### B2. [Medium] 并发更新可产生重复 version_number
- **涉及文件 / 函数**：`backend/database.py:313-692`（`update_case`、`init_db` 索引声明）
- **涉及接口**：`PUT/POST /api/cases/{id}`
- **触发条件**：对同一 case 的两个并发更新同时修改 `VERSIONED_FIELDS`。
- **故障路径**：`update_case` 走 “读 max(version_number) + 1 → 插入” 的非原子序列；`(case_id, version_number)` 索引非唯一。
- **可能后果**：同一 case 出现两个版本号相同的版本，历史排序与回滚 / 审计变得歧义。
- **最小修复方向**：在 `(case_id, version_number)` 上建唯一索引；通过 per-case 计数器或事务原子分配版本号；加并发更新测试。

### B3. [Medium] 点赞与浏览量匿名、可重复，且会污染排行 / 统计
- **涉及文件 / 函数**：`backend/main.py:157-376`
- **涉及接口**：`GET /api/cases/{id}`、`POST /api/cases/{id}/like`、`POST /api/cases/{id}/unlike`
- **触发条件**：脚本反复发起匿名请求。
- **攻击路径**：详情接口默认自增 `view_count`；like / unlike 完全无身份校验，仅做计数器加减。前端 localStorage 不构成服务端控制。
- **可能后果**：trending / recommendation 排序与 statistics 可被廉价操纵；unlike 还能在没有先 like 的情况下扣减计数到 0。
- **最小修复方向**：按用户或受限的 IP / device key 唯一去重 like；对 view 做速率限制；考虑不计 owner / admin 浏览。补充重复点赞 / 高频浏览测试。

### B4. [Medium] 无上限的 limit 参数 + 内存排序可被滥用做昂贵公共查询
- **涉及文件 / 函数**：`backend/main.py:121-416`
- **涉及接口**：`GET /api/cases`、`/api/search/advanced`、`/api/recommendations/{id}`、`/api/trending`、`/api/latest`
- **触发条件**：传入巨大的 `limit`，尤其是 `trending` 会先把所有 approved 案例加载到 Python 再排序。
- **故障路径**：路由参数原样传给 `limit(max(0, int(limit)))` 或用作 Python 切片；无上限。
- **可能后果**：未认证客户端就能强制大扫描 / 大响应 / 大内存排序，降级服务。
- **最小修复方向**：用 FastAPI `Query(ge=0, le=100)` 限制；服务层再设上限；把 trending 的排序与截断推到 Mongo 上的索引字段或预计算分数。补充超大 `limit` 的测试。

### B5. [Medium] 默认 admin 账号与密码被提交进初始化文件
- **涉及文件 / 函数**：`backend/init_users.py:13-49`、`backend/accounts.csv`
- **触发条件**：在非测试环境运行 `init_users.py` 或导入 `accounts.csv`。
- **故障路径**：默认 active admin 账号共用密码 `default123456`；`accounts.csv` 还包含其它 active admin 默认值。`must_change_password` 只在登录时返回给前端，后端**没有**在敏感操作前强制要求改密。
- **可能后果**：一旦默认账号进入生产，结合 A1 的可伪造 token，admin 失陷几乎是免费的。属于部署相关但影响极高。
- **最小修复方向**：从仓库中移除真实 / 默认管理员凭据；要求由环境变量提供 bootstrap secret；后端在 `must_change_password=true` 时拒绝所有非改密接口。
- **必须补充的测试**：`must_change_password=true` 的用户无法访问 admin / 案例修改类接口。

---

## C. 需要进一步确认的问题

```text
需要进一步确认
```

- MongoDB 部署是 **standalone 还是 replica set**？决定 B1 是否能用事务修复。
- 默认账号 / 初始化脚本是否会在生产环境运行？决定 B5 的实际危害等级。
- 是否允许 owner 物理删除已通过审核入库的案例？当前 `DELETE /api/cases/{id}` 是物理删除（`backend/main.py:312-341` + `backend/database.py:697-723`）。
- 审核意见与版本历史是否本就允许对 approved 案例公开？决定 A4 修复时的可见性边界。
- `deployments` 集合的未来用途？目前只有索引声明和删除时的级联清理，没有写入路径。

---

## D. 必须补充的测试用例清单（按优先级）

1. 伪造 token 冒充 admin（如 `Bearer 10000002_anything`）应被拒绝
2. 无 token `POST /api/cases` 应被拒绝
3. owner `PUT status=approved` 应被拒绝（同样验证 `pending_review→draft`、`needs_revision→approved`）
4. 普通用户修改别人的案例应被拒绝
5. 无 token 访问 `GET /api/reviews/{id}`、`GET /api/versions/{id}` —— 在 draft / needs_revision / 隐藏 approved 上应被拒绝
6. 管理员审核时伪造 `reviewer` 应被忽略并以当前登录管理员身份落库
7. 修改案例时伪造 `updated_by` 应被忽略并以当前登录用户身份落库
8. 并发更新同一案例不应产生重复 `version_number`
9. 创建案例成功但 versions 写入失败的对账 / 恢复行为
10. 删除案例中途失败不应留下不可见的孤儿数据
11. 重复 like / unlike 应被阻断
12. 巨大 `limit` 应被截断
13. 已禁用用户（`status=no_active`）使用旧 token 访问任何接口应被拒绝

---

## E. 建议的修复优先级路线

1. **替换可伪造 token**（A1）—— 解掉所有下游权限失效
2. **从 owner 更新路径移除客户端可控的 `status`**（A2）—— 修复审核流程绕过
3. **创建案例强制登录、归属由服务端派生**（A3）—— 阻断匿名写入
4. **保护 reviews / versions 读取**（A4）—— 阻断历史 / 审核意见泄露
5. **`reviewer` / `updated_by` 一律来自 `current_user`**（A5）—— 恢复审计可信度
6. **跨集合写入加事务 / 对账**（B1）+ **`(case_id, version_number)` 唯一索引 + 原子分配**（B2）—— 数据一致性
7. **like / view / 大 `limit` 限频与上限**（B3、B4）+ **清理默认账号、强制 `must_change_password`**（B5）—— 滥用与运维加固

---

## 本次最值得立即修复的 Top 5 问题

1. 替换可伪造的 Bearer token（A1）
2. 从 owner 更新路径移除客户端可控的 `status`（A2）
3. 创建案例强制登录、`owner_username` 与 `author` 由服务端派生（A3）
4. 保护 `GET /api/reviews/{id}` 与 `GET /api/versions/{id}`（A4）
5. `reviewer` 与 `updated_by` 一律来自 `current_user`（A5）

---

## F. 修复记录（Top 5 已落地）

> 修复日期：2026-05-06。修复范围限定为 Top 5（A1–A5）。B 节中低风险问题与 C 节待确认问题尚未处理。

### F1. A1 — 替换可伪造 Bearer token
- **改动文件**：`backend/main.py`、`backend/test_submit_flow.py`
- **改动内容**：
  - `backend/main.py` 引入 `base64` / `hashlib` / `hmac` / `json` / `secrets`（均为 stdlib，无新依赖）。
  - 新增 `create_auth_token(username)` / `verify_auth_token(token)`：token 格式为 `base64url(payload).base64url(hmac_sha256(payload, secret))`，payload 含 `u`（username）、`iat`、`exp`。
  - 密钥来源：`AUTH_SECRET` 环境变量；未设置时进程启动随机生成并打印警告（重启后旧 token 会失效）。
  - TTL 默认 7 天，可由 `AUTH_TOKEN_TTL` 覆盖。
  - `get_current_user` 改为：先按 `Bearer <token>` 解析 Authorization 头，验签 + 验过期，再用解出的 username 查库；并仍要求 `status == 'active'`。
  - `POST /api/auth/login` 用 `create_auth_token(...)` 替代 `f"{username}_{timestamp}"`。
  - `backend/test_submit_flow.py` 的 `auth(username)` 改为通过 `main.create_auth_token(username)` 获取合法 token，不再伪造旧格式。
- **新部署须知**：生产环境必须显式设置 `AUTH_SECRET`，否则进程重启会让全部已签发 token 失效。

### F2. A2 — 移除 owner 更新路径上的客户端可控 `status`
- **改动文件**：`backend/main.py`
- **改动内容**：
  - 从 `_update_existing_case_impl` 的参数列表与 `case_data` 装配中删除 `status`。
  - 从 `PUT /api/cases/{case_id}` 与 `POST /api/cases/{case_id}` 路由签名中删除 `status: Optional[str] = Form(None)`。
  - FastAPI 对未声明的 Form 字段会忽略，因此前端若仍发送 `status=...` 不会 400，但服务端不会再使用该值。
- **效果**：状态机变更仅能通过 `POST /api/cases/{id}/submit` 与 `POST /api/reviews/{id}`，owner 无法绕开审核直接发布。

### F3. A3 — 案例创建强制登录、归属由服务端派生
- **改动文件**：`backend/main.py`、`backend/case_processor.py`
- **改动内容**：
  - `POST /api/cases` 现在在所有路径下都要求 `current_user`，否则返回 401。
  - `owner_username = current_user.username`；`author = current_user.nickname or current_user.username`；删除 `author` Form 参数，前端无法再伪造 author。
  - `status` 仅允许 `draft` / `pending_review`，其它值返回 400。
  - `process_new_case`（auto_process 路径）签名新增 `owner_username` 参数并写入 case 文档，避免 auto-process 案例归属为空。
- **效果**：匿名灌库与匿名污染审核队列被切断；author 元数据无法被伪造；`status=approved/needs_revision/deleted` 等非法初始状态被拒绝。

### F4. A4 — 给 reviews / versions 接口加可见性校验
- **改动文件**：`backend/main.py`
- **改动内容**：
  - 新增 `_ensure_case_history_visible(case_id, current_user)`：案例不存在 → 404；admin 或 owner → 通过；其余仅在 `status == 'approved'` 且 `is_hidden == False` 时通过；否则 403。
  - `GET /api/reviews/{case_id}` 与 `GET /api/versions/{case_id}` 两个路由增加 `request: Request` 参数，先 `get_current_user` 再走 `_ensure_case_history_visible`。
- **效果**：草稿、`needs_revision`、隐藏的 approved 案例的审核意见与版本历史不再对匿名 / 非归属用户暴露；公开案例（已审核且未隐藏）继续可读，符合既有 UX。

### F5. A5 — `reviewer` 与 `updated_by` 由服务端派生
- **改动文件**：`backend/main.py`
- **改动内容**：
  - `POST /api/reviews/{case_id}`：删除 `reviewer: str = Form(...)`；落库 `reviewer = current_user.username`。`comment` 仍是用户文本。
  - `PUT/POST /api/cases/{case_id}`：删除 `updated_by: str = Form("system")`；`update_case` 内部记录 `versions.changed_by` 时使用 `current_user.username`。`change_reason` 仍是用户文本。
- **效果**：`reviews.reviewer` 与 `versions.changed_by` 不再可被前端伪造，审计可信度恢复。

### F6. 验证手段
- **既有回归**：`backend/test_submit_flow.py` 重新跑通（`submit flow checks passed`）。
- **新增对抗性冒烟**（一次性脚本，未提交）覆盖以下用例并全部通过：
  - 伪造 `Bearer admin_1` 形式访问 `DELETE /api/cases/{id}` → 401
  - 匿名 `POST /api/cases` → 401
  - 已登录 `POST /api/cases` 携带 `status=approved` → 400
  - `POST /api/cases` 创建后 `owner_username` 与登录用户一致
  - owner `PUT /api/cases/{id}` 携带 `status=approved` → 案例 status 仍为 draft
  - `PUT /api/cases/{id}` 携带 `updated_by=mallory` → `versions.changed_by` 为登录用户
  - admin `POST /api/reviews/{id}` 携带 `reviewer=mallory` → `reviews.reviewer` 为登录管理员
  - 匿名 / 非归属用户 `GET /api/reviews/{id}` 与 `GET /api/versions/{id}` 在 draft 案例上 → 403
  - owner / admin 读取 draft 历史 → 200
  - approved 案例的 reviews / versions 仍对公众可读 → 200

### F7. 未在本次范围内的遗留项
- B1 跨集合写入无事务、B2 `version_number` 并发撞号、B3 like/view 防刷、B4 `limit` 上限、B5 默认 admin 账号清理：仍待处理。
- C 节中所有“需要进一步确认”项尚未推进。
- 测试缺口：本次仅做一次性对抗性冒烟脚本，未将其固化为仓库内的回归测试套件。建议后续把上述用例迁移到 pytest 或 `test_submit_flow.py` 同级的脚本里固化。
