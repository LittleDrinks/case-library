# 项目说明

本文档记录当前工程事实。产品需求见 `docs/prd.md`，API 索引见 `docs/api.md`，
AI 约束见 `docs/ai.md`。

## 当前状态

- 分支：`develop/alpha-summary`
- 代码库：`https://github.com/yangxuchen5898/case-library`
- 当前实现：可运行的 FastAPI + MongoDB + Vue/Vite alpha，已覆盖“正文 + 来源材料 +
  AI/人工批注 + 版本快照”主流程。
- 产品目标：上海大学专版思政案例库，继续围绕 alpha 验收收口视觉一致性、测试覆盖和
  文档一致性。
- 当前差距：创建流仍保留五步 wizard 形态；AI/人工批注已使用段落级 MVP，尚未实现
  字符级锚点、富文本编辑、文件上传、导出、多级审核或版本 diff/回滚。

## 目录职责

- `backend/`：FastAPI、MongoDB 数据层、账号脚本、迁移和 smoke 脚本。
- `frontend/`：Vue 3 + Vite 单页 alpha 前端，使用 hash 视图切换。
- `skills/`：思政案例提示词、模板和分类规则，是产品领域资产。
- `docs/`：项目、产品、API、AI、开发和质量文档。
- `docs/design/`：已跟踪的创建案例视觉参考图。
- `docs/case-library-design.zip`：本地 HTML 风格参考包，目前未跟踪，可作为设计参考。
- `agent-prompts/`：可复用 worker 提示词。
- `agent-runs/`：本地一次性 worker 输出，忽略不提交。

### 后端脚本和默认值

`backend/` 当前仍混放运行模块和操作脚本，暂不在 alpha PR 中搬目录：

- 运行模块：`main.py`、`database.py`、`schemas.py`、`ai_client.py`、`prompts.py`、
  `case_processor.py`、`search_engine.py`
- Compose 启动账号初始化：`backend/init_users.py`
- 管理员账号工具：`backend/account_admin.py`
- 演示数据脚本：`backend/demo.py`
- 迁移工具：`backend/migrate_sqlite_to_mongo.py`、`backend/migrate_timestamps.py`
- 本地 smoke/debug：`backend/smoke_test_mongo.py`
- 集成检查：`backend/test_submit_flow.py`，由 `make check` 调用
- E2E seed：`scripts/seed_e2e_accounts.py`，由 `docker-compose.dev.yml` 调用

`backend/init_users.py` 中的 `default123456` 仅用于首次空库初始化默认账号，所有默认账号
均设置 `must_change_password=true`。E2E 账号和 alpha demo 案例由
`scripts/seed_e2e_accounts.py` 确定性创建，仅用于 dev/e2e 环境。不要把真实账号、真实密码
或生产种子数据写入这些脚本。

`/api/constants` 的类型、主题和状态标签是当前 alpha 前后端共享默认值；变更时需同步
后端测试、前端 fallback 和文档。产品 prompt/template 资产当前保留在 `skills/`，后续若做
统一 prompt 管理，先按 issue #80 迁移路径和评测命令收口，不把 `.codex/` 代理技能混入产品
资产。

历史目录只读参考，不从中开发，不整目录复制：

- `/home/q2635/wsl-workspace/case-library-old`
- `/home/q2635/wsl-workspace/case-library-worktree-backup-20260605`

## 运行服务

`docker-compose.yml` 定义三个服务：

- `app`：FastAPI，宿主端口 `8001`
- `frontend`：Vite dev server，宿主端口 `18080`
- `mongo`：MongoDB，仅 Compose 网络内暴露

常用地址：

- API：`http://127.0.0.1:8001`
- Swagger：`http://127.0.0.1:8001/docs`
- OpenAPI：`http://127.0.0.1:8001/openapi.json`
- 前端：`http://127.0.0.1:18080/`

## 环境变量

`.env.example` 是可提交示例，`.env` 是本地文件，已忽略，禁止提交。

关键配置：

- MongoDB：`MONGODB_URI`、`MONGODB_DB_NAME`、`MONGODB_TIMEOUT_MS`
- 认证：`AUTH_SECRET`、`AUTH_TOKEN_TTL`
- AI：`AI_BASE_URL`、`AI_API_KEY`、`AI_MODELS`、`AI_DEFAULT_MODEL`、
  `AI_TIMEOUT_SECONDS`、`AI_REVIEW_ENABLED`
- 前端：`VITE_API_BASE_URL`、`FRONTEND_PORT`
- 镜像源：`APT_MIRROR`、`APT_SECURITY_MIRROR`、`PIP_INDEX_URL`、
  `NPM_CONFIG_REGISTRY`

禁止打印或提交真实 `AI_API_KEY`、AnySearch/Tavily key、代理地址和私有服务地址。

## 网络和代理

当前沙箱内普通网络可能 DNS 失败；提权后宿主网络可访问 GitHub。Docker Hub 直连
超时，但执行 `zsh -lic 'proxy_on'` 后可通过代理访问 Docker Registry。

`proxy_on` 定义在 `~/.zshrc`，会设置 shell 代理、写入 `/etc/docker/proxy.env`，
并在 Docker 正运行时重启 Docker。需要写系统目录时必须请求权限。

## 质量门禁

实现或脚手架变更完成前，在容器内运行：

```bash
docker compose up -d --build
curl -fsS http://127.0.0.1:8001/api/constants
curl -fsS http://127.0.0.1:18080/
docker compose ps
docker compose run --rm app make check
docker compose config --quiet
git diff --check
```

小范围文档修改可只运行 `git diff --check`，并在汇报中说明未跑完整门禁。

## 数据和资源

- 原始运行数据、Mongo dump、上传文件和未审材料不得提交。
- `data/` 保持忽略。
- 历史材料只能作为导入源：先只读盘点，再选择写导入器、精选 fixture 或记录弃用说明。
- 不把旧 `.claude/`、`.codex/` 工作流资产迁入产品仓库。

## 当前技术债

- `docs/api.md` 只做索引；真实契约以 FastAPI OpenAPI 为准。
- `POST /api/cases/{case_id}/ai-review` 已是 alpha 主流程的版本化段落批注接口；
  `/api/ai/chat` 仅作为兼容自查端点保留。
- 当前前端创建流仍是五步 wizard，而不是 PRD 理想形态中的单页输入 + 独立只读审核页。
- 当前 E2E 门禁覆盖 alpha 主路径，但仍偏精简；扩大稳定回归矩阵见 issue #78。
