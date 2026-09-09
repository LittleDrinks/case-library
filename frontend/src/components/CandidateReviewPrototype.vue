<script setup>
import { computed, onMounted, onBeforeUnmount, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ArrowLeft, ArrowRight, Check, MessageSquareText, Sparkles, X, History, FileText } from "@lucide/vue";
import { generateJSON } from "@tiptap/core";
import StarterKit from "@tiptap/starter-kit";
import { diffChars } from "diff";
import CanvasEditor from "./CanvasEditor.vue";
import { renderMarkdown } from "../lib/markdown.js";
import { api } from "../api.js";
const props = defineProps({ caseRecord: Object });
const route = useRoute(), router = useRouter();
const clone = value => JSON.parse(JSON.stringify(value));
const artifact = ref(null), selected = ref(1), tab = ref("original"), panel = ref("chat");
const original = ref(clone(props.caseRecord.document)), generated = ref(null), generatedOpen = ref(false);
const messages = ref([]), chatInput = ref(""), chatQuote = ref(""), selectionQuote = ref("");
const floating = ref(false), note = ref(""), opinions = ref({}), decisions = ref({});
const popup = ref({ left: "0px", top: "0px" }), status = ref("");
const variant = computed(() => route.query.variant === "B" ? "B" : "A");
const blocks = computed(() => artifact.value?.blocks || []);
const sections = computed(() => blocks.value.reduce(groupBlock, []));
const current = computed(() => sections.value[selected.value]);
const activeDocument = computed(() => tab.value === "original" ? original.value : generated.value);
const currentOpinion = computed(() => opinions.value[selected.value] || "这里的表述有些绕，能否更直接一些，同时保留原意？");
const decision = computed(() => decisions.value[selected.value] || "pending");
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
function candidateDocument() { return generateJSON(renderMarkdown(blocks.value.map(blockMarkdown).join("\n\n")), [StarterKit]); }
function openGenerated() {
  if (!generated.value) generated.value = candidateDocument();
  generatedOpen.value = true; tab.value = "generated";
}
function saveDocument(value) {
  if (tab.value === "original") original.value = value;
  else generated.value = value;
  status.value = "编辑已保留在原型内";
}
function resetGenerated() { generated.value = candidateDocument(); status.value = "已重新打开生成时的快照"; }
function escape(value) { return value.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;"); }
function revisedText(text) {
  if (text.includes("本案例聚焦")) return text.replace("本案例聚焦", "本案例探讨");
  if (text.includes("通过")) return text.replace("通过", "借助");
  return text + "（具体依据待补充）";
}
function changedParagraph(text) {
  return diffChars(text, revisedText(text)).map(part => {
    const tag = part.added ? "ins" : part.removed ? "del" : "span";
    return `<${tag}>${escape(part.value)}</${tag}>`;
  }).join("");
}
function sectionHtml(section, index) {
  return section.blocks.map(block => {
    if (block === section.blocks.find(item => item.type === "paragraph")) {
      if (decisions.value[index] === "accepted") return renderMarkdown(revisedText(block.text));
      if (index === selected.value && !["rejected", "comment"].includes(decisions.value[index])) return `<p>${changedParagraph(block.text)}</p>`;
    }
    return renderMarkdown(blockMarkdown(block));
  }).join("\n");
}
function captureSelection() {
  const selection = window.getSelection(), quote = selection?.toString().trim();
  if (!quote || !selection.rangeCount) { selectionQuote.value = ""; return; }
  const rect = selection.getRangeAt(0).getBoundingClientRect();
  selectionQuote.value = quote;
  popup.value = { left: `${Math.max(8, Math.min(rect.left, window.innerWidth - 320))}px`, top: `${Math.max(130, rect.top - 46)}px` };
}
function askAI() { chatQuote.value = selectionQuote.value; selectionQuote.value = ""; panel.value = "chat"; }
async function copySelection() {
  try { await navigator.clipboard.writeText(selectionQuote.value); status.value = "已复制，可切到当前正文粘贴"; selectionQuote.value = ""; }
  catch { status.value = "请使用 Ctrl+C 复制选中文字"; }
}
function addOpinion() {
  if (!note.value.trim()) return;
  opinions.value[selected.value] = note.value.trim(); decisions.value[selected.value] = "comment"; note.value = "";
}
function openComment(index) { selected.value = index; floating.value = true; selectionQuote.value = ""; }
function leaveSelectionComment() { note.value = `关于“${selectionQuote.value.slice(0, 90)}”：`; floating.value = true; selectionQuote.value = ""; }
function sendOpinion() {
  if (!chatInput.value.trim()) return;
  messages.value.push({ kind: "user", text: chatInput.value, quote: chatQuote.value });
  messages.value.push({ kind: "reply", text: "原型已记录这条意见。正式功能将在这份稿件的基础上继续处理。" });
  chatInput.value = ""; chatQuote.value = "";
}
function locate(index) {
  selected.value = index;
  if (variant.value === "B") document.getElementById(`candidate-section-${index}`)?.scrollIntoView({ block: "start", behavior: "smooth" });
  else document.querySelectorAll(".prototype-paper .tiptap h1, .prototype-paper .tiptap h2, .prototype-paper .tiptap h3")[index]?.scrollIntoView({ block: "start", behavior: "smooth" });
}
async function load() {
  const threads = await api.agentThreads(props.caseRecord.id);
  for (const thread of threads) {
    const snapshot = await api.agentThread(props.caseRecord.id, thread.id);
    const candidate = [...(snapshot.artifacts || [])].reverse().find(x => x.kind === "document");
    if (candidate) { artifact.value = candidate; return; }
  }
}
function switchVariant() { floating.value = false; router.replace({ query: { ...route.query, variant: variant.value === "A" ? "B" : "A" } }); }
function keySwitch(event) {
  if (["INPUT", "TEXTAREA"].includes(event.target.tagName) || event.target.isContentEditable) return;
  if (["ArrowLeft", "ArrowRight"].includes(event.key)) switchVariant();
}
onMounted(() => { load(); window.addEventListener("keydown", keySwitch); });
onBeforeUnmount(() => window.removeEventListener("keydown", keySwitch));
</script>
<template>
  <div class="canvas-workspace candidate-prototype">
    <nav class="prototype-outline"><small>本文目录</small><button v-for="(section, i) in sections" :key="i" :class="{ current: selected === i }" @click="locate(i)">{{ i === 0 ? "标题" : section.title }}</button></nav>
    <main class="canvas-column prototype-canvas">
      <div v-if="variant === 'A'" class="prototype-version-tabs"><button :class="{ active: tab === 'original' }" @click="tab = 'original'"><FileText :size="14" />当前正文</button><button v-if="generatedOpen" :class="{ active: tab === 'generated' }" @click="tab = 'generated'"><Sparkles :size="14" />AI 初稿 · 编辑副本</button><button class="version-history-entry" @click="panel = 'versions'"><History :size="15" />版本</button></div>
      <div v-else class="prototype-preview-bar"><span><MessageSquareText :size="15" />正文精修</span><span class="prototype-state">点击修改标记或右侧批注标记查看意见</span></div>
      <article class="document-paper prototype-paper" @mouseup="captureSelection">
        <template v-if="variant === 'A'"><div class="prototype-document-note">{{ tab === 'original' ? '当前正文 · 可编辑' : '基于 AI 生成快照编辑 · 可复制到当前正文' }}</div><CanvasEditor v-if="activeDocument" :key="tab" :document="activeDocument" :editable="true" @change="saveDocument" /></template>
        <template v-else><section v-for="(section, i) in sections" :id="`candidate-section-${i}`" :key="i" class="prototype-section" :class="{ focused: selected === i }"><div class="markdown-body" v-html="sectionHtml(section, i)" @click="openComment(i)" /><button v-if="i > 0" class="prototype-comment-pin" :class="{ active: selected === i }" :aria-label="`查看${section.title}的批注`" @click="openComment(i)"><MessageSquareText :size="16" /><span v-if="selected === i">1</span></button></section></template>
      </article>
    </main>
    <aside class="prototype-assistant">
      <header><button :class="{ active: panel === 'chat' }" @click="panel = 'chat'"><Sparkles :size="17" />AI</button><button :class="{ active: panel === 'versions' }" @click="panel = 'versions'"><History :size="17" />版本</button><button :class="{ active: panel === 'comments' }" @click="panel = 'comments'"><MessageSquareText :size="17" />批注</button></header>
      <div class="prototype-thread">根据我的资料帮我生成一份案例 <span>⌄</span></div>
      <div class="prototype-rail-content">
        <template v-if="panel === 'chat'"><div class="prototype-chat-user">根据我的资料生成一份完整案例。</div><div class="prototype-assistant-label">AI</div><p>初稿已保存。可以打开继续编辑，或选中文字和我讨论。</p><article class="prototype-compact-card"><div><FileText :size="17" /><b>科学家精神的时代回响</b></div><p>AI 生成稿 · {{ sections.length }} 个章节</p><button class="prototype-primary" :disabled="!artifact" @click="openGenerated(); router.replace({ query: { ...route.query, variant: 'A' } })">打开稿件</button></article><template v-for="(message, i) in messages" :key="i"><div :class="message.kind === 'user' ? 'prototype-chat-user' : 'prototype-chat-reply'"><blockquote v-if="message.quote">{{ message.quote }}</blockquote>{{ message.text }}</div></template></template>
        <template v-else-if="panel === 'versions'"><h2>稿件与版本</h2><p class="prototype-muted">打开工作副本继续编辑，生成时的快照保留。</p><button class="prototype-version-card" @click="tab = 'original'; router.replace({ query: { ...route.query, variant: 'A' } })"><FileText :size="18" /><span><b>当前正文</b><small>正在编辑的案例</small></span></button><button class="prototype-version-card" :disabled="!artifact" @click="openGenerated(); router.replace({ query: { ...route.query, variant: 'A' } })"><Sparkles :size="18" /><span><b>AI 初稿</b><small>从生成快照打开编辑副本</small></span></button><button v-if="generatedOpen" class="prototype-text-button" @click="resetGenerated">重新打开生成时的快照</button></template>
        <template v-else><h2>批注</h2><p class="prototype-muted">意见和对应的 AI 修订放在同一条批注里。</p><button class="prototype-version-card" @click="router.replace({ query: { ...route.query, variant: 'B' } }); openComment(1)"><MessageSquareText :size="18" /><span><b>{{ sections[1]?.title || '摘要' }}</b><small>查看意见与关联修改</small></span></button></template>
      </div>
      <footer class="prototype-composer"><div v-if="chatQuote" class="prototype-quote-chip"><span>稿件选区：{{ chatQuote.slice(0, 90) }}…</span><button @click="chatQuote = ''"><X :size="13" /></button></div><div class="prototype-compose-box"><textarea v-model="chatInput" aria-label="原型对话输入" placeholder="继续讨论，或选择稿件中的文字…" @keydown.ctrl.enter="sendOpinion" /><div><span>插入 Skill⌄</span><button class="prototype-primary" :disabled="!chatInput.trim()" @click="sendOpinion">发送 ↑</button></div></div><small>{{ status || '原型演示 · 编辑和批注仅保留在本页' }}</small></footer>
    </aside>
    <div v-if="selectionQuote" class="prototype-selection-toolbar" :style="popup" @mousedown.prevent><button @click="copySelection">复制</button><button @click="askAI">就此提问</button><button @click="leaveSelectionComment">留批注</button></div>
    <aside v-if="floating" class="prototype-comment-float" role="dialog" aria-label="批注与关联修改"><header><div><MessageSquareText :size="16" /><b>批注与修改</b></div><button aria-label="关闭批注浮窗" @click="floating = false"><X :size="17" /></button></header><div class="prototype-comment-scroll"><small class="prototype-muted">{{ current?.title }}</small><div class="prototype-thread-message"><b>我</b><p>{{ currentOpinion }}</p></div><template v-if="decision !== 'comment'"><div class="prototype-thread-message"><b><Sparkles :size="14" />AI · 对这条意见的修改</b><p>将“聚焦”改为“探讨”，使句子直接说明这份案例的研究目的。保留主体、事实与原有教学内容。</p><details><summary>修改依据与说明</summary><p>这是一处措辞调整，回应上方批注中的“更直接一些”。正文以淡红删除线标出原词、淡绿下划线标出建议用词；未经确认时保留原文。此处不补写新事实，也不把措辞修改当作事实核验。</p><p>如果你认为原来的措辞更准确，可以保留原文，或在下方补充意见，让 AI 继续针对同一条批注提出新的修改。</p></details></div><div class="prototype-floating-decisions" v-if="decision === 'pending'"><button class="prototype-primary" @click="decisions[selected] = 'accepted'"><Check :size="14" />接受修改</button><button @click="decisions[selected] = 'rejected'">保留原文</button></div><p v-else class="prototype-resolution">{{ decision === 'accepted' ? '已接受修改 · 原型内生效' : '已保留原文' }}</p></template><button v-else class="prototype-primary" @click="decisions[selected] = 'pending'">让 AI 按这条意见修改</button></div><footer><textarea v-model="note" aria-label="原型批注意见" placeholder="补充意见，继续讨论这处修改…" /><button class="prototype-primary" :disabled="!note.trim()" @click="addOpinion">发送意见</button></footer></aside>
    <div class="prototype-switcher"><span>交互原型</span><button @click="switchVariant"><ArrowLeft :size="16" /></button><b>{{ variant === 'A' ? 'A · 版本与编辑' : 'B · 浮动批注精修' }}</b><button @click="switchVariant"><ArrowRight :size="16" /></button></div>
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

.prototype-version-tabs { display:flex; align-items:center; gap:4px; position:sticky; top:0; z-index:3; padding:8px 10px 0; background:#f4f0e8; border:1px solid var(--line); border-radius:9px 9px 0 0; }
.prototype-version-tabs button { display:flex; gap:7px; align-items:center; padding:13px 16px; background:transparent; border:0; color:var(--ink-2); border-radius:7px 7px 0 0; font-size:12px; }
.prototype-version-tabs button.active { background:white; color:var(--brand); box-shadow:0 -2px 0 var(--brand) inset; }
.prototype-version-tabs .version-history-entry { margin-left:auto; }
.prototype-version-card { display:flex; align-items:flex-start; gap:12px; width:100%; text-align:left; background:white; border:1px solid var(--line); border-radius:8px; padding:17px; margin-top:14px; color:var(--ink); }
.prototype-version-card span { display:flex; flex-direction:column; gap:5px; }
.prototype-version-card small { color:var(--ink-3); font-size:11px; }
.prototype-section { position:relative; }
.prototype-section :deep(ins), .prototype-section :deep(del) { cursor:pointer; }
.prototype-comment-pin { position:absolute; right:-43px; top:36px; border:1px solid #e8dfd0; background:#fffdf7; color:#9b8661; padding:7px; border-radius:7px; display:flex; align-items:center; gap:4px; opacity:.5; }
.prototype-comment-pin.active, .prototype-section:hover .prototype-comment-pin { opacity:1; color:var(--brand); }
.prototype-comment-float { position:fixed; z-index:100; right:max(26px,calc((100vw - 1440px)/2)); top:205px; width:400px; max-height:calc(100vh - 240px); display:flex; flex-direction:column; border:1px solid #dfd5c4; border-radius:13px; background:#fffefa; box-shadow:0 16px 60px #30271930,0 2px 8px #30271915; }
.prototype-comment-float > header { display:flex; align-items:center; justify-content:space-between; padding:15px 18px; border-bottom:1px solid var(--line); font-size:13px; }
.prototype-comment-float > header > div { display:flex; align-items:center; gap:7px; }
.prototype-comment-float > header > button { display:flex; padding:5px; border:0; background:transparent; color:var(--ink-3); }
.prototype-comment-scroll { padding:18px; overflow:auto; min-height:0; font-size:13px; line-height:1.8; }
.prototype-thread-message { margin-top:17px; padding-bottom:16px; border-bottom:1px solid #eee7db; }
.prototype-thread-message > b { display:flex; align-items:center; gap:6px; font-size:12px; color:var(--ink-2); }
.prototype-thread-message > p { margin:8px 0 0; }
.prototype-thread-message details { margin-top:12px; color:var(--ink-2); font-size:12px; }
.prototype-thread-message summary { cursor:pointer; color:#947c55; }
.prototype-floating-decisions { display:flex; gap:10px; margin-top:16px; }
.prototype-floating-decisions button { display:flex; gap:5px; align-items:center; padding:9px 13px; border:1px solid var(--line); border-radius:6px; background:white; }
.prototype-floating-decisions button.prototype-primary { background:var(--brand); color:white; border-color:var(--brand); }
.prototype-comment-float > footer { flex-shrink:0; border-top:1px solid var(--line); padding:14px 18px; display:flex; flex-direction:column; align-items:flex-end; gap:9px; }
.prototype-comment-float textarea { width:100%; min-height:68px; max-height:130px; padding:10px; border:1px solid var(--line); border-radius:7px; resize:vertical; font:12px/1.7 sans-serif; }
.prototype-resolution { color:#348260; font-size:12px; }
@media(max-width:780px) { .prototype-comment-float { right:12px; width:calc(100vw - 24px); top:160px; max-height:calc(100vh - 190px); } }
</style>
