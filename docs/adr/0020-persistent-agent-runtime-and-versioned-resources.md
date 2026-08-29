# ADR 0020：持久化 Agent 闭环与版本化资源
AI 编辑由绑定作者和案例的服务端 Agent 闭环承载。Agent 模块拥有 Thread、Message、Run、Event 与 Artifact，Skill 模块拥有不可变 Skill 版本；MongoDB 保存对话真源，案例模块仍拥有正文、revision 与快照，检索模块仍拥有权限过滤后的 `search_corpus`。浏览器通过公开 Agent HTTP API 提交当前动作和订阅事件，不提交可信历史、不执行工具、不协调正文写入；断开只结束订阅，Run 持续到明确停止或终态。
进入模型上下文的系统指令、任务模板和 Skill 正文全部来自仓库内 UTF-8 Markdown。16 个上游 v2.1 文本资源仅保留为 source/reference 资源；运行时按公开清单读取标为可加载的资源，M1 只有平台适配的运行时 Skill 可加载，安装说明、模板和范例不得进入模型上下文。运行时记录资源标识与内容哈希，代码只负责选择资源、校验变量和组装非可信业务数据；不保留代码内完整提示词、数据库提示词、运行时 ZIP、外部路径或 Skill 脚本执行。Git 历史是资源修改记录，同一 Run 固定已解析版本。
模型只通过保留现有 URL、DNS、TLS、禁重定向和配额约束的 ModelAdapter 参与决策；工具 schema、权限和执行属于服务端。事件先持久化再流式投影，Artifact 只创建待确认结果；接受操作在一个 MongoDB 事务内完成校验、批前快照、正文变换、revision 递增、决定和事件写入，并以 Artifact ID 幂等。
编辑 Agent 与检索摘要分别使用所属模块的窄接口和 Markdown 提示词。闭环切换后删除通用 `/api/ai/chat`、浏览器本地消息真源、自由文本候选解析和伪工具，不保留兼容路径。
公开 Agent API 是主要测试边界：真实 FastAPI、MongoDB 副本集、案例、快照与检索配合确定性 ModelAdapter；替身必须产生真实工具调用和结构化产物，不能直接伪造最终业务状态。Playwright 复用同一累计 tracer 验证用户可见闭环。另设显式真实模型 E2E，在隔离测试数据上执行同一路径并接受一次产物，只断言工具、结构、来源、状态和 revision，不断言生成措辞；它不替代确定性提交门禁。
