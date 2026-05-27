# Dev Container

本目录适合提交到仓库并与协作者共享。配置通过仓库内的 Docker Compose 文件启动开发环境，并使用相对路径挂载代码，因此不同开发者可以在任意本地目录打开项目。

## 首次使用

1. 安装 Docker Desktop，或安装 Docker Engine 与 Compose plugin。
2. 安装 VS Code Dev Containers 扩展。
3. 用 VS Code 打开仓库根目录。
4. 执行 `Dev Containers: Reopen in Container`。

最终校验应在 Dev Container 或 Docker Compose 环境内完成。

端口：

- `8001`：FastAPI 后端
- `5173`：Vue/Vite 前端（当 `frontend/package.json` 存在时）
- `27017`：MongoDB（容器网络内）

MongoDB 默认不发布到宿主端口，容器内部使用 `mongo:27017`。

## 本地密钥

不要提交 `.env`。需要本地配置时，复制 `.env.example` 为 `.env`，并只在被忽略的 `.env` 中填写私有配置。
