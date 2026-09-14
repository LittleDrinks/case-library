---
sources:
  repository: https://github.com/ckeditor/ckeditor5
  pinned_commit: 27f01f0c2af03e034dbdf185c802f4e383dd16a8
  chat: https://ckeditor.com/docs/ckeditor5/latest/features/ai/ckeditor-ai-chat.html
  quick_actions: https://ckeditor.com/docs/ckeditor5/latest/features/ai/ckeditor-ai-actions.html
  integration: https://ckeditor.com/docs/ckeditor5/latest/features/ai/ckeditor-ai-integration.html
  programmatic: https://ckeditor.com/docs/ckeditor5/latest/features/ai/ckeditor-ai-programmatic.html
  licensing: https://ckeditor.com/docs/ckeditor5/latest/getting-started/licensing/license-and-legal.html
  browser_evidence: /home/q2635/wsl-workspace/case-library-v2/.scratch/m1-285-uat/ckeditor-deep-dive/
  local_evidence: /home/q2635/wsl-workspace/case-library-v2/.scratch/m1-285-uat/ckeditor-deep/source-logs
---
# CKEditor 交互机制与案例库映射
## 证据边界
公开源码固定在 `27f01f0c2af03e034dbdf185c802f4e383dd16a8`。该提交的工具栏、浮层、编辑模型代码可直接核查；源码快照不等于用户正在使用的在线演示构建。AI、批注和 Track Changes 在官方集成文档中作为 premium 功能提供；本次公开仓库没有 `packages/ckeditor5-ai`，只核查官方 API、配置示例和公开变更记录，没有下载商业包或查看私有实现。主仓的 Tiptap/Vue 代码仅用于复用映射，没有替换编辑器的决定。
| 用户观察 | 证据强度 | 核查结论 |
| --- | --- | --- |
| 划词浮动工具栏 | 用户截图＋公开实现 | 有选择稳定、焦点、位置、宽度与键盘导航机制，不是单纯绝对定位 |
| AI 分组命令菜单 | 用户截图＋官方 API | 命令可独立放进主工具栏或浮动工具栏，支持分组、增删与两种执行路径 |
| 侧边功能切换 | 用户截图＋官方 API | AI 功能插件可单独启用，按钮与面板可分离摆放；切换不应清空各功能状态 |
| model／联网／thinking 控件 | 用户截图＋官方说明 | 能力受模型支持约束；仅看图标不能证明该次请求调用了联网或 reasoning |
| 选区 chip 与动效 | 用户截图＋官方上下文规则＋演示 CSS | 选区可显式加入或自动更新；渲染样式含新 chip 的 0.6s/ease-out 单次强调，触发条件未做完整运行核查 |
| 会话自动摘要标题 | 用户截图＋固定提交 CHANGELOG | 官方明确 AI 首次生成标题时播放标题动画；生成提示词、重命名策略和服务端实现未公开核查 |
## 浮动工具栏：值得借用的行为契约
[BalloonToolbar 源码](https://github.com/ckeditor/ckeditor5/blob/27f01f0c2af03e034dbdf185c802f4e383dd16a8/packages/ckeditor5-ui/src/toolbar/balloon/balloontoolbar.ts) 的具体机制：
- `123–135`：编辑区与工具栏共用焦点追踪；注册 Alt+F10 进入工具栏、Esc 退出的导航；选择变化防抖 200ms。
- `149–173`：拖动或直接改变选择先隐藏；选择停止变化且编辑器仍聚焦才显示。不会在拖选每一帧持续抢占视线。
- `176–186`：监测编辑区尺寸，默认将浮栏最大宽度限制为编辑区的 90%，容纳不下的按钮分组。
- `238–274`：默认不为折叠选择显示；所有命令均禁用时不显示；显示期间随编辑器 UI 更新重算位置。
- `317–349`：位置依据选择方向取首／末行矩形，并过滤下一行宽度为零的矩形；锚点是每次计算的函数，随滚动更新。
[ContextualBalloon 源码](https://github.com/ckeditor/ckeditor5/blob/27f01f0c2af03e034dbdf185c802f4e383dd16a8/packages/ckeditor5-ui/src/panel/balloon/contextualballoon.ts#L32) `32–63,208–271` 把工具栏、链接编辑等视图放进同一浮层栈：进入子界面后返回上一层，不叠出多个互相遮挡的独立浮窗。并发批注等独立对象可分栈切换。
**建议映射**：短浮栏只保留常用格式、批注、AI 入口；长菜单作为下一层。点击菜单输入框时继续保留对应正文高亮。滚动、窗口缩窄、多行选择、反向选择都纳入原型验收。200ms 与 90% 是参考实现参数，不直接当成案例库定值。
## AI 快捷命令：入口和执行必须分开
[Quick Actions 官方说明](https://ckeditor.com/docs/ckeditor5/latest/features/ai/ckeditor-ai-actions.html) 区分两条路径：`Ask AI` 打开聊天并带入选择，等待用户输入；`Summarize` 等聊天命令可带选择直接发起对话；`Continue writing`／缩短等修改命令在选区附近显示候选，等待接受或拒绝。动作使用 `id / label / prompt / type` 描述，可另设 `displayedPrompt`；类别或单项均可作为工具栏入口，也可移除默认项。
**建议映射**：复用“命令入口＋可见上下文＋候选预览”，不直接恢复用户此前取消的旧快捷按钮。候选清单可以作为显式插入 Skill 的入口；具体命令点下去是预填还是直接发送，要在原型中明确表现。全文对话、局部修改与独立版本仍按本项目已有业务语义处理，不由浮栏是否出现来决定权限或修改范围。
## 选择不是一块装饰标签
[Chat 官方说明](https://ckeditor.com/docs/ckeditor5/latest/features/ai/ckeditor-ai-chat.html#attaching-the-selection-automatically) 规定：默认点击 Ask AI 才附加选择；启用 `alwaysAddSelection` 后随选择变化更新，选择折叠时移除；该配置依赖文档上下文启用。`AIChatController#addSelectionToChatContext()` 的用途是把选择加入下一条消息。
**建议映射**：待发送 chip 展示摘要，可关闭、展开原文、返回正文定位；已发送消息保存实际引用文本与版本位置。正文蓝色原生选区、失焦后的保留高亮、当前消息上下文、已持久化引用是不同状态，不应仅凭 DOM selection 判断全部有效性。动效只表达刚刚带入或更新，不暗示后台已读取或审核完成。
案例库现有空 chip 有直接证据：`frontend/src/components/AgentChatPanel.vue:552–556` 发出的 `data-selection` 只有 `from/to`；`:668–671` 却读取 `part.data.quote`。`CanvasEditor.vue:142–164` 已形成包括 quote、revision、quoteHash 的选择上下文。优先修复这条展示／持久化契约，比加动效更基础。
## 侧边栏、会话与模型控制
[集成说明](https://ckeditor.com/docs/ckeditor5/latest/features/ai/ckeditor-ai-integration.html#ui-types-and-positioning) 提供 sidebar、overlay、custom；custom 示例可分别放置 `AITabs` 的按钮与面板。收起状态留下可点击的标签按钮；maximize 状态样式由集成者决定。适合案例库把文档操作区和 AI 对话区分开排布，同时保留同一个工作空间。
[Chat 模型配置](https://ckeditor.com/docs/ckeditor5/latest/features/ai/ckeditor-ai-chat.html#available-models) 的选择在会话期间保持，换模型需新会话；Web search 与 reasoning 只对兼容模型启用。案例库应由服务端真实能力驱动可用控件和运行标记；用户已将联网核验放入 Later，参考其布局不等于把联网范围重新搬回 M1。模型切换是否同样绑定会话，仍是本项目待定行为。
[固定提交 CHANGELOG:553](https://github.com/ckeditor/ckeditor5/blob/27f01f0c2af03e034dbdf185c802f4e383dd16a8/CHANGELOG.md#L553) 证实标题由 AI 首次生成时播放动画，历史会话重开不重复播放。`:558–559` 记录了切换 AI 功能不应重置状态或重复创建视图的行为。自动标题属于会话导航信息，不能覆盖文章标题；教师改过的会话名是否锁定、生成失败时如何展示需要案例库自己的契约。
## 现有依赖已经覆盖部分机制
本次本机已安装 `@tiptap/vue-3` 包，`src/index.ts:1` 导出 `BubbleMenu`；`src/BubbleMenu.ts:44–66` 负责注册与卸载 ProseMirror plugin。对应 `@tiptap/extension-bubble-menu/src/bubble-menu-plugin.ts`：
- `80–105`：菜单内部焦点视作编辑器焦点；空文本、空选择、只读编辑器默认不显示。
- `125–165`：鼠标进入菜单时抑制失焦隐藏；拖动开始隐藏。
- `220–238`：支持更新防抖，输入法 composing 时不刷新菜单。
- `264–285`：通过选择范围计算锚点矩形。
本项目 `frontend/package.json:21–24` 使用 Tiptap 2；本机这一实现使用 Tippy，不能照搬最新版 Tiptap 3 的 Floating UI API。`EditorToolbar.vue:9–14,29–38` 已把动作整理成命令列表，格式按钮已使用 `mousedown.prevent`；可在现有技术栈中做浮栏原型并共享命令，避免同时维护两套格式逻辑。
## 可转成 spec 的验收场景
以下是研究推导的候选要求，待主设计稿采纳：
1. 正文中后部划词即可加粗或开批注，工具栏不需要滚回顶部；反向多行选择和窄屏菜单不溢出。
2. 从划词到浮栏、菜单、聊天输入的焦点移动不清空目标；关闭选择 chip 后再发消息不携带旧选择。
3. chip 与已发送消息能看到相同原文；点击定位到对应版本；原文已变更时明确失效，不能悄悄套用其他范围。
4. 同一入口的“预填可编辑”“立即对话”“生成候选”可区分；接受前能查看变更，取消不修改教师稿。
5. 切换 AI、历史、批注等区域保留输入草稿和当前定位；返回历史会话不重复播放首次标题动画。
6. 模型、联网、reasoning 的启用状态与真实请求一致；不支持或未接通的能力不出现可操作的假开关。
7. 输入法组合、键盘导航、Esc 返回、触摸选择、减少动态效果偏好分别验证；动画完成不是操作成功的唯一反馈。
## 未核查
未执行 CKEditor demo 的真实模型请求或检查其请求载荷；未核实 chip 动画的全部触发条件、标题摘要 prompt、商业服务端源码；未确定案例库最佳浮栏延迟、面板宽度、命令数量或是否需要换编辑器。公开源码受其许可证约束；本轮产物是机制研究与自主实现建议，未复制 CKEditor 产品代码进入应用。
