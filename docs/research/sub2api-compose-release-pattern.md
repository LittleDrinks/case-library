---
sources:
  - https://github.com/Wei-Shaw/sub2api/blob/aa2c4e8d136b13553ac7bae3d76c25715333a554/deploy/docker-compose.yml#L14-L326
  - https://github.com/Wei-Shaw/sub2api/blob/aa2c4e8d136b13553ac7bae3d76c25715333a554/Dockerfile#L1-L161
  - https://github.com/Wei-Shaw/sub2api/blob/aa2c4e8d136b13553ac7bae3d76c25715333a554/.github/workflows/release.yml#L1-L186
  - https://github.com/Wei-Shaw/sub2api/blob/aa2c4e8d136b13553ac7bae3d76c25715333a554/.goreleaser.yaml#L90-L169
  - https://github.com/Wei-Shaw/sub2api/blob/aa2c4e8d136b13553ac7bae3d76c25715333a554/README_CN.md#L294-L431
  - https://github.com/LittleDrinks/case-library/issues/34
---
# Sub2API Compose 与 GHCR 发布
## Sub2API
- Compose 编排 `sub2api`、`postgres`、`redis` 三个容器；只有 `weishaw/sub2api:latest` 是项目镜像，数据库与缓存使用上游 `postgres:18-alpine`、`redis:8-alpine`。
- 前端在构建阶段编入 Go 后端二进制，因此它只需发布一个自有应用镜像；这与 Case Library 的独立 Nginx 前端、Mongo 初始化器和带 secrets 入口点的 Meilisearch 镜像不同。
- 发布工作流由 `v*` 标签触发；GoReleaser 为一个 GHCR 仓库发布按架构拆分的镜像，再生成版本号和 `latest` 的多架构 manifest。
- Docker 部署的升级就是 `docker compose pull` 与 `docker compose up -d`；内置“在线更新”更新的是二进制发布包，不是 Compose 栈。
## #34 的发布边界
- 四个 GHCR 仓库不是运维负担：Compose 会按依赖关系拉取和替换，管理员不应逐个 `docker pull` 或选择四个 tag。
- 不能把四个镜像合成一个镜像。它们对应不同进程与生命周期；合并前后端会移除现有 Nginx 边界，合并初始化器会混淆一次性任务与常驻服务。
- 对外发布物应是一个版本化部署包：`compose.yaml`、`.env.example`、`update.sh`。Compose 的四个项目镜像全部使用同一 `vX.Y.Z-pre-alpha.N`，更稳妥的是在发布包中写为四个不可变 `@sha256` 引用。
- `latest` 保留为发现最新预发布的入口，但运行中的 Compose 不直接依赖四个 `:latest`；否则镜像陆续推送时可拉到混合版本。`update.sh` 先取得对应 Release 的部署包，再执行 `docker compose pull`、`up -d --wait` 和版本输出，命名卷保持不变。
- CI 顺序固定为：构建并验证四个镜像，推送同一版本 tag 与提交 SHA，生成包含四个 digest 的 Compose 发布包，最后发布/移动 `latest`。发布包成功出现才是这组镜像可升级的信号。
