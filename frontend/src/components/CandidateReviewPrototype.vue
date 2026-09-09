<script setup>
import { computed, nextTick, onMounted, onBeforeUnmount, ref } from "vue";
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
const floating = ref(false), note = ref(""), decisions = ref({}), commentThreads = ref({});
const threadQuote = ref(""), overwriteOpen = ref(false), savedOriginal = ref(clone(props.caseRecord.document));
const savedGenerated = ref(null), savedTimes = ref({});
const popup = ref({ left: "0px", top: "0px" }), status = ref("");
const variant = computed(() => route.query.variant === "B" ? "B" : "A");
const blocks = computed(() => artifact.value?.blocks || []);
const sections = computed(() => blocks.value.reduce(groupBlock, []));
const current = computed(() => sections.value[selected.value]);
const activeDocument = computed(() => tab.value === "original" ? original.value : generated.value);
const threadMessages = computed(() => commentThreads.value[selected.value] || []);
const threadList = computed(() => Object.entries(commentThreads.value).map(([index, entries]) => ({ index: Number(index), entries, latest: entries.at(-1), title: sections.value[index]?.title })));
const timeline = computed(() => [
  { id: "generated", title: "AI 初稿", origin: "AI 生成", time: savedTimes.value.generated || artifact.value?.createdAt },
  { id: "original", title: "教师稿", origin: "教师保存", time: savedTimes.value.original || props.caseRecord.updatedAt },
]);
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
  if (!generated.value) { generated.value = candidateDocument(); savedGenerated.value = clone(generated.value); }
  generatedOpen.value = true; tab.value = "generated";
}
function displayTime(value) { return value ? new Date(value).toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }) : "生成时"; }
function openVersion(id) {
  if (id === "generated") openGenerated();
  else tab.value = "original";
  router.replace({ query: { ...route.query, variant: "A" } });
}
function overwriteVersion() {
  if (tab.value === "original") savedOriginal.value = clone(original.value);
  else savedGenerated.value = clone(generated.value);
  savedTimes.value[tab.value] = new Date().toISOString();
  overwriteOpen.value = false; status.value = "已覆盖保存此版本（原型）";
}
function saveDocument(value) {
  if (tab.value === "original") original.value = value;
  else generated.value = value;
  status.value = "编辑已保留在原型内";
}
function restoreSaved() {
  if (tab.value === "original") original.value = clone(savedOriginal.value);
  else generated.value = clone(savedGenerated.value);
  status.value = "已载入此版本最后保存的内容";
}
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
function askAI() {
  if (variant.value === "B") { ensureThread(selected.value); threadQuote.value = selectionQuote.value; floating.value = true; }
  else { chatQuote.value = selectionQuote.value; panel.value = "chat"; }
  selectionQuote.value = "";
}
async function copySelection() {
  try { await navigator.clipboard.writeText(selectionQuote.value); status.value = "已复制，可切到当前正文粘贴"; selectionQuote.value = ""; }
  catch { status.value = "请使用 Ctrl+C 复制选中文字"; }
}
function ensureThread(index) {
  if (commentThreads.value[index]) return;
  commentThreads.value[index] = [
    { kind: "human", text: "这里的表述有些绕，能否更直接一些，同时保留原意？" },
    { kind: "revision", round: 1, text: "建议把‘聚焦’改为‘探讨’，保留原句其他内容。", decision: "pending" },
  ];
}
function addOpinion() {
  if (!note.value.trim()) return;
  ensureThread(selected.value);
  const entries = commentThreads.value[selected.value];
  entries.filter(item => item.kind === "revision" && item.decision === "pending").forEach(item => item.decision = "superseded");
  entries.push({ kind: "human", text: note.value.trim(), quote: threadQuote.value });
  const round = entries.filter(item => item.kind === "revision").length + 1;
  entries.push({ kind: "revision", round, text: threadQuote.value ? "已记录你引用的部分。下一轮围绕这部分继续修改，其他内容保留。" : "收到补充意见。继续沿用已认可的部分，针对你指出的问题提出下一轮修改。", quote: threadQuote.value, decision: "pending" });
  decisions.value[selected.value] = "pending"; note.value = ""; threadQuote.value = "";
  nextTick(() => { const box = document.querySelector(".prototype-comment-scroll"); if (box) box.scrollTop = box.scrollHeight; });
}
function decideRevision(message, value) { message.decision = value; decisions.value[selected.value] = value; }
function openComment(index) { selected.value = index; ensureThread(index); floating.value = true; selectionQuote.value = ""; }
function leaveSelectionComment() { threadQuote.value = selectionQuote.value; openComment(selected.value); }
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
    if (candidate) { artifact.value = candidate; ensureThread(1); return; }
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
      <div v-if="variant === 'A'" class="prototype-version-tabs"><button :class="{ active: tab === 'original' }" @click="tab = 'original'"><FileText :size="14" />教师稿</button><button v-if="generatedOpen" :class="{ active: tab === 'generated' }" @click="tab = 'generated'"><Sparkles :size="14" />AI 初稿</button><button class="version-save-entry" @click="overwriteOpen = true">覆盖保存</button><button class="version-history-entry" @click="panel = 'versions'"><History :size="15" />版本</button></div>
      <div v-else class="prototype-preview-bar"><span><MessageSquareText :size="15" />正文精修</span><span class="prototype-state">点击修改标记或右侧批注标记查看意见</span></div>
      <article class="document-paper prototype-paper" @mouseup="captureSelection">
        <template v-if="variant === 'A'"><div class="prototype-document-note">{{ tab === 'original' ? '教师稿 · 可编辑' : 'AI 初稿 · 可编辑、复制到教师稿' }}</div><CanvasEditor v-if="activeDocument" :key="tab" :document="activeDocument" :editable="true" @change="saveDocument" /></template>
        <template v-else><section v-for="(section, i) in sections" :id="`candidate-section-${i}`" :key="i" class="prototype-section" :class="{ focused: selected === i }"><div class="markdown-body" v-html="sectionHtml(section, i)" @click="openComment(i)" /><button v-if="i > 0" class="prototype-comment-pin" :class="{ active: selected === i }" :aria-label="`查看${section.title}的批注`" @click="openComment(i)"><MessageSquareText :size="16" /><span v-if="selected === i">1</span></button></section></template>
      </article>
    </main>
    <aside class="prototype-assistant">
      <header><button :class="{ active: panel === 'chat' }" @click="panel = 'chat'"><Sparkles :size="17" />AI</button><button :class="{ active: panel === 'versions' }" @click="panel = 'versions'"><History :size="17" />版本</button><button :class="{ active: panel === 'comments' }" @click="panel = 'comments'"><MessageSquareText :size="17" />批注</button></header>
      <div class="prototype-thread">根据我的资料帮我生成一份案例 <span>⌄</span></div>
      <div class="prototype-rail-content">
        <template v-if="panel === 'chat'"><div class="prototype-chat-user">根据我的资料生成一份完整案例。</div><div class="prototype-assistant-label">AI</div><p>初稿已保存。可以打开继续编辑，或选中文字和我讨论。</p><article class="prototype-compact-card"><div><FileText :size="17" /><b>科学家精神的时代回响</b></div><p>AI 生成稿 · {{ sections.length }} 个章节</p><button class="prototype-primary" :disabled="!artifact" @click="openGenerated(); router.replace({ query: { ...route.query, variant: 'A' } })">打开稿件</button></article><template v-for="(message, i) in messages" :key="i"><div :class="message.kind === 'user' ? 'prototype-chat-user' : 'prototype-chat-reply'"><blockquote v-if="message.quote">{{ message.quote }}</blockquote>{{ message.text }}</div></template></template>
        <template v-else-if="panel === 'versions'"><h2>版本时间线</h2><div class="prototype-timeline"><article v-for="version in timeline" :key="version.id"><span class="timeline-dot" :class="{ ai: version.id === 'generated' }" /><small>{{ displayTime(version.time) }} · {{ version.origin }}</small><button class="prototype-version-card" :disabled="version.id === 'generated' && !artifact" @click="openVersion(version.id)"><Sparkles v-if="version.id === 'generated'" :size="18" /><FileText v-else :size="18" /><span><b>{{ version.title }}</b><small>在 Tab 中打开并编辑</small></span></button></article></div><button class="prototype-text-button" @click="restoreSaved">重新载入当前 Tab 已保存的内容</button></template>
        <template v-else><div class="prototype-list-heading"><h2>批注列表</h2><small>{{ threadList.length }} 条</small></div><button v-for="thread in threadList" :key="thread.index" class="prototype-comment-row" @click="router.replace({ query: { ...route.query, variant: 'B' } }); openComment(thread.index)"><span class="comment-row-icon"><MessageSquareText :size="17" /></span><span><b>{{ thread.title }}</b><p>{{ thread.entries.filter(item => item.kind === 'human').at(-1)?.text }}</p><small>{{ thread.entries.length }} 条消息 · {{ thread.latest.decision === 'accepted' ? '已接受' : thread.latest.decision === 'rejected' ? '保留原文' : '待处理' }}</small></span></button></template>
      </div>
      <footer class="prototype-composer"><div v-if="chatQuote" class="prototype-quote-chip"><span>稿件选区：{{ chatQuote.slice(0, 90) }}…</span><button @click="chatQuote = ''"><X :size="13" /></button></div><div class="prototype-compose-box"><textarea v-model="chatInput" aria-label="原型对话输入" placeholder="继续讨论，或选择稿件中的文字…" @keydown.ctrl.enter="sendOpinion" /><div><span>插入 Skill⌄</span><button class="prototype-primary" :disabled="!chatInput.trim()" @click="sendOpinion">发送 ↑</button></div></div><small>{{ status || '原型演示 · 编辑和批注仅保留在本页' }}</small></footer>
    </aside>
    <div v-if="selectionQuote" class="prototype-selection-toolbar" :style="popup" @mousedown.prevent><button @click="copySelection">复制</button><button @click="askAI">就此提问</button><button @click="leaveSelectionComment">留批注</button></div>
    <div v-if="overwriteOpen" class="prototype-pick-backdrop"><section class="prototype-pick-dialog" role="dialog" aria-label="覆盖版本警告"><h2>覆盖保存“{{ tab === 'original' ? '教师稿' : 'AI 初稿' }}”？</h2><p class="overwrite-warning">此版本原先保存的内容将被替换，覆盖后无法找回。其他版本不受影响。</p><button class="prototype-primary" @click="overwriteVersion">确认覆盖保存</button><button @click="overwriteOpen = false">取消</button><small class="prototype-muted">原型操作，仅本页生效</small></section></div>
    <aside v-if="floating" class="prototype-comment-float" role="dialog" aria-label="批注与关联修改"><header><div><MessageSquareText :size="16" /><b>批注与修改</b></div><button aria-label="关闭批注浮窗" @click="floating = false"><X :size="17" /></button></header><div class="prototype-comment-scroll"><small class="prototype-muted">{{ current?.title }}</small><article v-for="(message, i) in threadMessages" :key="i" class="prototype-thread-message"><b v-if="message.kind === 'human'">我</b><b v-else><Sparkles :size="14" />AI · 第 {{ message.round }} 轮修改</b><blockquote v-if="message.quote" class="thread-message-quote">{{ message.quote }}</blockquote><p>{{ message.text }}</p><template v-if="message.kind === 'revision'"><details><summary>修改依据与说明</summary><p>针对上方意见调整表达。淡红删除线标出原词，淡绿下划线标出建议用词。采用前保留原文。</p><p>进一步讨论时可以引用具体文字，说明要保留或继续修改的部分。每轮意见与建议都会保留；最新建议等待确认，先前建议仍可回看。这里是交互演示，未调用真实 AI。</p></details><div v-if="message.decision === 'pending'" class="prototype-floating-decisions"><button class="prototype-primary" @click="decideRevision(message, 'accepted')"><Check :size="14" />接受修改</button><button @click="decideRevision(message, 'rejected')">保留原文</button></div><small v-else class="prototype-resolution">{{ message.decision === 'accepted' ? '已接受修改' : message.decision === 'rejected' ? '已保留原文' : '已有后续建议 · 保留供回看' }}</small></template></article></div><footer><div v-if="threadQuote" class="prototype-quote-chip"><span>引用选区：{{ threadQuote.slice(0, 120) }}</span><button @click="threadQuote = ''"><X :size="13" /></button></div><textarea v-model="note" aria-label="原型批注意见" placeholder="继续讨论，例如：前半句保留，只改后半句…" /><button class="prototype-primary" :disabled="!note.trim()" @click="addOpinion">发送意见</button></footer></aside>
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

.prototype-version-tabs .version-save-entry { margin-left:auto; color:var(--brand); }
.prototype-version-tabs .version-history-entry { margin-left:0; }
.prototype-timeline { padding-left:18px; margin:24px 0; }
.prototype-timeline article { position:relative; border-left:1px solid #ded4c3; padding:0 0 28px 24px; }
.prototype-timeline article:last-child { border-color:transparent; }
.prototype-timeline article > small { color:var(--ink-3); }
.timeline-dot { position:absolute; width:9px; height:9px; border:2px solid #fcfaf6; background:#9e8a69; border-radius:50%; left:-5px; top:5px; box-shadow:0 0 0 1px #d9cdb8; }
.timeline-dot.ai { background:var(--brand); }
.prototype-timeline .prototype-version-card { padding:14px; margin-top:9px; }
.prototype-list-heading { display:flex; justify-content:space-between; align-items:center; }
.prototype-list-heading small { color:var(--ink-3); }
.prototype-comment-row { display:flex; gap:12px; width:100%; text-align:left; border:0; border-bottom:1px solid var(--line); background:none; padding:18px 0; }
.prototype-comment-row > span:last-child { min-width:0; }
.prototype-comment-row p { color:var(--ink-2); margin:7px 0; font-size:12px; line-height:1.7; }
.prototype-comment-row small { color:var(--ink-3); font-size:11px; }
.comment-row-icon { color:var(--brand); padding-top:2px; }
.thread-message-quote { margin:10px 0; border-left:2px solid #bba67f; background:#f5f0e6; padding:8px 10px; font-size:12px; color:var(--ink-2); max-height:130px; overflow:auto; }
.prototype-comment-float .prototype-quote-chip { width:100%; margin:0; }
.prototype-pick-dialog .overwrite-warning { color:#9b302c; line-height:1.8; font-size:14px; }
</style>
