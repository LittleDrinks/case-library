# AI Agent 协作规范

本文件是所有 AI 编码 agent 共享的项目约定。`CLAUDE.md` 只记录 Claude Code 专用补充说明；两者都适用时应同时遵守。

## 环境

- 默认在 Dev Container 或 `docker compose` 提供的一致环境内执行开发、测试和校验命令。
- 宿主机命令只作辅助排查；交付前的最终校验应在容器环境内完成，或说明无法进入容器的原因和剩余风险。
- 不要提交 `.env`、API Key、数据库导出、`.claude/`、`.codex/`、`.planning/` 等本地状态。

## 范围

- `.devcontainer/`、`Dockerfile`、`docker-compose.yml`、`docker-compose.override.yml`、`.github/`、`pyproject.toml`、`.pre-commit-config.yaml` 属于共享基础设施，应保持可复用。
- `CLAUDE.md` 可以跟踪，但内容应限于项目级约定，不应写入个人机器路径、私有代理或密钥。

## 改动纪律

- 用最小改动完成任务。
- 不重排、不改写、不移动无关代码。
- 未经明确要求，不删除用户工作或生成的规划产物。
- 前端大改前，先保持既有 API、store 和用户流程契约，并用测试验证。
- 后端当前按冻结状态处理；除非任务明确要求，不做大范围重构。

## 校验

交付前运行与改动范围匹配的检查。优先使用 `make` 目标：

```bash
make check
make test
make compose-config
```

等价底层命令：

```bash
ruff check backend scripts
mypy backend/core/config.py backend/core/logging_config.py
pytest
cd frontend && npm test
cd frontend && npm run build
docker compose config
```

如果某项检查因目录或依赖尚未合入而无法运行，需要明确说明跳过原因和剩余风险。

## 前端

- Vue 3 + Vite 代码位于 `frontend/`。
- 不要基于已知有问题的 UI 建立视觉回归基线。先稳定目标设计，再补截图测试。
- 视图层不要自行猜测 API 返回结构，应通过 API 层和 store 访问数据。

## 后端

- FastAPI 后端目标结构为 `backend/core/`；旧版入口为 `backend/main.py`。
- 新增必需环境变量时，同步更新 `.env.example`。
- 新增或修改接口时，优先补充显式契约测试。
