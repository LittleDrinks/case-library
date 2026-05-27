# Claude Code 项目说明

本文件记录 Claude Code 专用项目说明。所有 AI 编码 agent 共享规范见 `AGENTS.md`。

## 开发环境

必须使用仓库内置 Dev Container 或 Docker Compose 容器执行开发、测试、lint、format、typecheck、构建和提交前验证。宿主机命令只用于只读排查，不能作为交付依据。

Dev Container 通过 Docker Compose 启动：

- `app`：FastAPI 后端
- `mongo`：MongoDB
- `frontend`：Vue/Vite 前端（当 `frontend/package.json` 存在时启用）

除非命令另有说明，默认在仓库根目录执行。最终交付检查必须在容器环境中完成。

## 常用检查

```bash
make check
make test
make compose-config
```

底层命令：

```bash
ruff check backend scripts
mypy backend
pytest
cd frontend && npm test
cd frontend && npm run build
docker compose config
```

## 项目结构

- `backend/`：FastAPI 后端。目标结构为 `backend/core/`，旧版入口为 `backend/main.py`。
- `frontend/`：Vue 3 + Vite 前端；旧版静态前端位于 `frontend/index.html`、`frontend/css/`、`frontend/js/`。
- `prompts/` 或 `skills/`：AI/prompt 相关资源。
- `tests/`：后端、契约和端到端测试。
- `docs/`：开发、质量、API、AI 和设计文档。

## 后端冻结

除非任务明确要求修改后端行为，否则将后端视为冻结状态。优先补充契约测试和窄范围修复，避免大范围重构。

当前后端类型检查基线是：

```bash
mypy backend
```


## AI 集成

修改 AI 配置、prompt 加载、响应解析或 LLM client 行为时，应同步更新 `docs/ai.md`。

不要提交真实服务凭据。私有配置应放在被忽略的 `.env` 文件中。
