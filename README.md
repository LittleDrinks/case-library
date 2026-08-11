# Case Library V2 Agent Handoff

## 版本管理

- `main` 只放稳定基线并打 tag；每个迭代一个分支（`v2.1`、`v2.2`…），验收后合回 main 打同名 tag。
- 当前：`v2.0` = demo 基线；`v2.1` = 开发中（范围见 `docs/demo-improvement-todo.md`）。

## 本目录：可运行演示原型

本目录是思政教学案例库的**可运行演示原型**，与下方云端主仓库（FastAPI + MongoDB + Vue 3）
不是同一套代码，请勿混淆。

- **技术形态**：无构建的原生 JS 前端（`app/`，`index.html` 直接引用 `app/js/*.js`）+
  单文件 Python 后端（`server.py`，仅依赖标准库 + `python-docx`）。
- **启动方式**：`/usr/bin/python3 server.py`（或 `python3 server.py [port]`）。
  端口优先取命令行参数，其次取 `.env` 的 `PROTOTYPE_PORT`，默认 `8080`
  （见 `server.py` 尾部启动代码）。知识图谱（WP7）需要 `.venv` 里的 neo4j 驱动：
  `python3 -m venv .venv && .venv/bin/pip install neo4j python-docx` 后用
  `.venv/bin/python server.py` 启动；`/usr/bin/python3` 启动时图谱接口降级，其余功能不变。
- **知识图谱（WP7）**：`docker compose up -d neo4j`（bolt 7687 / browser 7474，密码取
  `.env` 的 `NEO4J_PASSWORD`）；服务端启动时从 SQLite 全量灌库（LLM 实体增强后台补边，
  AI 不可用则跳过），案例/素材写路径增量同步。接口：`/api/graph/overview|ego|reverse|qa`
  与 `POST /api/admin/graph/rebuild`；Neo4j 不可达时返回降级提示，不影响其他功能。
- **数据架构**：业务数据（案例、审核留痕、批注、版本、收藏、点赞、素材登记）持久化在服务端
  SQLite（`db.py`，库文件 `data/cases.db`，首启自动灌入 `files/cases_seed.json` 与
  `files/materials_seed.json`）；素材的被引计数/待淘汰由服务端维护，新采集一律先落「候选」，
  管理员确认后才进检索语料（入库闸，ADR 0003）。前端 `app/js/store.js` 只缓存服务端数据并调
  `/api/cases`、`/api/materials` 等 REST 端点，`localStorage` 仅保留纯前端偏好。
  后端另有 AI 代理（`/api/ai/chat`，含 SSE 流式）、文件库（`/api/files`，上传 md/txt/docx
  自动抽取纯文本）、知识库在线导入（`/api/knowledge/import`）、服务端检索（`/api/search`，
  BM25，检索页与 AI 共用）与 docx 导出（`/api/export-docx`）。
  种子数据构建期写入 `app/data.js` 与 `files/`。
- **AI 配置**：`.env` 中的 `AI_BASE_URL` / `AI_API_KEY` / `AI_MODELS` /
  `AI_DEFAULT_MODEL` 等 `AI_*` 变量；密钥只存在服务端，浏览器通过
  `GET /api/constants` 的 `aiConfigured` 判断能力开关。
- **重建静态数据**：`python3 tools/build_data.py`（从 `assets/`、`examples/` 重新生成
  `app/data.js`、`files/index.json`、`files/users.json`、`files/cases_seed.json`、
  `files/materials_seed.json` 等，保留已有上传条目；提取 `app/seed.js` 种子案例需要本机有 node）。
- **冒烟测试**：`node tools/smoke_materials.js [baseUrl]`（加载真实 store.js 打真实服务端，
  覆盖素材同步/收藏/推荐/候选确认/查重/批量操作/被引计数）；`node tools/smoke_evidence.js`
  （引用证据链）；`node tools/smoke_review.js`（审核闭环：提交前自检/reasonType/
  退回台账/diffSummary/AI 生成标识）；`node tools/smoke_graph.js`（图谱：灌库计数/ego/reverse/
  全局问答/增量同步/AI 降级，需 Neo4j 在线）；`node tools/smoke_material_demo.js`（证据包、
  权威性分维度、自动入库边界、万级数据分页和闭环指标产品不变量，无需启动服务）。
- **素材闭环组件原型**：服务启动后访问 `/material-workspace.html`（教师证据包）、
  `/material-explorer.html`（万级素材掌控台）、`/material-intake.html`（候选审核）和
  `/material-metrics.html`（闭环测试）。四页共享模型和交互状态，可连续试用完整流程。
- **记忆 bench**：`python3 tools/bench_memory.py [--rejudge]`（用户级记忆三臂对照评测，
  需先以临时 `SQLITE_DB_PATH` 启动服务，报告见 `docs/memory-bench.md`）。

## 云端仓库

### 产品代码仓库

- `https://github.com/LittleDrinks/case-library.git`
- 这是当前 FastAPI + MongoDB + Vue 3/Vite 项目的主仓库。

### 原始参考仓库

- `https://github.com/yangxuchen5898/case-library.git`
- 仅用于参考原始 Skills、分类思路和案例资产，不要整目录复制实现。

## 技术栈

### 后端

- Python 3.12；
- FastAPI + Uvicorn；
- PyMongo；
- MongoDB 7；
- `python-docx` 用于 Docs/DOCX 导出；
- OpenAI-compatible 服务端 AI 客户端；
- AI 凭据只能存在后端环境变量，浏览器不得接收。

### 前端

- Vue 3；
- Vite 7；
- Node.js 20；
- Vitest + jsdom；
- Playwright。

### 工程环境

- Docker Compose 是默认运行、安装依赖、测试和构建环境；
- Dockerfile 基于 `python:3.12-slim`，复用 Node 20；
- 不要求宿主机安装 Python、Node 或 MongoDB 项目依赖。

## 端口和服务

| 服务 | 容器端口 | 宿主端口 | 地址 |
| --- | ---: | ---: | --- |
| Vue/Vite 前端 | 5173 | **18080** | `http://127.0.0.1:18080` |
| FastAPI 后端 | 8001 | 8001 | `http://127.0.0.1:8001` |
| MongoDB | 27017 | 不暴露 | Compose 网络内使用 |

18080 是前端演示和浏览器 QA 的固定入口，不要改成其他默认端口。后端 API 通过前端代理
使用 `/api`，健康检查地址为 `http://127.0.0.1:8001/api/constants`。

## Docker 启动

```bash
# 日常开发
docker compose up --build

# 后台启动
docker compose up --build -d

# 查看日志
docker compose logs -f app frontend

# 停止
docker compose down
```

开发/测试 Compose：

```bash
docker compose -f docker-compose.dev.yml up --build

# 需要 Playwright 时
docker compose -f docker-compose.dev.yml --profile e2e up --build
```

不要把 Mongo 数据卷、上传材料、Playwright 截图、运行日志或 Agent 过程文件提交到 Git。

## AI 环境变量

只在本地 `.env` 或受控部署环境配置，不要写入 README、源码、截图或测试报告：

```dotenv
AI_BASE_URL=
AI_API_KEY=
AI_MODELS=
AI_DEFAULT_MODEL=
AI_TIMEOUT_SECONDS=60
AI_REVIEW_ENABLED=false
VECTOR_SEARCH_ENABLED=false
VECTOR_BACKEND=none
EMBEDDING_MODEL=
```

MVP 不提供教师侧模型选择、自定义模型页或 MCP 配置页。模型、Agent 和内置 Skills 由服务端
处理；回答中显示实际使用的 Skill 名称即可。
