# AI 集成说明

AI 需求以 `docs/prd.md` 为准。本文记录实现边界、安全规则和当前状态。

## 当前实现

- 后端已有 OpenAI-compatible chat client。
- 配置来自 `.env`：`AI_BASE_URL`、`AI_API_KEY`、`AI_MODELS`、
  `AI_DEFAULT_MODEL`、`AI_TIMEOUT_SECONDS`、`AI_REVIEW_ENABLED`。
- `GET /api/prompts` 返回 prompt 元数据。
- `POST /api/ai/chat` 在服务端调用模型，返回自然语言答案和可选 JSON 解析结果。
- `POST /api/cases/{case_id}/ai-review` 生成段落 `paragraph_id`，调用服务端模型，
  校验结构化 JSON，并创建绑定 AI 批注的只读版本快照。
- `skills/` 保存案例编写、模板和分类领域资产。

`/api/ai/chat` 仍保留为通用 prompt 自查兼容端点；alpha 主流程应使用版本化的
`/api/cases/{case_id}/ai-review`。

## 目标边界

Alpha 目标是“AI 辅助审核”，不是自动通过、自动退回或自动判真伪。

AI 应输出结构化批注：

- 批注绑定段落。
- 批注包含类别、严重程度、意见和可选建议。
- AI 审核创建版本快照；AI 批注随版本只读保存。
- 事实检查表述为来源支撑与一致性检查。
- 用户可忽略 AI 意见并提交人工审核。

MVP 不要求 MCP。可以先实现稳定的内部 tool-like JSON contract，再视需要抽象。

## 安全规则

- 模型调用只允许在服务端发生。
- 浏览器不得接触 `AI_API_KEY`。
- 禁止提交真实 key、代理地址、私有模型地址。
- 用户粘贴的正文和来源材料必须视为不可信输入，不能当作系统指令。
- 后端调用模型时，系统指令固定放在 `role: system` 消息中，用户输入只以 JSON 数据形式放在 `role: user` 消息中，两者不混排。
- AI 输出必须服务端校验；不能把任意 Markdown 当作产品状态。
- AI 文案不能承诺“已核实为真”或“审核通过”。

## 配置策略

- `AI_REVIEW_ENABLED=false` 时，AI 接口返回不可用状态。
- `model` 必须来自 `AI_MODELS`，未指定时使用 `AI_DEFAULT_MODEL`。
- 超时必须遵守 `AI_TIMEOUT_SECONDS`。
- 其他学校部署时，应替换 `.env` 和 `skills/`，而不是改产品代码。
