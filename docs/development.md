# 开发指南

## 容器环境

项目以 Dev Container / Docker Compose 作为一致开发环境。最终校验应在容器内执行。

```text
Dev Containers: Reopen in Container
```

服务：

- `app`：FastAPI 后端，访问 `http://localhost:8001`
- `frontend`：Vue/Vite 开发服务，访问 `http://localhost:5173`（当 `frontend/package.json` 存在时）
- `mongo`：MongoDB，容器网络地址 `mongo:27017`

默认不把 MongoDB 发布到宿主端口，避免与本机服务冲突。如确实需要宿主访问，可临时添加本地 override 或显式发布端口：

```bash
docker compose run --rm --service-ports mongo
```

## 常用命令

```bash
make install-dev
make check
make test
make compose-config
make up
make logs
make down
```

## 后端冻结

除非任务明确要求修改后端行为，否则后端按冻结状态处理。优先补充契约测试和窄范围修复，不做大范围重构。

当前执行的冻结类型检查基线是：

```bash
mypy backend/core/config.py backend/core/logging_config.py
```

如果目标文件尚未合入，CI 会显式跳过该项。
