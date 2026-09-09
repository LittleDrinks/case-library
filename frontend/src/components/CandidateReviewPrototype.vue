<script setup>
// 两种候选预览交互嵌入真实工作台；所有采用和批注操作仅保存在本页内存。
import { computed, onMounted, onBeforeUnmount, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ArrowLeft, ArrowRight, Check, MessageSquareText, Sparkles, X } from "@lucide/vue";
import CanvasEditor from "./CanvasEditor.vue";
import { diffChars } from "diff";
import { generateJSON } from "@tiptap/core";
import StarterKit from "@tiptap/starter-kit";
import { renderMarkdown } from "../lib/markdown.js";
import { api } from "../api.js";
const props = defineProps({ caseRecord: Object });
const route = useRoute(), router = useRouter();
const artifact = ref(null), selected = ref(1), tab = ref("candidate"), comments = ref([]);
const rejected = ref([]);
const accepted = ref([]), status = ref("待确认"), note = ref(""), panel = ref("candidate");
const chatInput = ref(""), chatQuote = ref(""), selectionQuote = ref(""), targetQuote = ref("");
const messages = ref([]), pickOpen = ref(false), previewOpen = ref(false), original = ref(JSON.parse(JSON.stringify(props.caseRecord.document)));
const popup = ref({ left: "0px", top: "0px" });
const variant = computed(() => route.query.variant === "B" ? "B" : "A");
const blocks = computed(() => artifact.value?.blocks || []);
const sections = computed(() => blocks.value.reduce(groupBlock, []));
const current = computed(() => sections.value[selected.value]);
function groupBlock(result, block) {
  if (block.type === "heading" || !result.length) result.push({ title: block.type === "heading" ? block.text : "正文", blocks: [] });
  result.at(-1).blocks.push(block);
  return result;
}
function blockMarkdown(block) {
  if (block.type === "heading") return `${"#".repeat(Math.min(block.level || 2, 3))} ${block.text}`;
  if (block.type === "bullet_list") return block.items.map(x => `- ${x}`).join("\n");
  if (block.type === "ordered_list") return block.items.map((x, i) => `${i + 1}. ${x}`).join("\n");
  if (block.type === "blockquote") return block.paragraphs.map(x => `> ${x}`).join("\n");
  return block.text || "";
}
function escape(value) { return value.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;"); }
function revisedText(text) {
  if (text.includes("本案例聚焦")) return text.replace("本案例聚焦", "本案例探讨");
  if (text.includes("通过")) return text.replace("通过", "借助");
  return text + "（具体依据待补充）";
}
function changedParagraph(text) {
  const replacement = revisedText(text);
  return diffChars(text, replacement).map(part => {
    const tag = part.added ? "ins" : part.removed ? "del" : "span";
    return `<${tag}>${escape(part.value)}</${tag}>`;
  }).join("");
}
function sectionHtml(section, index) {
  return section.blocks.map(block => {
    if (variant.value === "B" && block === section.blocks.find(item => item.type === "paragraph")) {
      if (accepted.value.includes(index)) return renderMarkdown(revisedText(block.text));
      if (index === selected.value && !rejected.value.includes(index)) return `<p class="prototype-inline-change">${changedParagraph(block.text)}</p>`;
    }
    return renderMarkdown(blockMarkdown(block));
  }).join("\n");
}
function captureSelection() {
  const selection = window.getSelection();
  const quote = selection?.toString().trim();
  if (!quote || !selection.rangeCount) { selectionQuote.value = ""; return; }
  const rect = selection.getRangeAt(0).getBoundingClientRect();
  selectionQuote.value = quote;
  popup.value = { left: `${Math.min(rect.left, window.innerWidth - 360)}px`, top: `${Math.max(125, rect.top - 46)}px` };
}
function askAI() {
  chatQuote.value = selectionQuote.value;
  selectionQuote.value = "";
  panel.value = "candidate";
}
function selectTarget() { targetQuote.value = selectionQuote.value; selectionQuote.value = ""; tab.value = "candidate"; }
function replaceText(node, quote, replacement) {
  if (node.text?.includes(quote)) { node.text = node.text.replace(quote, replacement); return true; }
  return (node.content || []).some(child => replaceText(child, quote, replacement));
}
function chooseText(replace = false) {
  const draft = JSON.parse(JSON.stringify(original.value));
  if (replace && !replaceText(draft, targetQuote.value, selectionQuote.value)) { status.value = "请重新选择一个完整段落内的替换位置"; return; }
  if (!replace) draft.content.push({ type: "paragraph", content: [{ type: "text", text: selectionQuote.value }] });
  original.value = draft;
  messages.value.push({ kind: "receipt", text: replace ? "已在原型正文中替换选区。" : "已将所选内容加入原型正文末尾。" });
  status.value = "部分选用";
  selectionQuote.value = "";
  pickOpen.value = false;
}
function sendOpinion() {
  if (!chatInput.value.trim()) return;
  messages.value.push({ kind: "user", text: chatInput.value, quote: chatQuote.value });
  messages.value.push({ kind: "reply", text: "已收到这条修改意见。正式交互会针对该选区返回新的修订候选，原内容在采用前保留。" });
  chatInput.value = "";
  chatQuote.value = "";
}
function commentOnSelection() { note.value = `关于“${selectionQuote.value.slice(0, 100)}”：`; selectionQuote.value = ""; panel.value = "comments"; }
function keySwitch(event) {
  if (["INPUT", "TEXTAREA"].includes(event.target.tagName) || event.target.isContentEditable) return;
  if (["ArrowLeft", "ArrowRight"].includes(event.key)) switchVariant();
}
async function load() {
  const threads = await api.agentThreads(props.caseRecord.id);
  for (const thread of threads) {
    const snapshot = await api.agentThread(props.caseRecord.id, thread.id);
    const candidate = [...(snapshot.artifacts || [])].reverse().find(x => x.kind === "document");
    if (candidate) { artifact.value = candidate; return; }
  }
}
function locate(index) {
  selected.value = index;
  document.getElementById(`candidate-section-${index}`)?.scrollIntoView({ block: "start", behavior: "smooth" });
}
function switchVariant() { router.replace({ query: { ...route.query, variant: variant.value === "A" ? "B" : "A" } }); }
function acceptAll() {
  original.value = generateJSON(renderMarkdown(blocks.value.map(blockMarkdown).join("\n\n")), [StarterKit]);
  status.value = "已在原型中采用整稿";
  tab.value = "original";
  previewOpen.value = true;
}
function acceptSection(index) { rejected.value = rejected.value.filter(i => i !== index); if (!accepted.value.includes(index)) accepted.value.push(index); }
function rejectSection(index) { accepted.value = accepted.value.filter(i => i !== index); if (!rejected.value.includes(index)) rejected.value.push(index); }
function addComment() {
  if (!note.value.trim()) return;
  comments.value.push({ section: current.value?.title || "全文", text: note.value.trim() });
  note.value = "";
}
onMounted(() => { load(); window.addEventListener("keydown", keySwitch); });
onBeforeUnmount(() => window.removeEventListener("keydown", keySwitch));
</script>

<template>
  <div class="canvas-workspace candidate-prototype">
    <nav class="prototype-outline"><small>候选目录</small><button v-for="(section, i) in sections" :key="i" :class="{ current: selected === i }" @click="locate(i)">{{ i === 0 ? "标题" : section.title }}<Check v-if="accepted.includes(i)" :size="13" /></button></nav>
    <main class="canvas-column prototype-canvas">
      <div class="prototype-preview-bar"><span><Sparkles :size="15" />{{ variant === 'A' ? '全文候选预览' : '逐节审阅候选' }}</span><div v-if="variant === 'A'" class="prototype-segment"><button :class="{ active: tab === 'original' }" @click="tab = 'original'; previewOpen = true">当前正文</button><button :class="{ active: tab === 'candidate' }" @click="tab = 'candidate'; previewOpen = true">AI 候选</button></div><span class="prototype-state">{{ status }}</span></div>
      <article class="document-paper prototype-paper" @mouseup="captureSelection">
        <template v-if="variant === 'A' && (!previewOpen || tab === 'original')"><h1>{{ caseRecord.title }}</h1><CanvasEditor :document="original" :editable="false" /></template>
        <template v-else>
          <div class="prototype-document-note">{{ variant === 'A' ? '完整预览 · 采用前不会修改正文' : '精修示意 · 仅高亮当前修改的文字，原文保持可读' }}</div>
          <p v-if="!artifact">正在读取本案例的完整候选……</p>
          <section v-for="(section, i) in sections" :id="`candidate-section-${i}`" :key="i" class="prototype-section" :class="{ proposed: variant === 'B', focused: selected === i, adopted: accepted.includes(i) }" @click="selected = i">
            <div class="markdown-body" v-html="sectionHtml(section, i)" />
            <div v-if="variant === 'B' && selected === i" class="prototype-section-actions"><span>{{ accepted.includes(i) ? '已采用这处修改' : rejected.includes(i) ? '已保留原文' : '表达精炼 · 示例修订' }}</span><button @click.stop="acceptSection(i)"><Check :size="14" />接受修改</button><button @click.stop="selected = i; panel = 'comments'"><MessageSquareText :size="14" />留批注</button><button @click.stop="rejectSection(i)"><X :size="14" />保留原文</button></div>
          </section>
        </template>
      </article>
    </main>
    <aside class="prototype-assistant">
      <header><button :class="{ active: panel === 'candidate' }" @click="panel = 'candidate'"><Sparkles :size="17" />AI</button><button :class="{ active: panel === 'comments' }" @click="panel = 'comments'"><MessageSquareText :size="17" />批注 <small v-if="comments.length">{{ comments.length }}</small></button></header>
      <div class="prototype-thread">根据我的资料帮我生成一份案例 <span>⌄</span></div>
      <div class="prototype-rail-content">
        <template v-if="panel === 'candidate'">
          <div class="prototype-chat-user">根据我的资料生成一份完整案例。</div>
          <div class="prototype-assistant-label">AI</div><p>已准备好一份初稿。你可以先预览全文，选用其中的段落，也可以继续告诉我怎么改。</p>
          <article class="prototype-compact-card"><div><Sparkles :size="16" /><b>全文初稿候选</b><span>{{ status }}</span></div><p>{{ sections.length }} 个章节 · 尚未修改正文</p><button class="prototype-primary" @click="previewOpen = true; tab = 'candidate'">{{ previewOpen ? '正在预览' : '预览完整初稿' }}</button><button class="prototype-text-button" @click="acceptAll">采用整稿</button><button class="prototype-text-button" @click="status = '已拒绝候选'">拒绝</button></article>
          <p class="prototype-chat-hint">在预览中拖选文字，可选择放入正文的位置，或把选区带入对话继续修改。</p>
          <template v-for="(message, i) in messages" :key="i"><div :class="message.kind === 'user' ? 'prototype-chat-user' : 'prototype-chat-reply'"><blockquote v-if="message.quote">{{ message.quote }}</blockquote>{{ message.text }}</div></template>
        </template>
        <template v-else>
          <div class="prototype-assistant-label">当前定位</div><blockquote>{{ current?.title || '全文' }}</blockquote><p class="prototype-muted">先定位原文，再记录具体问题与建议。正式审核的通过或退回仍在页面顶部操作。</p>
          <article v-for="(comment, i) in comments" :key="i" class="prototype-comment"><small>{{ comment.section }}</small><p>{{ comment.text }}</p><span>待处理</span></article>
          <div v-if="!comments.length" class="prototype-empty"><MessageSquareText :size="25" /><p>这个位置还没有批注</p></div>
          <textarea v-model="note" placeholder="例如：这个数据的来源是什么？建议补充出处。" aria-label="原型批注意见" /><button class="prototype-primary" :disabled="!note.trim()" @click="addComment">添加意见</button>
        </template>
      </div>
      <footer class="prototype-composer"><div v-if="chatQuote" class="prototype-quote-chip"><span>候选选区：{{ chatQuote.slice(0, 90) }}{{ chatQuote.length > 90 ? '…' : '' }}</span><button @click="chatQuote = ''"><X :size="13" /></button></div><div class="prototype-compose-box"><textarea v-model="chatInput" aria-label="原型对话输入" placeholder="继续讨论，或选中候选文字提出修改意见…" @keydown.ctrl.enter="sendOpinion" /><div><span>插入 Skill⌄</span><button class="prototype-primary" :disabled="!chatInput.trim()" @click="sendOpinion">发送 ↑</button></div></div><small>原型演示 · 本页操作不写入真实案例</small></footer>
    </aside>
    <div v-if="selectionQuote && !pickOpen" class="prototype-selection-toolbar" :style="popup" @mousedown.prevent><template v-if="variant === 'A' && (!previewOpen || tab === 'original')"><button @click="selectTarget">设为正文替换位置</button></template><template v-else><button @click="pickOpen = true">选用到正文…</button><button @click="askAI">让 AI 修改</button><button @click="commentOnSelection">留批注</button></template></div>
    <div v-if="pickOpen" class="prototype-pick-backdrop"><section class="prototype-pick-dialog"><h2>把所选内容放在哪里？</h2><blockquote>{{ selectionQuote.slice(0, 180) }}</blockquote><button @click="chooseText(false)">追加到正文末尾</button><button :disabled="!targetQuote" @click="chooseText(true)">替换已选择的正文位置</button><p v-if="!targetQuote">需要替换时，先在“当前正文”中选择要替换的文字。</p><button class="prototype-text-button" @click="pickOpen = false">取消</button></section></div>
    <div class="prototype-switcher"><span>交互原型</span><button @click="switchVariant"><ArrowLeft :size="16" /></button><b>{{ variant === 'A' ? 'A · 正文切换预览' : 'B · 原位逐节审阅' }}</b><button @click="switchVariant"><ArrowRight :size="16" /></button><span>{{ status }}</span></div>
  </div>
</template>
<style scoped>
.candidate-prototype { color: var(--ink); }
.prototype-outline { display: flex; flex-direction: column; gap: 12px; padding: 38px 12px 90px 0; overflow: auto; }
.prototype-outline small { color: var(--ink-3); margin-bottom: 16px; }
.prototype-outline button { text-align: left; border: 0; background: none; color: var(--ink-2); line-height: 1.7; padding: 8px 0; display: flex; align-items: center; gap: 6px; }
.prototype-outline button.current { color: var(--brand); }
.prototype-canvas { position: relative; }
.prototype-preview-bar { position: sticky; top: 0; z-index: 3; min-height: 56px; display: flex; align-items: center; justify-content: space-between; gap: 8px; padding: 10px 16px; background: #f9f6ef; border: 1px solid var(--line); border-radius: 8px 8px 0 0; font-size: 12px; }
.prototype-preview-bar > span:first-child { display: flex; gap: 6px; align-items: center; }
.prototype-state { color: var(--ink-3); }
.prototype-segment { display: flex; padding: 3px; background: #eee8de; border-radius: 6px; }
.prototype-segment button { border: 0; background: transparent; padding: 6px 10px; border-radius: 4px; color: var(--ink-2); }
.prototype-segment button.active { background: white; color: var(--brand); }
.prototype-paper { border-radius: 0 0 8px 8px; padding: 46px 56px 100px; }
.prototype-paper h1 { font-family: var(--serif); text-align: center; }
.prototype-document-note { text-align: center; color: var(--ink-3); font-size: 12px; margin-bottom: 30px; }
.prototype-section { scroll-margin-top: 85px; padding: 10px 0 20px; }
.prototype-section :deep(.markdown-body) { font-family: var(--serif); font-size: 18px; line-height: 1.9; }
.prototype-section :deep(.markdown-body h1), .prototype-section :deep(.markdown-body h2) { font-size: 23px; margin-bottom: 18px; }
.prototype-section.proposed { background: transparent; padding: 10px 0 20px; border-left: 0; margin: 0; }
.prototype-section.proposed.focused { position: relative; }
.prototype-section.adopted { border-left-color: #348260; }
.prototype-section-actions { display: flex; gap: 10px; justify-content: flex-end; align-items: center; margin-top: 20px; font: 12px/1.6 sans-serif; }
.prototype-section-actions > span { margin-right: auto; color: #348260; }
.prototype-section-actions button, .prototype-decisions button { display: inline-flex; align-items: center; gap: 6px; padding: 8px 12px; border: 1px solid var(--line); border-radius: 6px; background: white; }
.prototype-assistant { min-height: 0; display: flex; flex-direction: column; border: 1px solid var(--line); border-radius: 12px; background: #fcfaf6; overflow: hidden; }
.prototype-assistant header { display: flex; gap: 16px; padding: 0 16px; border-bottom: 1px solid var(--line); }
.prototype-assistant header button { display: flex; align-items: center; gap: 7px; padding: 16px 10px; border: 0; border-bottom: 2px solid transparent; background: transparent; color: var(--ink-2); }
.prototype-assistant header button.active { color: var(--brand); border-bottom-color: var(--brand); }
.prototype-thread { font-size: 12px; padding: 12px 18px; border-bottom: 1px solid var(--line); }
.prototype-thread span { float: right; }
.prototype-rail-content { min-height: 0; overflow: auto; padding: 26px 22px; flex: 1; font-size: 13px; line-height: 1.8; }
.prototype-assistant-label { font-size: 11px; color: var(--ink-3); }
.prototype-rail-content h2 { font-size: 19px; margin: 8px 0 12px; }
.prototype-facts { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; padding: 20px 0; border-bottom: 1px solid var(--line); }
.prototype-facts span { color: var(--ink-3); }
.prototype-facts b { font-weight: 500; text-align: right; }
.prototype-evidence { background: #f2ece1; border-radius: 7px; padding: 16px; margin: 24px 0; }
.prototype-evidence p { margin-bottom: 0; }
.prototype-locate { display: flex; align-items: center; justify-content: space-between; gap: 6px; width: 100%; text-align: left; border: 1px solid var(--line); padding: 12px; background: white; border-radius: 7px; color: var(--brand); }
.prototype-help { margin-top: 30px; color: var(--ink-2); }
.prototype-help h3 { font-size: 14px; }
.prototype-assistant footer { padding: 18px 22px; border-top: 1px solid var(--line); }
.prototype-decisions { display: flex; gap: 10px; margin-bottom: 12px; }
.prototype-primary, .prototype-decisions .prototype-primary { border: 0; background: var(--brand); color: white; border-radius: 6px; padding: 9px 15px; }
.prototype-primary:disabled { opacity: .5; }
.prototype-assistant footer small, .prototype-muted { color: var(--ink-3); font-size: 11px; }
.prototype-rail-content blockquote { margin: 14px 0; padding: 14px; background: #f2ece1; border-left: 2px solid var(--brand); }
.prototype-empty { text-align: center; padding: 35px 10px; color: var(--ink-3); }
.prototype-rail-content textarea { width: 100%; min-height: 105px; padding: 12px; border: 1px solid var(--line); border-radius: 6px; margin: 12px 0; resize: vertical; background: white; }
.prototype-comment { border: 1px solid var(--line); border-radius: 8px; padding: 12px; margin-top: 12px; background: white; }
.prototype-comment small, .prototype-comment span { font-size: 11px; color: var(--ink-3); }
.prototype-switcher { position: fixed; bottom: 18px; left: 50%; transform: translateX(-50%); z-index: 90; display: flex; gap: 12px; align-items: center; padding: 10px 14px; border-radius: 10px; color: white; background: #302c27; box-shadow: 0 4px 22px #0002; font-size: 12px; }
.prototype-switcher > span { color: #c6bbaa; white-space: nowrap; }
.prototype-switcher button { background: transparent; color: white; border: 1px solid #72685a; border-radius: 5px; padding: 4px; display: flex; }
.prototype-switcher b { white-space: nowrap; font-weight: 500; }
@media(max-width: 1000px) { .prototype-outline { display:none; } .prototype-paper { padding: 30px 24px 80px; } }
@media(max-width: 780px) { .candidate-prototype { display: grid; grid-template-columns: 1fr; overflow: auto; } .prototype-assistant { min-height: 500px; } .prototype-preview-bar { flex-wrap: wrap; } .prototype-switcher > span:last-child { display:none; } }

.prototype-section :deep(ins) { background: #e6f2e9; color: #286746; text-decoration: underline; text-decoration-color: #9cbda6; text-underline-offset: 4px; }
.prototype-section :deep(del) { background: #faeeee; color: #a77777; text-decoration-thickness: 1px; }
.prototype-section-actions { border-top: 1px solid #eae5dc; padding-top: 12px; margin-top: 12px; }
.prototype-chat-user { margin: 0 0 22px 34px; padding: 12px 14px; background: #f5eee2; border: 1px solid #e7d9c4; border-radius: 10px; }
.prototype-chat-user blockquote { font-size: 11px; margin: 0 0 8px; max-height: 80px; overflow: auto; }
.prototype-compact-card { padding: 16px; border: 1px solid #e5ded1; background: white; border-radius: 9px; margin: 20px 0; }
.prototype-compact-card > div { display: flex; gap: 7px; align-items: center; }
.prototype-compact-card > div span { margin-left: auto; color: var(--ink-3); font-size: 11px; }
.prototype-compact-card p, .prototype-chat-hint { font-size: 12px; color: var(--ink-3); }
.prototype-text-button { background: none; border: 0; padding: 8px; color: var(--ink-2); }
.prototype-chat-reply { padding: 12px 0; margin-bottom: 16px; }
.prototype-composer { flex-shrink: 0; }
.prototype-compose-box { padding: 12px; background: white; border: 1px solid var(--line); border-radius: 12px; margin-bottom: 8px; }
.prototype-compose-box textarea { width: 100%; min-height: 78px; resize: vertical; border: 0; outline: none; font: inherit; line-height: 1.7; }
.prototype-compose-box > div { display: flex; align-items: center; justify-content: space-between; font-size: 12px; color: var(--ink-3); }
.prototype-quote-chip { display: flex; align-items: flex-start; gap: 8px; padding: 10px; background: #f2ece1; border-left: 2px solid #c9b797; border-radius: 4px; font-size: 11px; line-height: 1.7; margin-bottom: 10px; }
.prototype-quote-chip button { margin-left: auto; border: 0; background: transparent; }
.prototype-selection-toolbar { position: fixed; z-index: 110; display: flex; gap: 4px; background: white; border: 1px solid var(--line); box-shadow: 0 5px 20px #0002; border-radius: 7px; padding: 5px; }
.prototype-selection-toolbar button { border: 0; background: none; padding: 6px 10px; color: var(--ink); font-size: 12px; }
.prototype-selection-toolbar button:hover { background: #f3eee5; }
.prototype-pick-backdrop { position: fixed; inset: 0; z-index: 130; background: #0005; display: grid; place-items: center; }
.prototype-pick-dialog { width: min(520px, 92vw); background: white; border-radius: 12px; padding: 26px; box-shadow: 0 20px 70px #0003; }
.prototype-pick-dialog h2 { font-size: 18px; }
.prototype-pick-dialog blockquote { margin: 18px 0; background: #f7f4ef; padding: 14px; color: var(--ink-2); font-size: 13px; line-height: 1.7; }
.prototype-pick-dialog > button { display: block; width: 100%; padding: 12px; border: 1px solid var(--line); border-radius: 7px; background: white; margin-top: 10px; }
.prototype-pick-dialog > button:disabled { opacity: .5; }
.prototype-pick-dialog p { color: var(--ink-3); font-size: 12px; }
</style>
