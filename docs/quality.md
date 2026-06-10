# 质量门禁

当前强制门禁由 Docker Compose 容器执行。本机没有完整项目运行环境，除纯文档检查外，
不要在宿主机直接运行项目依赖、测试或构建。

## 标准门禁

```bash
docker compose up -d --build
curl -fsS http://127.0.0.1:8001/api/constants
curl -fsS http://127.0.0.1:18080/
docker compose ps
docker compose run --rm app make check
docker compose config --quiet
git diff --check
```

`make check` 当前包含：

- `ruff check backend`
- 后端提交流测试或 `pytest`
- 前端依赖安装和 `npm run build`

## E2E

前端 Playwright smoke 也应在容器环境中运行；仅在已确认宿主机环境完整时才可临时
使用本机命令。

```bash
docker compose -f docker-compose.dev.yml --profile e2e run --rm e2e
```

容器化 E2E：

```bash
docker compose -f docker-compose.dev.yml up -d --build
docker compose -f docker-compose.dev.yml --profile e2e run --rm e2e
```

## 允许缩小门禁的情况

纯文档修改可只运行：

```bash
git diff --check
```

并在汇报中说明未运行完整 Compose 门禁。

## 扩展方向

- 为 PRD 目标补充版本化批注接口测试。
- 为 AI JSON contract 增加 schema 校验测试。
- 为公开案例“不展示批注”增加回归测试。
- 为前端批注页增加 Playwright 截图/交互测试。
