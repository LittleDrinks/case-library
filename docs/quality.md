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
mypy backend/core/config.py backend/core/logging_config.py
pytest
cd frontend && npm test
cd frontend && npm run build
docker compose config
```

## 渐进启用策略

`develop/littledrinks` 是基础设施分支。为避免在前后端目标结构尚未合入时制造红灯，CI 会采用“存在即检查”策略：

- `backend/` 始终 lint。
- `scripts/` 存在时纳入 lint。
- `backend/core/config.py` 和 `backend/core/logging_config.py` 存在时启用冻结 mypy 基线。
- `scripts/check_exceptions.py` 先约束冻结基线文件，避免历史后端债务阻塞 infra 分支。
- `tests/` 存在时运行 `pytest`；否则运行旧版 smoke test。
- `frontend/package.json` 存在时运行 `npm test` 和 `npm run build`。

目标结构合入后，这些检查会自动变成强制门禁。

## 扩展门禁

后续可以逐步加入：

- `pip-audit` 或 Dependabot 依赖安全检查。
- Playwright 截图或 E2E 门禁。
- 全量 `mypy backend`。
- 更严格的 Ruff 规则收敛。

## 已知历史债务

旧版后端入口和脚本当前排除在全量 Ruff 之外，避免基础设施分支要求改写业务代码。相关文件包括 `backend/main.py`、`backend/database.py`、`backend/case_processor.py`、迁移脚本和旧运维脚本。迁移到 `backend/core/` 后，应逐步从 `pyproject.toml` 的 `extend-exclude` 中移除这些文件。
