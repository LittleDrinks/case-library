# Dev Container

本目录适合提交到仓库并与协作者共享。配置通过仓库内的 Docker Compose 文件启动开发环境，并使用相对路径挂载代码，因此不同开发者可以在任意本地目录打开项目。

## 首次使用

1. 安装 Docker Desktop，或安装 Docker Engine 与 Compose plugin。
2. 安装 VS Code Dev Containers 扩展。
3. 用 VS Code 打开仓库根目录。
4. 执行 `Dev Containers: Reopen in Container`。

最终校验应在 Dev Container 或 Docker Compose 环境内完成。

端口：

- `8001`：FastAPI 后端和静态前端
- `18080`：Vue 3 / Vite 前端（宿主端口，可通过 `FRONTEND_PORT` 覆盖）
- `27017`：MongoDB（容器网络内）

Dev Container 的 `app` 镜像包含 Python、Node 20/npm、git 和 zsh。前端技术栈是 Vue 3 + Vite。

Dockerfile 默认使用国内 apt/pip/npm 镜像，可在本地 `.env` 中覆盖 `APT_MIRROR`、`APT_SECURITY_MIRROR`、`PIP_INDEX_URL` 和 `NPM_CONFIG_REGISTRY`。这些设置不影响 Docker 拉取基础镜像；如 `python:3.12-slim` 或 `node:20-bookworm-slim` 拉取很慢，需要单独配置宿主机 Docker daemon 的 registry mirror。

MongoDB 默认不发布到宿主端口，容器内部使用 `mongo:27017`。

## 本地密钥

不要提交 `.env`。需要本地配置时，复制 `.env.example` 为 `.env`，并只在被忽略的 `.env` 中填写私有配置。
