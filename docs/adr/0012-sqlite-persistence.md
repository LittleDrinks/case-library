# ADR 0012：SQLite 服务端持久化（业务数据出 localStorage）

状态：已定案（v2.1）

## 决策

- 案例、审核留痕、批注、版本、收藏、点赞、素材登记、用户偏好、盯源、贡献全部存 SQLite（`./data/cases.db`，`db.py`）；localStorage 只留 UI 偏好。
- 数据模型按正式形态设计：status 状态机（draft/checking/pending/reviewing/published/hidden）、reviews 留痕含 reasonType、citations 带 evidence。
- 前端 store 改 API-backed：流转类操作 API-first，高频编辑本地+防抖 PATCH，失败 toast 明示。
- 登录不做：右上角下拉切换账号，token 身份用于归属与权限判断（编辑/提交仅 owner，审核仅 admin）。
- 检索统一走服务端 `/api/search`（BM25+bigram），前端本地 BM25 废除；命中带 sec 切片深链。

## 理由

多用户闭环（提交→审核→退回→复审）在 localStorage 下物理不成立；SQLite 满足演示期从简、模型按正式形态预留产品化路径的要求。
