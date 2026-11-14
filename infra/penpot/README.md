# 本地 Penpot

基于 [Penpot 2.19.1 官方 Compose](https://github.com/penpot/penpot/blob/2.19.1/docker/images/docker-compose.yaml)，使用独立容器、网络和数据卷。Penpot 五个服务共用 `.env` 中的 `PENPOT_VERSION`；PostgreSQL、Valkey、Mailpit 在 Compose 中固定完整版本。

## 打开

在 VS Code 远程窗口的 **端口 / Ports** 面板添加 `9001`，然后打开 <http://localhost:9001>。如果本机端口已被占用，以面板显示的转发地址为准。服务器只监听 `127.0.0.1:9001`。

初始账号保存在本机 `deploy/penpot/.local/account.json`，可从 VS Code 文件树打开。`.local/`、`.env` 和 MCP 凭据均被 Git 忽略。公开注册已关闭。

## 启停与首次安装

可复用配置位于 `infra/penpot`；本机部署、凭据与备份放在 Git 忽略的 `deploy/penpot`。首次部署先在仓库根目录复制模板，已有部署无需重复复制：

```sh
mkdir -p deploy/penpot
cp infra/penpot/compose.yaml infra/penpot/backup.sh infra/penpot/.env.example deploy/penpot/
```

以下命令在 `deploy/penpot` 目录运行：

```sh
docker compose --env-file .env -f compose.yaml up -d
docker compose --env-file .env -f compose.yaml ps
docker compose --env-file .env -f compose.yaml stop
```

新服务器先复制 `.env.example` 为 `.env`，分别为 `PENPOT_SECRET_KEY` 和 `PENPOT_DATABASE_PASSWORD` 生成随机值，例如运行两次 `python3 -c 'import secrets; print(secrets.token_urlsafe(48))'`，再执行 `chmod 600 .env`。启动后使用官方交互命令创建账号：

```sh
docker compose --env-file .env -f compose.yaml exec penpot-backend python3 manage.py create-profile
```

`up -d` 返回时后端可能仍在启动。等待以下请求返回 HTTP 200，再登录：

```sh
curl -o /dev/null -sS -w '%{http_code}\n' http://127.0.0.1:9001/api/main/methods/get-profile
```

在项目列表点击“导入文件”，选择 `design/case-library.penpot`。仓库快照含 18 个页面和 184 个组件。导入另一实例后文件 ID 会改变；使用 [Penpot 链接迁移命令](../../tools/penpot/README.md#更换原型链接的站点) 更新原型中的站点和原文件 ID。

## MCP

本地实例已启用官方 MCP。登录后，在设计文件菜单中连接 MCP，按界面提供的地址配置仓库忽略的 `.codex/config.toml`；客户端用法见 [Penpot 工具](../../tools/penpot/README.md)。

2.19.1 的 MCP 仍需要一个打开设计文件并连接插件的浏览器页面。自部署移除了对官方托管服务的依赖，但服务容器本身不代替浏览器。自动化使用服务器浏览器时，应保持该页面连接，并避免同一账号在另一个页面重复连接 MCP。

## 备份与更新

```sh
bash backup.sh
```

备份会短暂停止编辑入口和写入服务，将数据库、附件、版本配置和密钥一起保存到 `.local/backups/<时间>/`，随后重新启动。备份目录包含凭据，应整体复制到可信位置保管。脚本检查数据库目录和压缩包可读取；这不等同于完成恢复演练。

更新时先备份，再阅读目标版本的 [升级说明](https://help.penpot.app/technical-guide/getting-started/docker/#update-penpot)，修改 `.env` 的 `PENPOT_VERSION`，执行：

```sh
docker compose --env-file .env -f compose.yaml pull
docker compose --env-file .env -f compose.yaml up -d
```

升级后验证登录、打开文件、保存设计和 MCP。数据库发生迁移后，回退需要配套恢复升级前的数据库、附件和配置，不能只修改镜像版本。日常停止服务使用 `stop`，保留数据卷。

邮件进入本地 Mailpit，不会发往外部邮箱。当前入口通过 SSH 转发使用 HTTP；如需公网域名，另行配置 HTTPS 和安全 Cookie。
