import { reactive } from "vue";

// 原型状态：文档/批注/会话为内存模拟；AI 对话、修订建议、会话标题走真实模型（/prototype-ai 代理）。

export const mockSkills = [
  { id: "source-trace", name: "史料考证", version: "v3" },
  { id: "citation-check", name: "引文核对", version: "v2" },
  { id: "tone-polish", name: "语气润色", version: "v1" },
];

export const mockResources = [
  { id: "r1", name: "钱伟长《教育和教学问题的思考》节选.pdf", meta: "资料库 · 已挂载" },
  { id: "r2", name: "上海大学校史馆讲解词（2024 修订）.docx", meta: "资料库 · 已挂载" },
  { id: "r3", name: "《自然辩证法概论（2025版）》第二章.md", meta: "公共素材" },
];

export const store = reactive({
  doc: {
    title: "从钱伟长教育思想看“强国何以有我”",
    byline: "思政教学案例 · 工作稿",
    status: "撰写中",
    savedAt: "已保存至内存（演示）",
  },
  annotations: [
    {
      id: "a1", author: "王老师", time: "09-12 14:02", kind: "comment",
      anchorQuote: "我不知道什么专业是热门的，我只知道国家需要什么，我就做什么",
      text: "这句名言建议补充出处年份（1952 年赴京途中对记者所言），并核对通行版本的措辞差异。",
      resolved: false, replies: [
        { id: "a1r1", author: "李编辑", time: "09-12 15:10", text: "已查校史馆讲解词，通行版本确为“国家的需要就是我的专业”。" },
      ],
    },
    {
      id: "a2", author: "李编辑", time: "09-13 09:41", kind: "comment",
      anchorQuote: "既做科学家，又做教育家",
      text: "这里建议引用原文页码，并说明“两个身份”如何统一在办学实践中。",
      resolved: false, replies: [],
    },
    {
      id: "a3", author: "王老师", time: "09-13 16:20", kind: "comment",
      anchorQuote: "科学家最重要的品质是爱国",
      text: "此处可加一句过渡，把个人选择与国家需要连接起来，避免论述断层。",
      resolved: false, replies: [],
    },
  ],
  elapsedTick: 0,
  runningJob: null, // { id, startedAt, kind, elapsed, controller, timer }
  railTab: "ai",
  composerDraft: "",
  selectionChip: null, // { quote, from, to }
  pendingSelection: null, // 最近一次正文选区，供工具栏/命令菜单继续使用
  threads: [{ id: "t0", title: "新会话", auto: false, messages: [], draft: "" }],
  activeThreadId: "t0",
  aiConfig: { models: [], defaultModel: "", ready: false, error: "" },
  modelId: "",
  webSearch: false, // Later：未接入，只展示不可用的说明
  thinking: false,
  ui: { aiCollapsed: false, expandedAnnId: "" }, // AI面板收起态 / 当前展开的批注卡（其余折叠）
});

export function activeThread() {
  return store.threads.find((t) => t.id === store.activeThreadId);
}

export function newThread() {
  const id = `t${Date.now()}`;
  store.threads.unshift({ id, title: "新会话", auto: false, messages: [], draft: "" });
  store.activeThreadId = id;
  return id;
}
