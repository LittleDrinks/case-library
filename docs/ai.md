# AI 集成说明

本项目的 AI 相关配置和 prompt 资源应保持可审计、可复现、无私密凭据。

## 约定

- 不提交真实 API Key、代理地址、私有服务 URL 或个人机器路径。
- AI 服务配置通过 `.env` 注入，并在 `.env.example` 中提供非敏感示例。
- 修改 prompt、响应解析、LLM client 或 AI 路由时，同步更新本文档和相关测试。

## Agent 协作

- 所有 AI agent 先读 `AGENTS.md`。
- Claude Code 额外读取 `CLAUDE.md`。
- 本地规划状态如 `.planning/` 不提交到仓库。
- agent 产物进入仓库前必须被当作普通代码审查：检查范围、密钥、可复现性和测试。
