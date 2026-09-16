// 命令菜单定义：三类执行行为（prefill / chat / revise）严格区分。
export const aiCommands = [
  { id: "ask", label: "问 AI", icon: "sparkles", mode: "prefill",
    hint: "带入选区，不自动发送" },
  { id: "chat-commands", label: "对话命令", icon: "sparkles", mode: "group", children: [
    { id: "explain", label: "解释", mode: "chat", prompt: "请解释下面这段教学内容的核心论点与论证方式，用中文回答：" },
    { id: "summarize", label: "总结", mode: "chat", prompt: "请用三句话总结下面这段教学内容：" },
    { id: "keypoints", label: "划出要点", mode: "chat", prompt: "请以要点列表列出下面这段教学内容的关键信息：" },
  ] },
  { id: "improve", label: "改进写作", mode: "revise", prompt: "请改写下面这段教学案例文字，提高表达质量，保持事实与语气不变。" },
  { id: "continue", label: "续写", mode: "revise", prompt: "请紧接原文续写一两句，延续论述方向与语气。" },
  { id: "fix-grammar", label: "修正语法与错别字", mode: "revise", prompt: "请修正下面文字中的语法与错别字，其余保持原样。" },
  { id: "adjust-length", label: "调整长度", icon: "chevron", mode: "group", children: [
    { id: "shorten", label: "精简", mode: "revise", prompt: "请把选中的原文改写得更精简，保持教学语气与事实不变。" },
    { id: "expand", label: "扩写", mode: "revise", prompt: "请把选中的原文适度扩写，补充细节，保持教学语气与事实不变。" },
  ] },
  { id: "change-tone", label: "调整语气", icon: "chevron", mode: "group", children: [
    { id: "formal", label: "更正式", mode: "revise", prompt: "请把选中的原文改得更正式，适合教学案例发表。" },
    { id: "plain", label: "更平实", mode: "revise", prompt: "请把选中的原文改得更平实易懂，适合本科课堂。" },
  ] },
  { id: "translate", label: "翻译", icon: "chevron", mode: "group", children: [
    { id: "zh2en", label: "中 → 英", mode: "revise", prompt: "请把选中的原文翻译成学术英文。" },
    { id: "en2zh", label: "英 → 中", mode: "revise", prompt: "请把选中的原文翻译成中文。" },
  ] },
];

export function flattenCommands(term) {
  const query = term.trim().toLowerCase();
  const out = [];
  for (const item of aiCommands) {
    if (item.mode === "group") {
      for (const child of item.children) {
        if (!query || `${item.label} ${child.label}`.toLowerCase().includes(query)) {
          out.push({ ...child, group: item.label });
        }
      }
    } else if (!query || item.label.toLowerCase().includes(query)) {
      out.push(item);
    }
  }
  return out;
}
