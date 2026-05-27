# 质量基线

仓库质量门覆盖 lint、format、类型检查、后端测试、前端测试、构建和 Compose 配置校验。

## 当前强制检查

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

## 渐进启用策略

`develop/littledrinks` 是基础设施分支。质量门禁必须在容器内执行。前端采用“存在即检查”策略：

- `backend/` 始终全量 lint。
- `scripts/` 存在时纳入 lint。
- `mypy backend` 始终全量类型检查后端。
- `scripts/check_exceptions.py` 全量检查后端可疑异常处理。
- `tests/` 存在时运行 `pytest`；否则运行旧版 smoke test。
- `frontend/package.json` 存在时运行 `npm test` 和 `npm run build`。

目标结构合入后，这些检查会自动变成强制门禁。

## 扩展门禁

后续可以逐步加入：

- `pip-audit` 或 Dependabot 依赖安全检查。
- Playwright 截图或 E2E 门禁。
- 全量 `mypy backend`。
- 更严格的 Ruff 规则收敛。
