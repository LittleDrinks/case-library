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

等价的 make 入口：

```bash
make dev-e2e
```

该容器入口只运行 `frontend/tests/audit.spec.js`。`frontend/tests/smoke.spec.js` 会调用宿主机
`docker compose exec`，不能放进无 Docker daemon/socket 的 Playwright 容器执行。

完整 smoke E2E 入口：

```bash
make smoke-e2e
```

`make smoke-e2e` 会启动 dev compose，然后在宿主机运行完整 Playwright suite。若默认
compose 栈已在本机运行，请先 `docker compose down`，避免 `8001` / `18080` 端口冲突。

当前 `e2e` profile 的 `frontend/tests/audit.spec.js` 覆盖：

- `chromium-desktop`：默认管理员强制改密、创建流作者身份不读旧草稿、教师创建/AI
  自查/提交、教师历史版本、管理员版本化段落批注、退回修改后教师查看人工批注并复制
  版本再提交、管理员通过再提交版本、公开检索、案例库公开字段白名单、首页公开详情
  来源材料和内部审核信息不渲染。
- `chromium-mobile`：创建案例基本信息、案例内容、分类选择三个关键屏的可读性和截图。

当前矩阵中移动端只跑移动专属可读性测试；桌面专属验收流在移动项目中显式 skip。

## 允许缩小门禁的情况

纯文档修改可只运行：

```bash
git diff --check
```

并在汇报中说明未运行完整 Compose 门禁。

## 扩展方向

- 为 AI JSON contract 增加更严格的 schema 边界测试；当前已覆盖 disabled、
  parse_failed、invalid_contract 和主成功路径。
- 为前端批注页增加 Playwright 截图/交互测试。
