# 项目说明

本文档记录当前工程事实。产品需求见 `docs/prd.md`，API 索引见 `docs/api.md`，
AI 约束见 `docs/ai.md`。

## 当前状态

- 分支：`develop`
- 代码库：`https://github.com/yangxuchen5898/case-library`
- 当前实现：可运行的 FastAPI + MongoDB + Vue/Vite alpha，已覆盖“正文 + 来源材料 +
  AI/人工批注 + 版本快照”主流程。
- 产品目标：上海大学专版思政案例库，继续围绕 alpha 验收收口视觉一致性、测试覆盖和
  文档一致性。
- 前端基线：issue #156 将当前 UI/交互声明为 alpha frontend baseline，冻结范围见
  `docs/frontend-baseline.md`。
- 当前差距：创建流仍保留五步 wizard 形态；AI/人工批注已使用段落级 MVP，尚未实现
  字符级锚点、富文本编辑、文件上传、导出、多级审核或版本 diff/回滚。

## 目录职责

- `backend/`：FastAPI、MongoDB 数据层、账号脚本、迁移和 smoke 脚本。
- `frontend/`：Vue 3 + Vite 单页 alpha 前端，使用 hash 视图切换；顶层视图使用
  `defineAsyncComponent` 懒加载，构建时保留独立 `vendor` chunk。
- `prompts/`：思政案例提示词、模板、分类规则和评测样例，是产品领域资产；
  不再使用根目录 `skills/`，避免与 `.codex/skills` 等代理技能目录混淆。
- `docs/`：项目、产品、API、AI、开发和质量文档。
- `docs/design/`：已跟踪的创建案例视觉参考图。
- `docs/case-library-design.zip`：本地 HTML 风格参考包，目前未跟踪，可作为设计参考。
- `agent-prompts/`：可复用 worker 提示词。
- `agent-runs/`：本地一次性 worker 输出，忽略不提交。

### 后端脚本和默认值

`backend/` 当前保留运行模块；后端测试脚本已迁入 `backend/tests/`，操作脚本已迁入
`backend/scripts/`。
第一阶段布局：

- 运行入口：`backend/app/main.py` 是唯一 canonical FastAPI app，Compose、Dockerfile 和
  `make run` 使用 `backend.app.main:app`。旧 top-level main 兼容入口已移除；测试和脚本
  必须使用 `backend.app.main` 或更具体的 canonical 模块。
- API 装配：`backend/app/api/router.py` 聚合 API 路由；`backend/app/api/routes/` 是 canonical
  route 实现。旧 `backend/routers/` 兼容导出已移除。
- 核心和数据边界：`backend/app/core/` 保存认证与 FastAPI dependency helper；
  `backend/app/db/database.py` 聚合 canonical db/repository/service 导出。旧 top-level
  database 兼容导出已移除；
  Mongo 连接、计数器、校验和 repository helper 分别位于 `backend/db/` 和
  `backend/repositories/`；case serializer 实现位于 `backend/app/domains/cases/serializers.py`，
  旧 `backend/serializers.py` 兼容导出已移除。
- 其他运行模块：`backend/app/domains/*/schemas.py` 保存 domain schema 定义，
  旧 `backend/schemas.py` 兼容导出已移除；`backend/app/domains/cases/processing.py` 保存
  `auto_process` 案例处理 helper，`backend/app/domains/public/service.py` 保存公开搜索 facade。
- Prompt runtime：`prompts/runtime/` 保存运行时产品 prompt 元数据、配置和
  markdown body；`backend/app/domains/ai/prompts/` 作为 AI domain 内部加载器和查询 API，提供稳定 prompt ID、
  数据结构和查询入口。`/api/prompts` 只返回元数据，不返回 prompt body。
  `prompts/runtime/prompts.json` 中的 `asset_id` 映射到
  `prompts/runtime/<asset_id>/` prompt body 目录；`prompts/case-writing/` 保存长文模板和参考材料，
  `prompts/classification/` 保存分类器规则。
- `backend/services/`：业务 helper 归属；当前包含公开检索、推荐、最新/热门和统计缓存 helper，
  公开读缓存 seam，以及公开浏览/点赞类写入的身份和限流 seam。
- `backend/db/transactions.py`：跨 cases、versions、reviews 的多集合写入边界；当前使用
  best-effort compensation helper，保持现有 Mongo 部署兼容。
- Compose 启动账号初始化：`backend/scripts/init_users.py`
- 管理员账号工具：`backend/scripts/account_admin.py`
- 演示数据脚本：`backend/scripts/demo.py`
- 迁移工具：`backend/scripts/migrate_sqlite_to_mongo.py`、
  `backend/scripts/migrate_timestamps.py`
- 本地 smoke/debug：`backend/tests/smoke/smoke_test_mongo.py`
- 单元脚本：`backend/tests/unit/test_contract_helpers.py` 覆盖纯 contract helper，如段落拆分、段落批注
  规范化、AI review summary 规范化和公开案例快照序列化白名单。
- 单元脚本：`backend/tests/unit/test_prompt_injection.py` 覆盖产品 prompt/template 的注入边界。
- 单元脚本：`backend/tests/unit/test_public_search_helpers.py` 覆盖公开检索、过滤、推荐、热门、最新和
  公开读缓存 helper。
- 单元脚本：`backend/tests/unit/test_security_dependencies.py` 覆盖认证、权限和依赖装配 helper。
- 单元脚本：`backend/tests/unit/test_database_repository_helpers.py` 覆盖数据库 repository helper、
  多集合写入补偿边界和公开交互反滥用 seam。
- 集成检查：`backend/tests/integration/test_submit_flow.py`，由 `make check` 调用，仍作为提交、
  AI/人工审核、权限、公开可见性和统计缓存主流程的回归门禁。
- 旧兼容入口：`backend/test_contract_helpers.py`、`backend/test_prompt_injection.py`、
  `backend/test_submit_flow.py`、`backend/smoke_test_mongo.py` 已移除，新命令只使用
  `backend/tests/` 下的规范路径。
- Alpha/E2E seed：`scripts/seed_e2e_accounts.py`，仅在 `ENABLE_DEMO_SEED=true` 时运行；
  默认 `docker-compose.yml` 不再调用，开发/e2e 通过 `docker-compose.dev.yml` 显式启用

`backend/scripts/init_users.py` 中的 `default123456` 仅用于首次空库初始化默认账号，所有默认账号
均设置 `must_change_password=true`。测试账号和 alpha demo 案例由
`scripts/seed_e2e_accounts.py` 确定性创建，仅用于本地 alpha demo、dev 和 e2e 环境。
该 seed 中的演示管理员 `10000002` 为便于浏览器验收不强制改密，不代表生产默认账号策略。
不要把真实账号、真实密码或生产种子数据写入这些脚本。

`/api/constants` 的类型、主题和状态标签是当前 alpha 前后端共享默认值；API-facing 常量集中在
`backend/app/shared/constants.py`，变更时需同步后端测试、前端 fallback 和文档。
产品 prompt/template 资产已迁入 `prompts/`；
后续若做统一 prompt 管理，应继续以 `prompts/runtime/` 管理运行时 prompt
元数据、配置和 markdown body，并以 `backend/app/domains/ai/prompts/` 提供的稳定 ID 为 API
契约，不要把 `.codex/` 代理技能混入产品资产。issue #80 的完整自动评测 harness 尚未
落地，当前仅保留 `prompts/case-writing/evals/evals.json` 样例、`prompts/runtime/evals/`
运行时 fixture 和注入边界测试。

历史目录、备份目录或其他项目目录只能作为只读参考；不从中开发，不整目录复制。

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
- 跨域：`CORS_ALLOW_ORIGINS`。后端未配置时默认不放行跨域；
  Compose 和 `.env.example` 为本地开发提供 localhost 默认值，生产必须显式设置允许源。
- AI：`AI_BASE_URL`、`AI_API_KEY`、`AI_MODELS`、`AI_DEFAULT_MODEL`、
  `AI_TIMEOUT_SECONDS`、`AI_REVIEW_ENABLED`
- 前端：`VITE_API_BASE_URL`、`FRONTEND_PORT`
- 镜像源：`APT_MIRROR`、`APT_SECURITY_MIRROR`、`PIP_INDEX_URL`、
  `NPM_CONFIG_REGISTRY`。默认使用官方源；国内镜像只应通过本地 `.env` 或构建参数显式启用。

禁止打印或提交真实 `AI_API_KEY`、AnySearch/Tavily key、代理地址和私有服务地址。

## 网络和代理

若 Docker 拉取镜像或安装依赖失败，先按 `docs/development.md` 的网络诊断命令确认问题。
代理、镜像源和 Docker daemon 配置属于本地开发环境，不写入仓库规范；需要时通过本机
环境变量、Docker 配置或团队约定的安全方式启用。

## 质量门禁

后端测试发现由 `pyproject.toml` 指向 `backend/tests/`，不再依赖根目录 `tests/` 或逐个
执行脚本的 fallback。当前架构回归矩阵：

| 层级 | 本地入口 | CI 入口 | 覆盖重点 |
| --- | --- | --- | --- |
| 后端 lint | `make lint` | `make lint` | `backend/` ruff 规则 |
| 后端单元 | `make test-backend-unit` | `make test-backend-unit` | contract、prompt 注入、公开检索、权限、repository 和 AI service seam；repository/service seam 使用 compose MongoDB，默认排除 `real_ai` |
| 后端集成 | `make test-backend-integration` | `make test-backend-integration` | 登录、提交、审核、公开可见性、统计缓存和 OpenAPI 文档主流程 |
| 前端单元 | `make test-frontend-unit` | `make test-frontend-unit` | Vue draft/split helper 单元行为 |
| Mock E2E | `make test-e2e-mock` | `npm run test:e2e:mock` in e2e profile | dev seed + mock AI 的稳定浏览器回归；容器内只跑不依赖 Docker CLI 的 spec |
| OpenAPI smoke | `make openapi-smoke` | `make openapi-smoke` | `/docs`、`/openapi.json`、关键 path/schema/security scheme |
| 覆盖率 | `make cov` | `make cov` + artifact | `coverage.xml`、`htmlcov/`，当前非回退阈值为 30% |
| Compose 配置 | `docker compose config --quiet` / dev e2e config | 同左 | 默认 compose 和 dev e2e profile 可解析 |
| 真实 AI smoke | 手动 workflow 或受控本地环境 | `Real AI Smoke` 手动 opt-in | 使用密钥环境变量调用真实供应商，不打印 key、base URL 或 prompt |

实现或脚手架变更完成前，在容器内运行与变更相称的门禁；完整本地门禁为：

```bash
docker compose up -d --build
curl -fsS http://127.0.0.1:8001/api/constants
curl -fsS http://127.0.0.1:18080/
docker compose ps
docker compose run --rm app make check
docker compose run --rm app make openapi-smoke
docker compose run --rm app make cov
docker compose config --quiet
docker compose -f docker-compose.dev.yml --profile e2e config --quiet
git diff --check
```

小范围文档修改可只运行 `git diff --check`，并在汇报中说明未跑完整门禁。

## E2E 产物

Playwright 默认输出到忽略目录；常规截图/trace 产物在 `agent-runs/screenshots/`，baseline
demo 视频按 `docs/development.md` 的命令生成到 `agent-runs/demo-media/`。这些产物用于
本地验收和交接，不进入 git。

## 数据和资源

- 原始运行数据、Mongo dump、上传文件和未审材料不得提交。
- `data/` 保持忽略。
- 历史材料只能作为导入源：先只读盘点，再选择写导入器、精选 fixture 或记录弃用说明。
- 不把旧 `.claude/`、`.codex/` 工作流资产迁入产品仓库。

## 当前技术债

- `docs/api.md` 只做索引；真实契约以 FastAPI OpenAPI 为准。
- `POST /api/cases/{case_id}/ai-review` 已是 alpha 主流程的版本化段落批注接口；
  `/api/ai/chat` 仅作为兼容自查端点保留。
- 后端模块拆分第一阶段边界见 `docs/backend-module-split.md`；拆分前必须保持
  `docs/api.md` 的前端 baseline 契约不变。
- 当前前端创建流仍是五步 wizard，而不是 PRD 理想形态中的单页输入 + 独立只读审核页。
- 当前 E2E 门禁覆盖 alpha 主路径，但仍偏精简；扩大稳定回归矩阵见 issue #78。
