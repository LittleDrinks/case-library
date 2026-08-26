---
sources:
  - product: Notion AI
    urls:
      - https://www.notion.com/help/guides/notion-ai-for-docs
      - https://www.notion.com/help/research-mode
  - product: Microsoft Copilot in Word
    urls:
      - https://support.microsoft.com/en-us/word/copilot/draft-and-add-content-with-copilot-in-word
      - https://support.microsoft.com/en-us/word/copilot/rewrite-text-with-copilot-in-word
  - product: Gemini in Google Docs
    urls:
      - https://support.google.com/docs/answer/13447609?hl=en
  - product: NotebookLM
    urls:
      - https://blog.google/innovation-and-ai/models-and-research/google-labs/notebooklm-discover-sources/
  - product: Grammarly
    urls:
      - https://support.grammarly.com/hc/en-us/articles/14528857014285-Introducing-generative-AI-assistance
  - product: Perplexity
    urls:
      - https://www.perplexity.ai/hub/blog/introducing-internal-knowledge-search-and-spaces
      - https://www.perplexity.ai/help-center/en/articles/10352961-what-are-spaces.html
  - product: ChatGPT Canvas
    urls:
      - https://openai.com/index/introducing-canvas/
  - product: WPS AI
    urls:
      - https://ai.wps.cn/
  - product: 飞书智能伙伴
    urls:
      - https://www.feishu.cn/hc/zh-CN/articles/318505042260
---
# AI 写作与研究产品模式
## 产品做法
| 产品 | 用户入口 | 上下文与资料 | 结果承接 | 可复用结论 |
| --- | --- | --- | --- | --- |
| Notion AI | 侧栏 Agent、选中文本后编辑、空行生成 | 当前页面、工作区、连接应用、网页；研究模式可限定来源 | 编辑结果可接受、丢弃、重试；研究结果显示来源并可保存为页面 | 全局任务、局部修改、新内容生成是三个入口；资料来源不是快捷按钮 |
| Microsoft Copilot in Word | 空白文档起草、引用文件起草、选中文本重写 | 最多选择 20 个文件、邮件或会议作为起草依据 | 草稿可保留、重生成、丢弃、继续细化；重写可替换、插入下方、重生成 | 先给依据再生成；AI 结果始终是可拒绝的草稿 |
| Gemini in Google Docs | 底部输入、侧栏输入、选中文本后的 Refine | 文档上下文、Drive 文件、Chat、Gmail、网页 | 建议直接显示在文档中，可逐条接受、全部接受或全部拒绝 | 常驻入口只承接自由意图；改写动作随选区出现；来源单独选择 |
| NotebookLM | 来源面板中的 Discover、对来源提问 | 用户上传资料与网页候选；网页发现最多返回 10 条带相关性说明的来源 | 用户一键加入来源，原文长期留在项目中，回答保留引用 | 先收敛来源，再让 AI 使用；发现结果不能自动进入项目 |
| Grammarly | AI Chat、选中文本后的段落操作 | 当前文本与个人表达偏好 | 生成、改写、构思和回复均围绕当前写作位置 | 局部能力只在有选区时出现，避免常驻工具栏堆积 |
| Perplexity | 问答与项目空间 | 公开网页和内部文件可在同一研究空间检索 | 回答附来源，研究过程保留在项目中 | 内外资料可以统一编排，但来源类别和引用必须可见 |
| ChatGPT Canvas | 对话打开画布、直接编辑、写作快捷操作 | 当前画布与用户选中的局部内容 | 用户直接编辑正文，AI 对选区或全文提出调整 | 长文写作应保持正文为主，AI 控件不能持续占据注意力 |
| WPS AI | 写作模板、文档内 AI、全文总结与问答 | 当前文档、主题、大纲或段落要点 | 续写、缩写、润色、风格转换继续留在原文档 | 面向办公用户先选任务，再提供材料和约束；模板承担起步成本 |
| 飞书智能伙伴 | AI 模板新建、选中文本后智能润色 | 当前文档与选区 | 调整篇幅、语法和语气后回到原文档 | 模板负责从零开始，选区动作负责局部修改，两者不混成按钮矩阵 |
## 共同模式
1. 用户选择目标，Agent 选择工具。成熟产品通常不要求用户理解“站内检索、联网检索、网页抓取”的技术区别；本平台因教学资料来源有明确边界，允许教师显式限定资料范围。
2. 常驻入口保持一到三个。自由输入承接开放需求，资料查找和长任务只在明确需要时进入专门流程。
3. 局部动作随上下文出现。选中文字后出现改写，选中批注后出现处理意见；没有选区时不展示。
4. 来源先于写作。内部资料、网页候选和用户文件先成为可查看、可选择的来源，生成内容再引用这些来源。
5. AI 不直接覆盖正文。草稿、建议和改写候选必须经过接受、拒绝或重试。
6. 研究过程与普通对话分级。只有需要多来源检索的长任务展示阶段和来源；简单润色不展示工具流水账。
7. 模板解决从零开始的问题。模板建立结构，AI 在结构内补充内容；一键生成整篇不是唯一入口。
8. 来源与建议分层。事实、数据和理论判断展示依据；结构、表达和教学活动明确为 AI 建议。
## 平台取舍
- 保留截图中的能力，但不把六个能力都做成同级常驻按钮。输入框旁的“资料范围”打开复选框：理论知识、平台案例与素材、联网检索、网页采集；教师勾选即限定本次可用资料工具。
- “理论”和“平台”是 `search_corpus` 的不同检索范围；“联网”对应 `web_search`；“网页”对应 `fetch_url`，勾选后显示 URL 输入。教师提交 URL 即确认把成功采集的网页加入当前案例附件。
- 选中文字或当前小节时保留“改写选区”“改写本节”和“润色”；选中批注后显示“让 AI 处理”。它们是写作任务，不与资料工具混放。
- “教学版”不纳入首轮试用，待教学版转换形成完整需求、来源边界和验收标准后再开放。
- “查资料”在教师勾选的范围内检索；过程卡显示实际调用、查询词和结果摘要。案例结果只能“引用案例”，素材和网页结果只能“加入附件”。
- 写作候选继续使用接受、拒绝、重试和批次回滚，不增加直接改写正文的捷径。
