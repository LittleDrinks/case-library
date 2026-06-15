# AI 协作规范

本文件用于声明本仓库通用的 AI 协作规范，适用于所有 AI 编程助手和自动化写作者。
本文件只记录项目级共识，不记录个人开发习惯、本地工具配置、临时 handoff 或运行状态。

如需为某个具体助手补充额外规范，请添加或更新对应的专属文件，例如 `CLAUDE.md`；
不要把个人工作流、窗口管理器、代理、shell 函数或本地路径写入 `AGENTS.md`。

## 信息来源

- 产品需求和前端体验约束：`docs/prd.md`
- 项目架构、环境、质量门禁和工程事实：`docs/project.md`
- API 说明：`docs/api.md`
- AI 行为约束：`docs/ai.md`
- 开发、验证和 PR 流程：`docs/development.md`
- 看板索引：`docs/kanban.md`
- 具体任务详情和状态：GitHub Issues

同一个事实只维护在一个地方。若事实已有归属文档，应链接到该文档，不要复制粘贴到
多个文件中。

## 工作边界

- 一次只处理一个 GitHub Issue 或一个明确的维护切片。
- 使用聚焦分支，保持 PR 小而可审查。
- 不把临时提示词、运行日志、截图、审查草稿、worker 输出或本地工具状态提交到仓库。
- 不从旧目录、其他项目或外部代码库整文件复制实现；需要复用时先理解行为，再在当前
  代码结构中实现。
- 未经明确要求，不做无关重构、格式化、依赖升级或目录搬迁。

## 密钥与数据

- 不打印、提交或暴露 `.env`、API Key、私有 URL、代理配置、账号表、Mongo dump、上传
  材料、浏览器会话或 private token。
- `.env.example` 只能包含配置名和非敏感示例。
- 产品 AI 调用必须经过后端；浏览器端不得接收模型供应商凭据。
- 原始运行数据、上传材料和数据库导出不得进入 git，除非已经转化为经过审查的 fixture
  或文档。

## 代码与文档

- 遵循现有架构、命名、样式和测试组织方式。
- 改 API 时同步 schema、测试和 `docs/api.md`。
- 改 AI 行为时同步 `docs/ai.md` 和相关测试。
- 改产品流程时先同步 `docs/prd.md`。
- 改开发流程、验证命令或 PR 规则时同步 `docs/development.md`。
- 文档默认使用中文，除非文件本身已有明确的英文约定。

## 验证

实现或脚手架变更完成前，运行 `docs/project.md` 中的质量门禁，或说明为什么只运行了
更小的检查子集。文档小改通常至少运行：

```bash
git diff --check
```

## PR 规范

- 每个 PR 说明变更范围、关联 issue、验证证据和未运行检查的原因。
- PR 合并前必须处理所有 CI、已产生的 AI review、人工 review 和 review conversation。
- 未 resolve 的 review thread 视为阻塞合并。
- 具体 PR 流程和分支保护建议见 `docs/development.md`。
