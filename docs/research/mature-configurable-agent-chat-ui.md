---
sources:
  - name: OpenAI ChatKit and Responses
    urls:
      - https://openai.github.io/chatkit-python/concepts/threads/
      - https://openai.github.io/chatkit-python/concepts/actions/
      - https://openai.github.io/chatkit-python/guides/prepare-your-app-for-production/
      - https://developers.openai.com/api/docs/guides/conversation-state
      - https://developers.openai.com/api/docs/guides/function-calling
  - name: ChatGPT activity interface
    urls:
      - https://cdn.openai.com/pdf/b96a6047-53b2-43bd-85b9-44885cf4007a%20/chatgpt-enterprise-prompt-pack-for-financial-services.pdf
  - name: OpenAI Agents SDK
    urls:
      - https://openai.github.io/openai-agents-js/guides/sessions/
      - https://openai.github.io/openai-agents-js/guides/human-in-the-loop/
      - https://openai.github.io/openai-agents-js/guides/streaming/
  - name: Vercel AI SDK
    urls:
      - https://ai-sdk.dev/docs/reference/ai-sdk-ui/use-chat
      - https://ai-sdk.dev/docs/reference/ai-sdk-core/ui-message
      - https://ai-sdk.dev/docs/ai-sdk-ui/chatbot-tool-usage
      - https://ai-sdk.dev/docs/ai-sdk-ui/chatbot-message-persistence
      - https://ai-sdk.dev/docs/ai-sdk-ui/chatbot-resume-streams
      - https://ai-sdk.dev/docs/ai-sdk-ui/stream-protocol
  - name: Open WebUI
    urls:
      - https://docs.openwebui.com/features/workspace/
      - https://docs.openwebui.com/features/extensibility/plugin/tools/
      - https://docs.openwebui.com/getting-started/advanced-topics/hardening/
      - https://docs.openwebui.com/features/authentication-access/rbac/permissions/
  - name: LibreChat
    urls:
      - https://github.com/danny-avila/LibreChat/blob/main/packages/data-provider/src/config.ts
      - https://github.com/danny-avila/LibreChat/blob/main/packages/api/src/agents/run.ts
  - name: Visual Studio Code chat context
    urls:
      - https://code.visualstudio.com/docs/chat/copilot-chat-context
      - https://code.visualstudio.com/updates/v1_95
---
# 成熟可配置 Agent 对话工作台
## 已确认的 Vue 选择
仓库此前选的是 [`@ai-sdk/vue` 的 `useChat`](https://github.com/vercel/ai/blob/main/packages/vue/src/use-chat.ts)，[`frontend/package.json`](../../frontend/package.json)已将其纳入依赖。它提供响应式会话状态、消息流和 transport，`UIMessage` 的 `parts[]` 是渲染输入；它不是带聊天室、联系人、消息气泡的成品界面。[Vercel `useChat` 文档](https://ai-sdk.dev/docs/reference/ai-sdk-ui/use-chat) [`UIMessage` 源码](https://github.com/vercel/ai/blob/main/packages/ai/src/ui/ui-messages.ts)
`vue-advanced-chat` 没有被此前方案选用，也未出现在当前依赖中；其维护者已将主线迁为 Advanced Chat Components，旧包仍是 `vue-advanced-chat@2.1.2`。该项目提供房间、消息、文件、反应、回复等通用 Vue 3 聊天 UI，且明确把 transport、持久化、授权、上传与重试留给宿主应用，适合一般 IM 外壳，不替代 Agent 的运行态、工具审批或服务端真源。[第一方 README](https://github.com/advanced-chat/advanced-chat-components)
## 可验证事实
| 领域 | 成熟实现的事实 | 一手依据 |
| --- | --- | --- |
| 对话界面与线程 | ChatKit 将 Thread 定义为有序时间线，包含消息、组件、动作、内部信号与元数据；Store 持久化 Thread，加载历史时由同一批 item 重新渲染。Assistant item 可含 Markdown、工具输出、widget 和注释。 | [Threads and items](https://openai.github.io/chatkit-python/concepts/threads/) |
| Thinking 与活动 | ChatGPT 官方界面样例在主对话中将完成态压缩为 `Thought for 18s`，来源紧随其后；Activity 视图以时间线列出检索、阶段说明和完成耗时。公开材料未规定运行态的 CSS 或关键帧。 | ChatGPT activity interface |
| 输入上下文 | VS Code Chat 将当前选区作为隐式上下文，也允许通过统一的 Add Context 选择器同时添加文件、文件夹、符号、图片、网页和其他上下文；每项上下文可独立管理。 | Visual Studio Code chat context |
| UI 动作 | ChatKit 的 widget action 带类型化 payload；默认交给服务端，影响线程或启动 Agent 的动作必须在服务端处理，payload 在落库前须校验并授权。 | [Actions](https://openai.github.io/chatkit-python/concepts/actions/) |
| 消息与 trace | Vercel `UIMessage` 以 `id`、`role`、可选 metadata 和 `parts[]` 表达一条消息；`useChat` 暴露 `submitted`、`streaming`、`ready`、`error` 状态及 `sendMessage`、`regenerate`、`stop`、`resumeStream`。 | [`UIMessage`](https://ai-sdk.dev/docs/reference/ai-sdk-core/ui-message) [`useChat`](https://ai-sdk.dev/docs/reference/ai-sdk-ui/use-chat) |
| 工具审批 | AI SDK 的敏感工具可声明 `needsApproval`；首次模型调用返回 `tool-approval-request`，提交 `tool-approval-response` 后第二次调用才执行或告知拒绝。OpenAI Agents SDK 也以可序列化 `RunState` 暂停、批准或拒绝后从同一状态恢复。 | [AI SDK approvals](https://ai-sdk.dev/docs/ai-sdk-ui/chatbot-tool-usage) [Agents SDK HITL](https://openai.github.io/openai-agents-js/guides/human-in-the-loop/) |
| 模型与工具状态 | Responses API 的 `conversation` 可关联多轮 item；响应输出是有序 item，而非只取一段助手文本。工具集可包含内置、MCP 与带 schema 的自定义函数，`tool_choice` 可限制或要求调用。 | [Conversation state](https://developers.openai.com/api/docs/guides/conversation-state) [Responses create](https://developers.openai.com/api/reference/cli/resources/responses/methods/create) |
| 技能、知识与工具目录 | Open WebUI Workspace 将 Model、Knowledge、Prompt、Skill、Tool 分为独立资源，再组合成可复用模型预设；其内置文件工具在读取前重新检查用户访问权，检索块可渲染为 citation。 | [Workspace](https://docs.openwebui.com/features/workspace/) [Tools](https://docs.openwebui.com/features/extensibility/plugin/tools/) [citation renderer](https://github.com/open-webui/open-webui/blob/d3e8bf3405e848cfba377814d0aa7ba7290e414d/src/lib/components/chat/Messages/Citations.svelte) |
| 配置安全边界 | Open WebUI 明确将 Tool/Function 视为与后端进程同权的任意 Python 代码，默认只允许管理员管理；可通过 RBAC、禁用插件和 Safe Mode 收紧。LibreChat 的当前配置源码也将 `allow`、`deny`、`ask` 审批策略与可持久化的 Mongo checkpoint 分开，供跨重启、跨副本恢复暂停的 HITL 运行。 | [Open WebUI hardening](https://docs.openwebui.com/getting-started/advanced-topics/hardening/) [Open WebUI permissions](https://docs.openwebui.com/features/authentication-access/rbac/permissions/) [Open WebUI approval](https://github.com/open-webui/open-webui/blob/d3e8bf3405e848cfba377814d0aa7ba7290e414d/backend/open_webui/utils/tool_approval.py) [LibreChat policy](https://github.com/danny-avila/LibreChat/blob/main/packages/data-provider/src/config.ts) [LibreChat run seam](https://github.com/danny-avila/LibreChat/blob/main/packages/api/src/agents/run.ts) |
| 断线、恢复与停止 | AI SDK 的消息持久化建议保存 UIMessage 并在含工具、metadata 或 data part 时验证；流恢复需要应用自建 active-stream 存储和 POST/GET 端点。其文档明确指出 `resume` 与 abort 不能同时使用。Agents SDK 流应消费到完成，取消后可从 `RunState` 继续同一 turn。 | [Message persistence](https://ai-sdk.dev/docs/ai-sdk-ui/chatbot-message-persistence) [Resume streams](https://ai-sdk.dev/docs/ai-sdk-ui/chatbot-resume-streams) [Agents streaming](https://openai.github.io/openai-agents-js/guides/streaming/) |
| 前后端协议 | AI SDK UI stream protocol 为自定义后端保留兼容面，文档直接以 FastAPI 为例；ChatKit 生产指南要求每个端点请求认证、按自身用户/租户模型授权 Thread 与附件、工具前验证输入，并避免把原始消息或工具参数整体写入遥测。 | [AI SDK stream protocol](https://ai-sdk.dev/docs/ai-sdk-ui/stream-protocol) [ChatKit production](https://openai.github.io/chatkit-python/guides/prepare-your-app-for-production/) |
## 可复用推断
以下是从上述事实归纳的工作台模式，不构成产品或架构决定。
| 目标 | 可复用模式 |
| --- | --- |
| 规范状态 | 分开保存 `thread`、`message(parts[])`、`run`、`event(seq,type,payload)`、`tool_call(callId,input,status,decision,result)`、`source` 与 `artifact`；浏览器中的流状态只是这些记录的投影。Thread 解决历史导航，Run 解决一次可中断执行，Event 解决 trace/replay，Artifact 解决待接受的业务结果。 |
| 已批准能力与用户选择 | 管理端维护可审查的 Skill/Tool/Model/Knowledge 目录、版本、风险级别和授权规则；用户只能在本次 Thread/Run 中选择已授权的条目、资料范围或审批决定。不能让用户配置任意工具代码、任意 MCP 地址或服务端密钥；任何客户端选择、工具参数、审批响应都在执行时按当前身份和资源再次验证。 |
| 工作台 UI | 输入区承接意图与允许范围；对话区按 part 渲染文本、引用、文件、工具申请、工具进度、结果、错误和待确认产物；工具 trace 默认折叠但可展开到调用名、经脱敏的输入摘要、状态、来源与结果。写入性结果放入独立候选/产物卡，不能伪装成已完成的正文修改。 |
| 活动动效 | 主对话只突出当前阶段：运行态使用低幅文字光泽、呼吸点和阶段淡入，完成后折叠为耗时摘要；不用伪造确定性进度条。Skill、Thinking 与 Tool 共享一条活动时间线，修订产物保持独立。 |
| 多上下文输入 | 输入上下文是有类型、有稳定标识、可逐项移除的 attachment 列表；正文可同时附加多个选区，平台资料和本地附件通过同一个添加入口进入。Skill 选择与上下文附件分开。 |
| 来源与产物 | Source 保存可追溯标识、标题、URL 或内部资源版本、摘录范围、访问控制和取得时间；Artifact 保存结构化内容、来源引用、关联 Run 与决定状态。模型文本中的链接不能替代 Source；工具返回的文件、图片或 citation 应通过受控 ID/下载入口呈现。 |
| 恢复与取消 | 断开浏览器只结束订阅，不能直接推断 Run 已取消。服务端应为 cancel、approval、retry、replay 定义各自的幂等请求；恢复使用 Run 身份和事件位置补投，而不是凭浏览器残存消息重跑。是否支持「停止后恢复同一 Run」应先与底层流协议的 abort/resume 语义对齐。 |
| 前后端分工 | 前端只提交新意图、已选的受权能力、显示状态和发出用户决定；后端从可信 Thread/资源目录重建模型输入，执行业务工具，持久化事件和最终状态。模型、工具、持久化、权限和副作用均不以浏览器的历史、part 或 status 为授权事实。 |
## 测试边界
以下为推断出的验证策略。单元测试覆盖 part reducer、工具状态机、批准/拒绝、来源与产物 schema、事件去重和权限决策；HTTP 集成测试覆盖真实持久化、刷新后重建、从指定事件位置回放、取消、重试、同一请求幂等和跨用户拒绝。浏览器 E2E 应验证用户可见的完整链路：选择已批准能力、看到实际工具调用与来源、处理批准、查看/接受或拒绝产物、刷新后仍能恢复；不得以伪造最终消息替代工具、授权、事件和持久化。对所有来自浏览器的 `parts[]`、审批和动作 payload 进行服务端负向测试，符合 ChatKit 与 AI SDK 对动作/持久化验证的边界；AI SDK 自身也在 Vue hook 与底层 Chat 上保留独立测试。[ChatKit actions](https://openai.github.io/chatkit-python/concepts/actions/) [AI SDK persistence validation](https://ai-sdk.dev/docs/ai-sdk-ui/chatbot-message-persistence) [Vue test](https://github.com/vercel/ai/blob/main/packages/vue/src/chat.vue.ui.test.tsx) [Chat test](https://github.com/vercel/ai/blob/main/packages/ai/src/ui/chat.test.ts)
