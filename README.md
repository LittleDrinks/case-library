# Case Library

上海大学“强国有我”大思政课案例库 alpha。

这是一个用于思政案例创建、AI 自查、人工审核和公开展示的 Web 应用。当前版本以
FastAPI、MongoDB、Vue 3 和 Vite 构建，后端运行入口为 `backend.app.main:app`。

## 功能概览

- 教师登录后创建案例，填写正文、来源材料和分类信息。
- 服务端 AI 自查生成段落级批注和版本快照。
- 管理员审核案例，支持通过、退回和人工段落批注。
- 公开案例库展示已通过案例，并隐藏 AI、人工审核、prompt 和模型等内部字段。
- 后台脚本支持 CSV/XLSX 批量导入用户，暂不开放自助注册通道。

## 目录结构

- `backend/`：FastAPI 应用、MongoDB 数据访问、领域服务、账号脚本和后端测试。
- `frontend/`：Vue 3 + Vite 前端、组件、页面、Playwright/Vitest 测试。
- `prompts/`：当前产品 prompt、模板、分类规则和评测样例。
- `docs/`：产品、API、AI、安全、开发和质量门禁文档。
- `scripts/`：演示数据、E2E seed 和辅助脚本。

## 本地启动

项目默认使用 Docker Compose 运行。

```bash
docker compose up -d --build
```

常用地址：

- 前端：`http://127.0.0.1:18080/`
- API：`http://127.0.0.1:8001`
- Swagger：`http://127.0.0.1:8001/docs`
- OpenAPI：`http://127.0.0.1:8001/openapi.json`

停止服务：

```bash
docker compose down
```

## 开发环境启动（不用 Docker）

开发环境也可以在宿主机直接启动后端和前端，但浏览器端必须继续通过同源 `/api`
访问后端，不要把前端 API 地址改成 `http://127.0.0.1:8001`，避免跨域。

前置要求：

- Python 3.12
- Node.js 20+
- 本机 MongoDB，监听 `mongodb://127.0.0.1:27017`

准备本地配置：

```bash
cp .env.example .env
```

本机启动时建议在 `.env` 中至少确认：

```env
MONGODB_URI=mongodb://127.0.0.1:27017
MONGODB_DB_NAME=case_library
VITE_API_BASE_URL=/api
AI_REVIEW_ENABLED=false
```

安装后端依赖并启动 API：

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
python backend/scripts/init_users.py
uvicorn backend.app.main:app --host 0.0.0.0 --port 8001 --reload
```

另开一个终端安装前端依赖并启动 Vite：

```bash
cd frontend
npm ci
npm run dev
```

前端开发地址：

- `http://127.0.0.1:5173/`

本仓库的 Vite 开发代理把 `/api` 转发到 `http://app:8001`。不用 Docker 启动时，
需要让本机能解析 `app` 到 `127.0.0.1`，否则前端代理无法连到后端：

```bash
sudo sh -c 'grep -q "^127.0.0.1 app$" /etc/hosts || echo "127.0.0.1 app" >> /etc/hosts'
```

验证同源代理是否可用：

```bash
curl -fsS http://127.0.0.1:5173/api/constants
```

## 配置

复制 `.env.example` 为 `.env` 后按需修改本地配置。

关键配置包括：

- MongoDB：`MONGODB_URI`、`MONGODB_DB_NAME`
- 认证：`AUTH_SECRET`、`AUTH_TOKEN_TTL`
- AI：`AI_BASE_URL`、`AI_API_KEY`、`AI_MODELS`、`AI_DEFAULT_MODEL`、`AI_REVIEW_ENABLED`
- 前端：`VITE_API_BASE_URL`、`FRONTEND_PORT`

不要提交真实 `.env`、API key、私有模型地址、账号表或数据库导出。

## 质量门禁

完整检查建议在容器内执行：

```bash
docker compose run --rm app make check
docker compose run --rm app make openapi-smoke
docker compose run --rm app make cov
docker compose config --quiet
docker compose -f docker-compose.dev.yml --profile e2e config --quiet
git diff --check
```

前端 mock E2E：

```bash
docker compose -f docker-compose.dev.yml --profile e2e run --rm e2e npm run test:e2e:mock
```

真实 AI smoke 只应在受控环境手动 opt-in，且不得打印密钥、私有 base URL、完整 prompt 或用户材料。

## 用户导入

学校统一身份认证接入前，使用后台脚本导入账号，不开放公共注册。

```bash
docker compose run --rm app python backend/scripts/account_admin.py import-users \
  --file /app/backend/accounts.csv \
  --dry-run
```

支持 `.csv` 和 `.xlsx`。完整操作步骤、表头模板、dry-run 和单账号维护命令见
`docs/user-import.md`。

## 文档入口

- 产品需求：`docs/prd.md`
- 项目结构和工程事实：`docs/project.md`
- API 说明：`docs/api.md`
- AI 行为和 prompt 边界：`docs/ai.md`
- 开发与验证流程：`docs/development.md`
- 用户导入操作手册：`docs/user-import.md`
- 质量门禁：`docs/quality.md`
