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

当前环境中 Docker Hub 直连可能超时。若需要代理，应通过本机环境变量、Docker daemon
代理配置或团队约定的开发环境配置显式启用，不要把个人 shell 函数写入仓库配置。

```bash
curl -I --max-time 8 https://registry-1.docker.io/v2/
```

代理可用时，Docker Registry 应返回 `401 Unauthorized`，这是未登录 registry 的正常响应。

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

## PR 与合并规范

- 每个 PR 应聚焦一个 GitHub Issue 或一个明确维护切片，不混入无关重构、格式化或本地工具状态。
- PR 描述必须说明变更范围、验证证据、关联 issue，以及未运行检查的原因。
- 新建、重新打开、标记 ready for review 或更新 PR 后，如额度、环境和权限允许，应触发
  Codex 或 Copilot 至少一个 AI review。Codex 可以在 PR 中评论 `@codex review` 手动触发；
  Copilot 按 GitHub 官方流程从 Reviewers 菜单请求，或通过仓库设置启用自动 review。
- AI review 是建议性质量步骤，不作为合并阻塞项。Codex/Copilot 返回额度不足、环境未配置
  或无法审查时，记录现状即可，不应因此阻塞合并。
- 如果使用 AI review，合并前应确认该 PR 当前 head，也就是最后一发 commit，已经完成有效
  AI review。旧 commit 上的 review 不能作为新提交后的合并依据。
- 本仓库已在 PR #100 验证 `@codex review` 可用：`chatgpt-codex-connector` 会回复审查结果。
- 本仓库已在 PR #131 验证 Copilot PR review 可返回正式 review 和 inline comment；Copilot
  review 可能晚于其他检查完成，且 push 新提交后不会自动 re-review，不能只看 CI 绿就立即合并。
- AI review advisory 检查只记录当前 head 是否已有有效 AI review；没有有效结果时只给出
  warning，不作为必需检查失败。
- 机器人审查、人工审查和 CI 反馈必须逐条处理。已修复的评论必须先回复
  `已在 commit <hash> 修复：<根因和改法>`，不采纳的评论必须先回复
  `Rebuttal：<不采纳原因和风险判断>`。
- 不要直接 resolve review thread；必须先在对应 thread 回复修复 commit 或 rebuttal，再 resolve，
  方便后续追溯。
- 所有 PR review conversations 必须在合并前 resolve。未 resolve 的 review thread 视为阻塞合并；
  即使评论已 outdated，只要 GitHub 仍显示未 resolve，也需要手动 resolve。
- 如果 resolve review thread 后治理检查未自动重跑，在 GitHub Actions 中手动 rerun 对应检查，
  或 push 新提交触发检查重跑。
- 合并前必须确保必需检查通过，包括 CI 和 unresolved review thread 检查。
- 如果机器人 review 在 merge 后才到达，关联 issue 不应立即关闭；必须记录 follow-up 并处理完
  新增 review thread。
- 不要在 PR 评论里粘贴密钥、`.env` 内容、私有 URL、代理配置或未脱敏数据。

推荐分支保护或 ruleset 设置：

- 禁止直接 push 到主干分支，所有变更通过 PR 合并。
- 要求通过 CI 和 review conversation resolved 检查；AI review advisory 不设为必需检查。
- 要求所有 review conversations resolved。
- push 新提交后 dismiss stale reviews。
