import { reactive } from "vue";

// 原型状态：文档/会话为内存模拟；AI 对话、修订建议、会话标题走真实模型（/prototype-ai 代理）。

export const store = reactive({
  doc: {
    title: "从钱伟长教育思想看“强国何以有我”",
    byline: "思政教学案例 · 工作稿",
    status: "撰写中",
    savedAt: "已保存至内存（演示）",
  },
  revisions: [],
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
  thinking: false,
  ui: { aiCollapsed: false, previewId: "" }, // AI面板收起态 / 当前预览修订
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
