# 贡献指南

感谢参与案例库项目建设。

## 开发环境

项目要求使用可复现的容器环境完成最终校验。推荐流程：

1. 安装 Docker 与 VS Code Dev Containers 扩展。
2. 用 VS Code 打开仓库根目录。
3. 执行 `Dev Containers: Reopen in Container`。

也可以直接使用 Docker Compose：

```bash
docker compose up -d
docker compose logs -f
```

## 本地密钥

不要提交 `.env`、API Key、数据库导出、本地 agent 状态或运行时产物。需要本地配置时，复制 `.env.example` 为 `.env`。

## 校验命令

提交 PR 前，根据改动范围运行对应检查。优先使用：

```bash
make check
make test
make compose-config
```

完整质量门禁：

```bash
ruff check backend scripts
mypy backend/core/config.py backend/core/logging_config.py
pytest
cd frontend && npm test
cd frontend && npm run build
docker compose config
```

如果仓库当前尚未包含某个目录或依赖，CI 会显式跳过对应检查；PR 描述中需要说明跳过原因。

## Pull Request 要求

- 改动聚焦单一问题。
- 新增必需环境变量时同步更新 `.env.example`。
- 修改公共接口时同步更新相关文档或契约测试。
- 行为变更有对应测试。
- 说明未能运行的检查及剩余风险。
