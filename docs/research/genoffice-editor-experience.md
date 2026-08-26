---
sources:
  - id: R1
    claim: GenOffice 将 AI 定位为文档编辑工作流的一等能力，Docs 使用 Tiptap/ProseMirror，并以块级编辑、快照和差异承接 AI 修改。
    url: https://github.com/genspark-ai/genoffice/blob/7a814dbd2327059f3f28fbaaa7f79f16f9245b37/README.md#L79-L97
  - id: R2
    claim: 选中文字后出现跟随选区的 Ask AI 入口；按选区类型提供不同的预填建议，用户可立即发送或加入编辑队列。
    url: https://github.com/genspark-ai/genoffice/blob/7a814dbd2327059f3f28fbaaa7f79f16f9245b37/apps/docs/src/renderer/components/AiAskPopover.tsx#L51-L75
  - id: R3
    claim: 队列项以编辑装饰锚定文本，随手动编辑迁移；发送前解析当前块范围，孤立锚点不提交，批量修改按从后到前的块顺序执行。
    url: https://github.com/genspark-ai/genoffice/blob/7a814dbd2327059f3f28fbaaa7f79f16f9245b37/apps/docs/src/renderer/ai/edit-queue.ts#L5-L16
  - id: R4
    claim: AI 面板按一次运行保存修改前快照，提供单次回退；可选将 AI 修改保留为待人工接受或拒绝的修订，并展示工具执行状态。
    url: https://github.com/genspark-ai/genoffice/blob/7a814dbd2327059f3f28fbaaa7f79f16f9245b37/apps/docs/src/renderer/ai/AiPanel.tsx#L573-L639
  - id: R5
    claim: 每次运行冻结选区和文档状态；基于块索引的写入在检测到用户外部编辑后被拒绝，直到 Agent 重新读取当前文档。
    url: https://github.com/genspark-ai/genoffice/blob/7a814dbd2327059f3f28fbaaa7f79f16f9245b37/apps/docs/src/renderer/ai/docs-skill.ts#L31-L55
  - id: R6
    claim: 编辑 Agent 通过读取上下文、插入、替换块和确定性格式命令修改文档；评审修订仅供用户在 Review 中接受或拒绝。
    url: https://github.com/genspark-ai/genoffice/blob/7a814dbd2327059f3f28fbaaa7f79f16f9245b37/apps/docs/src/renderer/ai/tools.ts#L32-L108
---
# GenOffice 编辑体验参考
## 可验证事实
- AI 的入口分为常驻侧栏和选区浮动入口。选区浮动入口针对文本、表格、图片、图表改变快捷建议，避免把局部编辑混入全局对话。R2
- 选区任务可立即执行，也可积累为最多 10 条的队列；队列卡可定位、编辑、移除和整体提交。锚点随正文变动解析，失效目标不发送。R2 R3
- 一次批量提交只修改已锚定的目标，按文档末尾到开头执行，避免前面的插入或删除改变后续块索引。R3
- 一次 AI 运行只保留一个运行前快照，用户可撤销该次运行及其后的回退点；开启修订时，AI 的修改进入人工评审而非立即定稿。R4
- AI 写入走受限的块级操作与确定性格式命令。任务开始时冻结选区，正文被人工改动后，旧上下文的索引写入会被拒绝。R5 R6
## 对本平台的编辑体验建议
- 保留正文居中主导、右侧 Copilot/批注/资料三标签和浮动大纲；不引入 Office Ribbon 或分页仿真。平台正文 JSON 已是唯一真源，工作台目标是案例创作而不是 DOCX 保真编辑。
- 将当前“改写选区/改写本节”统一为选区浮动入口：文本选区显示润色、精简、扩写、改错；无选区时不显示。点击后先写指令，再明确选择“生成候选”或“加入待处理”。
- 将现有最多三条候选升级为锚定编辑清单：每项保存精确范围、摘录和指令；正文变化后重新定位，失效项标为“目标已变更”，禁止应用。首个 alpha 只支持文本范围，不支持表格、图片和跨区块目标。
- AI 永远产出候选修订，不直接写正文。候选卡提供预览、接受、拒绝；接受后保留本批次快照，支持一次“撤销本批次”。不在 alpha 复制 GenOffice 的完整修订格式或多轮队列执行。
- 生成开始时记录 `revision`、目标范围与目标文本哈希；接受前再次校验三者。任一不一致即过期并提示重新生成，复用现有 revision 冲突模型，避免旧页面或旧候选覆盖新正文。
- 将对话流中的检索、资料与写作分开呈现：检索任务继续在 Copilot 中输出可查看来源；仅在用户选定候选后，提供“应用到选区/本节”的写作操作。工具过程可折叠，正文界面只显示候选状态与锚点。
## Alpha 验收
- 选中文本后，浮动入口不抢走编辑器焦点，取消后选区仍在。
- 同一案例存在三条待处理候选时，可分别预览、接受或拒绝；正文编辑后所有相关候选变为过期，不能应用。
- 生成或接受候选期间，手动保存与版本冲突行为保持现有语义；接受后的单批次撤销恢复接受前正文。
- AI 任务失败、取消或工具调用失败时，正文和待处理候选不产生隐式修改。
