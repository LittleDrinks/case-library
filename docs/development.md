# 开发指南

## 本地启动

本项目强制使用 Docker Compose / Dev Container 作为开发和验证环境。本机没有完整
项目运行环境，不应在宿主机直接安装依赖、运行后端、运行前端或执行测试。

```bash
docker compose up -d --build
```

服务地址：

- 后端：`http://127.0.0.1:8001`
- 前端：`http://127.0.0.1:18080`
- Swagger：`http://127.0.0.1:8001/docs`

## 网络问题

若 Docker 拉取镜像或安装依赖失败，先确认是否是网络问题：

```bash
curl -I --max-time 8 https://github.com
curl -I --max-time 8 https://registry-1.docker.io/v2/
```

当前环境中 Docker Hub 直连可能超时。若需要代理，应通过本机环境变量、Docker daemon
代理配置或团队约定的开发环境配置显式启用，不要把个人 shell 函数写入仓库配置。

```bash
curl -I --max-time 8 https://registry-1.docker.io/v2/
```

代理可用时，Docker Registry 应返回 `401 Unauthorized`，这是未登录 registry 的正常响应。

## 常用命令

```bash
docker compose up -d --build
docker compose ps
docker compose logs -f
docker compose run --rm app make check
docker compose config --quiet
docker compose down
```

允许在宿主机执行的操作仅限于：git、文档编辑、文件搜索、网络诊断、Docker/Compose
控制命令。所有项目运行、依赖安装、lint、测试、构建都必须在容器内完成。

## 测试布局第一阶段

后端测试脚本已经迁入 `backend/tests/` 第一阶段布局，`Makefile` 直接调用新路径。旧
`backend/test_*.py` 和 `backend/smoke_test_mongo.py` 只保留薄兼容 wrapper，后续新命令和文档
不要再依赖旧路径。

- `backend/tests/unit/test_contract_helpers.py`：后端单元脚本，只覆盖不需要启动 FastAPI 或真实 MongoDB
  流程的 contract helper。当前范围包括段落拆分、段落批注规范化、AI review summary 规范化、
  公开案例字段白名单和 reviewed version 公开快照行为。
- `backend/tests/unit/test_prompt_injection.py`：产品 prompt/template 的注入边界检查。
- `backend/tests/integration/test_submit_flow.py`：后端集成门禁，继续覆盖登录改密、提交审核、AI/人工批注版本、
  作者/管理员权限、隐藏/公开可见性、公开搜索/推荐/统计缓存等主流程，不用单元测试替代。
- `backend/tests/smoke/smoke_test_mongo.py`：本地 MongoDB smoke/debug 脚本，不属于 `make check`
  默认门禁，由 `make smoke` 调用。
- `frontend/tests/smoke.spec.js`、`frontend/tests/audit.spec.js`、`frontend/tests/demo-media.spec.js`：
  浏览器 E2E/baseline 验收；`frontend/tests/support/*` 只放浏览器测试辅助函数。

## 前端依赖异常

如果 Vite 或 node_modules 损坏，只重置前端依赖卷：

```bash
docker compose stop frontend
docker volume rm case-library_frontend_node_modules
docker compose up -d frontend
```

## 演示账号与 E2E seed

默认 `docker compose up` 不再创建固定密码的 E2E 演示账号和演示案例。
`scripts/seed_e2e_accounts.py` 只在 `ENABLE_DEMO_SEED=true` 时执行。

用于系统演示的完整示例案例见 `docs/demo-case.md`，其中包含案例正文、来源材料、元数据、
AI/人工审核批注示例以及 fixture 数据结构。本地 seed 和 E2E 截图验收可引用该文件内容。

开发/E2E 环境使用 dev compose，默认启用 seed：

```bash
docker compose -f docker-compose.dev.yml up -d --build
```

如需在 dev 环境下也关闭 seed：

```bash
ENABLE_DEMO_SEED=false docker compose -f docker-compose.dev.yml up -d --build
```

手动触发 seed：

```bash
make dev-seed
```

本地 demo/E2E seed 会创建可直接验收的演示管理员 `10000002` / `default123456`，
该账号不会触发强制改密弹窗。生产或默认初始化账号仍由 `backend/init_users.py`
创建，并保持首次登录强制改密。

容器化 E2E 入口使用同一套 dev compose seed 路径，只运行不依赖宿主机 Docker 的
`frontend/tests/audit.spec.js`：

```bash
make dev-e2e
```

完整 smoke E2E 入口会先启动 dev compose，再由宿主机运行完整 Playwright suite：

```bash
make smoke-e2e
```

`make smoke-e2e` 会启动 `docker-compose.dev.yml`。如果已经用默认 `docker compose up
-d --build` 启动了服务，两个 compose 项目会占用同一组本地端口；请先执行
`docker compose down`，或本次直接从 dev compose 启动。该入口运行
`frontend/tests/smoke.spec.js`，测试中会调用宿主机 `docker compose exec`，因此需要在有
Docker CLI/daemon 的宿主机执行，并通过 `SMOKE_E2E_COMPOSE_FILE=docker-compose.dev.yml`
把测试内的 compose exec 指向同一套 dev compose 服务。

## E2E demo 视频

issue #161 的交接视频使用 Playwright 录制，不提交视频二进制。先启动带 seed 的 dev
compose，再在 `e2e` profile 容器内运行专用 spec：

```bash
docker compose -f docker-compose.dev.yml up -d --build
docker compose -f docker-compose.dev.yml --profile e2e run --rm e2e npm run test:e2e:demo-media
```

该命令只跑桌面端 `frontend/tests/demo-media.spec.js`，并把 Playwright 产物写入
`agent-runs/demo-media/`。每个测试用例生成一段 `.webm`，对应四条 baseline 用户路径：

- 教师从“我的提交”进入创建，填写基本信息、正文、来源材料和分类，生成 AI 只读审核版本，
  查看 AI 批注并提交人工审核。
- 管理员进入审核管理，查看提交版本、预览和 AI 自查意见，添加人工段落批注并退回。
- 作者在“我的提交”查看退回结果、AI/人工段落批注，复制版本并重新提交修改。
- 管理员通过修改稿后，匿名用户从首页/案例库浏览公开案例，搜索和筛选公开结果，并确认不
  展示 AI/人工审核内部信息。

`agent-runs/`、`frontend/test-results/`、`frontend/playwright-report/` 和相关 trace/report
目录已被 `.gitignore` 覆盖。若需要临时换目录或强制开启视频，可复用同一配置入口：

```bash
PLAYWRIGHT_OUTPUT_DIR=../agent-runs/demo-media PLAYWRIGHT_VIDEO=on npm run test:e2e -- tests/demo-media.spec.js --project=chromium-desktop
```

## 开发约束

- 不提交 `.env`、密钥、私有 URL、代理地址。
- 不提交原始运行数据、Mongo dump、上传材料。
- 不从历史目录整文件复制实现。
- 优先使用容器运行项目依赖；宿主机入口仅用于需要访问宿主机 Docker 的验证命令。
- 改 API 时同步 schema、测试和 `docs/api.md`。
- 改 AI 行为时同步 `docs/ai.md` 和相关测试。
- 改产品流程时先更新 `docs/prd.md`。
- 拆分后端模块前先阅读 `docs/backend-module-split.md`，并确认 `docs/api.md` 中的前端
  baseline 契约不变。

## PR 与合并规范

- 每个 PR 应聚焦一个 GitHub Issue 或一个明确维护切片，不混入无关重构、格式化或本地工具状态。
- CI 会在 `main`、`develop/**`、`feature/**`、`rescue/**` 分支 push，以及所有 PR 上运行。
- CI 的 typecheck/security/audit 扫描当前是 advisory job，用于暴露 mypy、bandit 和
  pip-audit 结果；归零前不作为必需门禁。
- PR 描述必须说明变更范围、验证证据、关联 issue，以及未运行检查的原因。
- 新建、重新打开、标记 ready for review 或更新 PR 后，如额度、环境和权限允许，应触发
  Codex 或 Copilot 至少一个 AI review。Codex 可以在 PR 中评论 `@codex review` 手动触发；
  Copilot 按 GitHub 官方流程从 Reviewers 菜单请求，或通过仓库设置启用自动 review。
- AI review 是建议性质量步骤，不作为合并阻塞项。Codex/Copilot 返回额度不足、环境未配置
  或无法审查时，记录现状即可，不应因此阻塞合并。
- 如果使用 AI review，合并前应确认该 PR 当前 head，也就是最后一发 commit，已经完成有效
  AI review。旧 commit 上的 review 不能作为新提交后的合并依据。
- 本仓库已在 PR #100 验证 `@codex review` 可用：`chatgpt-codex-connector` 会回复审查结果。
- 本仓库已在 PR #131 验证 Copilot PR review 可返回正式 review 和 inline comment；Copilot
  review 可能晚于其他检查完成，且 push 新提交后不会自动 re-review，不能只看 CI 绿就立即合并。
- AI review advisory 检查只记录当前 head 是否已有有效 AI review；没有有效结果时只给出
  warning，不作为必需检查失败。
- 机器人审查、人工审查和 CI 反馈必须逐条处理。已修复的评论必须先回复
  `已在 commit <hash> 修复：<根因和改法>`，不采纳的评论必须先回复
  `Rebuttal：<不采纳原因和风险判断>`。
- 不要直接 resolve review thread；必须先在对应 thread 回复修复 commit 或 rebuttal，再 resolve，
  方便后续追溯。
- 所有 PR review conversations 必须在合并前 resolve。未 resolve 的 review thread 视为阻塞合并；
  即使评论已 outdated，只要 GitHub 仍显示未 resolve，也需要手动 resolve。
- 如果 resolve review thread 后治理检查未自动重跑，在 GitHub Actions 中手动 rerun 对应检查，
  或 push 新提交触发检查重跑。
- 合并前必须确保必需检查通过，包括 CI 和 unresolved review thread 检查。
- 如果机器人 review 在 merge 后才到达，关联 issue 不应立即关闭；必须记录 follow-up 并处理完
  新增 review thread。
- 不要在 PR 评论里粘贴密钥、`.env` 内容、私有 URL、代理配置或未脱敏数据。

推荐分支保护或 ruleset 设置：

- 禁止直接 push 到主干分支，所有变更通过 PR 合并。
- 要求通过 CI 和 review conversation resolved 检查；AI review advisory 不设为必需检查。
- 要求所有 review conversations resolved。
- push 新提交后 dismiss stale reviews。
