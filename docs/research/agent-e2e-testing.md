---
sources:
  - product: Vercel AI SDK
    urls:
      - https://ai-sdk.dev/docs/ai-sdk-core/testing
      - https://ai-sdk.dev/docs/ai-sdk-ui/chatbot-message-persistence
      - https://ai-sdk.dev/docs/ai-sdk-ui/chatbot-resume-streams
  - product: Playwright
    urls:
      - https://playwright.dev/docs/best-practices
      - https://playwright.dev/docs/api/class-apirequestcontext
  - product: FastAPI
    urls:
      - https://fastapi.tiangolo.com/advanced/async-tests/
  - product: MongoDB
    urls:
      - https://www.mongodb.com/docs/manual/core/transactions/
      - https://www.mongodb.com/docs/manual/core/write-operations-atomicity/
---
# Agent 端到端测试
## 结论
1. 回归测试不调用真实模型。AI SDK 官方提供 mock model 与可控流式输出，适合稳定产生文本、工具调用、延迟和异常；替身止于 ModelAdapter，FastAPI、MongoDB、案例、检索和工具执行保持真实。
2. Playwright 只断言教师可见行为和公开 HTTP 契约，使用角色、标签和可访问名称定位；每个场景拥有独立案例和线程，不共享执行顺序。
3. Artifact 接受涉及多个文档，必须在真实 MongoDB 副本集上验证事务与幂等。`mongomock` 只用于局部测试，不能作为原子性证据。
4. API 集成测试使用异步 HTTP 客户端并直接核对持久化结果；浏览器 E2E 不承担全部状态组合。真实供应商放在显式验收命令中，复用隔离 E2E 基础设施并接受一次产物，但不作为每次提交的确定性门禁。
5. Skill 资源契约是公开清单：16 个上游 v2.1 文本资源标为 source/reference 且不可加载，唯一可加载资源是平台适配的 M1 Skill；测试按清单枚举实际文件、解码 UTF-8 并核对原始字节哈希。
## 累计 tracer
| 阶段 | 操作 | 可观察结果 |
| --- | --- | --- |
| 准备 | 作者打开一个工作版本并启用固定 Skill | 显示 Skill 名称与版本，刷新仍存在 |
| 收集 | 依次填写选题、角度、受众 | 缺项期间模型和工具调用均为 0 |
| 执行 | 选择一个段落并提交修订要求 | fake model 发出 `search_corpus` 调用，界面显示查询、状态和来源 |
| 产物 | 工具结果返回后生成单段待确认修订 | 原文、新文、理由、来源可见，正文与 revision 不变 |
| 决定 | 教师接受 Artifact | 服务端创建批前快照，正文只变化一次，revision 只增加 1 |
| 恢复 | 刷新并从最后事件位置重连 | 同一 Thread、Run、来源、Artifact 和决定恢复且不重复 |
## 测试分层
| 层 | 真实部分 | 替换部分 | 主要断言 |
| --- | --- | --- | --- |
| 组件 | Vue parts renderer 与交互 | 服务端状态夹具 | 文本、工具、来源、产物、错误和移动抽屉映射 |
| Agent API | FastAPI、MongoDB 副本集、案例、检索、快照 | ModelAdapter | 幂等、事务、权限、事件重放、取消、失败恢复 |
| Playwright | 完整浏览器与全部第一方服务 | 确定性模型供应商 | 累计 tracer、刷新、断线、390px、跨用户阻断 |
| provider smoke | 受限 ModelAdapter 与真实供应商 | 无 | 最小请求可连通，不泄露密钥、提示词或正文 |
| live Agent E2E | 浏览器、全部第一方服务与真实供应商 | 无 | 真实工具调用、pending Artifact、接受、刷新和一次 revision |
## 命令与凭据
- `make e2e` 是提交门禁，使用确定性模型供应商，不读取本机 `.env` 的模型密钥。
- `make agent-live-e2e` 是显式真实验收，要求 `.env` 已配置 `AI_BASE_URL`、`AI_API_KEY`、`AI_MODELS` 和 `AI_DEFAULT_MODEL`；缺项立即失败，不条件跳过。
- `agent-live-e2e` 将密钥作为 Docker secret 文件注入隔离 Agent 服务，不把值放入命令参数、普通环境输出、测试报告、trace 或截图。
- 真实验收创建唯一测试案例和 Thread，固定检索资料与目标段落，结束后删除本次资源；清理失败使命令失败。
- 真实模型只断言其调用合法 `search_corpus`、返回符合 schema 的 Artifact 且来源可见。正文内容只断言非空、不同于原文并能通过服务端变换，不做字面匹配或主观质量打分。
## 必测故障
- 同一 `clientRequestId` 重发只创建一次消息和 Run；同一 Artifact 重复接受只增加一次 revision。
- SSE 订阅断开后 Run 继续；按事件序号重连无缺失、无重复；显式停止最终进入 `cancelled`。
- 工具超时、目录 503、模型中断和接受事务失败留下稳定失败状态，案例与 Artifact 不出现分裂写入。
- 非作者不能读取线程、来源或决定 Artifact；冻结或已发布案例不能启动运行或接受修订。
- 手工编辑导致 `baseRevision` 过期时返回冲突，候选不覆盖新正文。
## 不采用
- 不在 Playwright 中 mock `/api/agent/*`，否则不能证明持久化、权限、事件和事务闭环。
- 不把完整模型回复直接写成 Artifact fixture，必须经过工具 schema 和服务端产物创建路径。
- 不用重试掩盖竞态，不依赖固定 sleep，不提交永久跳过的核心场景。
