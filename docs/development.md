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

当前环境中 Docker Hub 直连可能超时。可使用 `~/.zshrc` 中的代理函数：

```bash
zsh -lic 'proxy_on'
```

该函数会写 `/etc/docker/proxy.env` 并可能重启 Docker，需要权限。代理可用时，
Docker Registry 应返回 `401 Unauthorized`，这是未登录 registry 的正常响应。

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

## 前端依赖异常

如果 Vite 或 node_modules 损坏，只重置前端依赖卷：

```bash
docker compose stop frontend
docker volume rm case-library_frontend_node_modules
docker compose up -d frontend
```

## 开发约束

- 不提交 `.env`、密钥、私有 URL、代理地址。
- 不提交原始运行数据、Mongo dump、上传材料。
- 不从历史目录整文件复制实现。
- 不在宿主机安装或运行项目依赖；使用容器。
- 改 API 时同步 schema、测试和 `docs/api.md`。
- 改 AI 行为时同步 `docs/ai.md` 和相关测试。
- 改产品流程时先更新 `docs/prd.md`。
