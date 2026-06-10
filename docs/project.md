# 项目说明

本文档记录当前工程事实。产品需求见 `docs/prd.md`，API 索引见 `docs/api.md`，
AI 约束见 `docs/ai.md`。

## 当前状态

- 分支：`develop/alpha-summary`
- 代码库：`https://github.com/yangxuchen5898/case-library`
- 当前实现：可运行的 FastAPI + MongoDB + Vue/Vite alpha。
- 产品目标：上海大学专版思政案例库，后续向“正文 + 来源材料 + AI/人工批注 +
  版本快照”演进。
- 当前差距：后端已有版本记录和 `ai_reviews` 字段，但还没有 PRD 中定义的
  段落级批注、来源材料字段、AI 审核即版本快照、只读批注审核页。

## 目录职责

- `backend/`：FastAPI、MongoDB 数据层、账号脚本、迁移和 smoke 脚本。
- `frontend/`：Vue 3 + Vite 单页 alpha 前端，使用 hash 视图切换。
- `skills/`：思政案例提示词、模板和分类规则，是产品领域资产。
- `docs/`：项目、产品、API、AI、开发和质量文档。
- `docs/design/`：已跟踪的创建案例视觉参考图。
- `docs/case-library-design.zip`：本地 HTML 风格参考包，目前未跟踪，可作为设计参考。
- `agent-prompts/`：可复用 worker 提示词。
- `agent-runs/`：本地一次性 worker 输出，忽略不提交。

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
- 当前版本记录由编辑触发，不等同于 PRD 中“AI 审核生成只读版本”。
- 当前 AI 路由是通用 prompt chat，不是段落级批注 review endpoint。
- 当前前端创建流仍是五步 wizard，未改成“输入页 + 只读批注审核页”。
