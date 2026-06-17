# AI 集成说明

AI 需求以 `docs/prd.md` 为准。本文记录实现边界、安全规则和当前状态。

## 当前实现

- 后端已有 OpenAI-compatible chat client。
- 配置来自 `.env`：`AI_BASE_URL`、`AI_API_KEY`、`AI_MODELS`、
  `AI_DEFAULT_MODEL`、`AI_TIMEOUT_SECONDS`、`AI_REVIEW_ENABLED`。
- `GET /api/prompts` 返回 prompt 元数据；元数据、配置和 markdown body 由
  `prompts/runtime/` 拥有，`backend/app/domains/ai/prompts/` 仅作为加载器和查询 API，
  不返回 prompt body。
- `POST /api/ai/chat` 在服务端调用模型，返回自然语言答案和可选 JSON 解析结果。
- `POST /api/cases/{case_id}/ai-review` 生成段落 `paragraph_id`，调用服务端模型，
  校验结构化 JSON，并创建绑定 AI 批注的只读版本快照。
- `POST /api/cases/{case_id}/ai-review` 的外部 API 仍是同步 POST；内部已拆成 request
  creation、prompt rendering、model call、parse、normalize/persist 的 service/job 边界，后续
  可接队列或复用存储而不改变当前响应契约。
- `prompts/` 保存案例编写、模板、分类和评测样例等产品领域资产；
  `.codex/skills`、个人 agent skills 或其他代理技能目录不得混入产品 prompt 资产。

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
- AI 段落批注优先要求 `paragraph_id`；后端兼容模型偶发输出的
  `paragraphId`、`paragraphID`、`paragraph` 别名，但只做字段名归一化，仍必须命中已生成的
  段落 ID，不会为缺失 ID 猜测段落。
- AI 文案不能承诺“已核实为真”或“审核通过”。

## Prompt 资产和评测状态

- 运行时 prompt 的元数据、配置和 markdown body 由 `prompts/runtime/` 管理；
  `backend/app/domains/ai/prompts/` 作为加载器和查询 API，继续提供 `/api/prompts` 和
  `/api/ai/chat` 使用的稳定 `prompt.id` 契约。
- `prompts/runtime/prompts.json` 中每条配置的 `asset_id` 映射到
  `prompts/runtime/<asset_id>/` 下的 `system.md` 和 `user.md`，不得把 `prompt.id`
  当作文件路径推断规则。
- 长文编写模板和参考材料归属 `prompts/case-writing/`，分类器规则归属
  `prompts/classification/`，评测样例随对应 prompt 资产目录保存；
  当前不会由后端动态加载，也不是完整 prompt CMS。
- 当前自动化覆盖重点是 prompt 注入边界：系统指令与用户 JSON 分离、未知变量过滤、
  prompt body 不经 `/api/prompts` 暴露。
- 轻量 prompt 评测 harness 可离线运行，不调用外部 AI、不需要 API key、不写入运行产物：
  `docker compose run --rm app python scripts/prompt_eval_harness.py`。本地已有 Python
  环境时也可运行 `python3 scripts/prompt_eval_harness.py`。可追加 prompt ID 只评测指定项，
  例如 `python3 scripts/prompt_eval_harness.py workflow/completeness alpha/paragraph-review`。
- 当前 harness 覆盖运行时 prompt 配置加载、本地 fixture 渲染、必填变量完整性、system/user
  body 分离，以及元数据不暴露 prompt body。

## 配置策略

- `AI_REVIEW_ENABLED=false` 时，AI 接口返回不可用状态。
- `model` 必须来自 `AI_MODELS`，未指定时使用 `AI_DEFAULT_MODEL`。
- 超时必须遵守 `AI_TIMEOUT_SECONDS`。
- AI review 错误分类保持稳定：`disabled`、`unconfigured`、`invalid_model`、
  `unavailable`、`parse_failed`、`invalid_contract`。
- 其他学校部署时，应替换 `.env` 和 `prompts/runtime/`，并保持稳定 prompt ID
  兼容，而不是在浏览器端拼接模型提示词。

## 真实 AI Smoke 安全

默认 `make check`、unit/integration tests 和 prompt eval harness 不调用真实模型，也不需要
`AI_API_KEY`。需要验证真实供应商连通性时，只能在本地或受控 CI 手动 opt-in：

- GitHub Actions 使用 `Real AI Smoke` 手动 workflow，且仅在 repository variable
  `REAL_AI_SMOKE_ENABLED=true` 时运行；pytest 入口使用 `real_ai` marker，常规单元门禁排除该 marker。
- 使用一次性测试 key 和测试 base URL，不复用生产 key。
- 显式设置 `AI_REVIEW_ENABLED=true`、`AI_BASE_URL`、`AI_API_KEY`、`AI_MODELS`、
  `AI_DEFAULT_MODEL`、`AI_TIMEOUT_SECONDS`。
- 只对测试库、测试账号和无敏感内容的案例运行 `POST /api/cases/{case_id}/ai-review`。
- 不把请求/响应全文、`.env`、私有 URL 或供应商 token 写入日志、截图、fixture 或 PR。
- smoke 结束后撤销或轮换测试 key；失败时只记录稳定错误分类和非敏感摘要。
