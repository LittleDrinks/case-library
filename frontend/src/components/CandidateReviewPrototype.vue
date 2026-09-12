<script setup>
import { computed, nextTick, onMounted, onBeforeUnmount, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ArrowLeft, ArrowRight, Check, MessageSquareText, Sparkles, X, History, FileText, Paperclip } from "@lucide/vue";
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
const original = ref(clone(props.caseRecord.document)), versions = ref([]), openedVersions = ref([]);
const messages = ref([]), chatInput = ref(""), chatQuote = ref(""), selectionQuote = ref("");
const floating = ref(false), note = ref(""), decisions = ref({}), commentThreads = ref({});
const activeThread = ref(null), draftAnchor = ref(null);
let nextThreadId = 1;
const threadQuote = ref(""), overwriteOpen = ref(false), savedOriginal = ref(clone(props.caseRecord.document));
const savedTimes = ref({});
const popup = ref({ left: "0px", top: "0px" }), status = ref("");
const variant = computed(() => route.query.variant === "B" ? "B" : "A");
const historyExpanded = ref(false), versionName = ref(""), creatingVersion = ref(false);
let hideTimer;
function showHistory() { clearTimeout(hideTimer); historyExpanded.value = true; }
function hideHistory() { hideTimer = setTimeout(() => historyExpanded.value = false, 450); }
const blocks = computed(() => artifact.value?.blocks || []);
const sections = computed(() => blocks.value.reduce(groupBlock, []));
const current = computed(() => sections.value[floating.value ? (draftAnchor.value?.section ?? commentThreads.value[activeThread.value]?.section ?? selected.value) : selected.value]);
const activeVersion = computed(() => versions.value.find(version => version.id === tab.value));
const activeDocument = computed(() => tab.value === "original" ? original.value : activeVersion.value?.document);
const activeTitle = computed(() => tab.value === "original" ? "当前教师稿" : activeVersion.value?.title);
const opened = computed(() => openedVersions.value.map(id => versions.value.find(version => version.id === id)).filter(Boolean));
const threadMessages = computed(() => shownThreads.value[activeThread.value]?.messages || []);
const threadList = computed(() => Object.values(shownThreads.value).map(thread => ({ ...thread, latest: thread.messages.at(-1), title: sections.value[thread.section]?.title })));
function sectionThreads(index) { return threadList.value.filter(thread => thread.section === index); }

const timeline = computed(() => versions.value);
const shownThreads = computed(() => tab.value === "original" ? commentThreads.value : activeVersion.value?.comments || {});
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
function seedVersions() {
  const titles = ["AI 初稿", "补充教学目标后提交", "AI 精炼摘要", "讨论问题调整后提交", "AI 补充案例结构", "核对引用后提交", "备课稿提交审核", "AI 改写案例背景", "课堂活动调整后提交", "AI 生成教学建议", "修改题目后提交", "AI 初次整理资料", "资料整理后提交", "首次提交审核"];
  versions.value = titles.map((title, index) => {
    const document = index === titles.length - 1 ? clone(props.caseRecord.document) : candidateDocument();
    return { id: index === 0 ? "generated" : `version-${index}`, title, origin: title.startsWith("AI") ? "AI 生成" : "提交审核", time: new Date(Date.now() - index * 8 * 3600000).toISOString(), document, comments: {} };
  });
}
function openGenerated() { openVersion("generated"); }
function displayTime(value) { return new Date(value).toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }); }
function openVersion(id) {
  if (id !== "original" && !openedVersions.value.includes(id)) openedVersions.value.push(id);
  tab.value = id;
  router.replace({ query: { ...route.query, variant: "A" } });
}
function closeVersion(id) {
  openedVersions.value = openedVersions.value.filter(value => value !== id);
  if (tab.value === id) tab.value = "original";
}
function recordVersion(title, origin) {
  const id = `history-${Date.now()}-${versions.value.length}`;
  versions.value.unshift({ id, title, origin, time: new Date().toISOString(), document: clone(original.value), comments: clone(commentThreads.value) });
  status.value = `已创建历史版本：${title}`;
}
function createVersion() {
  recordVersion(versionName.value.trim() || "手动保存", "手动创建");
  versionName.value = ""; creatingVersion.value = false; panel.value = "versions";
}
function overwriteVersion() {
  const target = activeVersion.value;
  if (!target) return;
  recordVersion("恢复前的当前稿", "覆盖前保存");
  original.value = clone(target.document);
  commentThreads.value = clone(target.comments || {});
  recordVersion(`恢复：${target.title}`, "恢复历史");
  tab.value = "original"; overwriteOpen.value = false; floating.value = false;
  status.value = "正文、批注及讨论状态已恢复；恢复前的稿件已保留";
}
function saveDocument(value) {
  if (tab.value !== "original") return;
  original.value = value;
  Object.values(commentThreads.value).forEach(thread => thread.stale = !JSON.stringify(value).includes(thread.quote));
  status.value = "当前稿已自动保存（本页内存），未新增历史版本";
}
function preserveCurrent(title) {
  const latest = versions.value[0];
  if (JSON.stringify(latest?.document) !== JSON.stringify(original.value) || JSON.stringify(latest?.comments) !== JSON.stringify(commentThreads.value)) recordVersion(title, "修改前保存");
}
function acceptChatSuggestion() {
  const document = clone(original.value);
  document.content.push({ type: "paragraph", content: [{ type: "text", text: "课堂讨论后，请学生结合校园观察提出一项可执行的改进建议。" }] });
  const id = `ai-${Date.now()}`;
  versions.value.unshift({ id, title: "AI · 补充课堂讨论要求", origin: "AI 编写", time: new Date().toISOString(), document, comments: clone(commentThreads.value) });
  openVersion(id); showHistory(); hideHistory();
  status.value = "AI 历史版本已打开；当前教师稿保持不变";
}
function resolveThread() {
  const thread = commentThreads.value[activeThread.value];
  if (thread) thread.resolved = true;
  floating.value = false;
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
    if (sectionThreads(index).length && block === section.blocks.find(item => item.type === "paragraph")) {
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
  if (variant.value === "B") { startComment(selected.value, selectionQuote.value); }
  else { chatQuote.value = selectionQuote.value; panel.value = "chat"; }
  selectionQuote.value = "";
}
async function copySelection() {
  try { await navigator.clipboard.writeText(selectionQuote.value); status.value = "已复制，可切到当前正文粘贴"; selectionQuote.value = ""; }
  catch { status.value = "请使用 Ctrl+C 复制选中文字"; }
}
function seedExampleComment() {
  const id = nextThreadId++;
  commentThreads.value[id] = { id, section: 1, quote: "本案例聚焦", messages: [
    { kind: "human", text: "这里的表述有些绕，能否更直接一些，同时保留原意？" },
    { kind: "revision", round: 1, text: "建议把‘聚焦’改为‘探讨’，保留原句其他内容。", decision: "pending" },
  ] };
}
function startComment(section, quote) {
  selected.value = section; activeThread.value = null; draftAnchor.value = { section, quote };
  threadQuote.value = quote; note.value = ""; floating.value = true; selectionQuote.value = "";
}
function replyToComment(entries, text, quote) {
  entries.filter(item => item.kind === "revision" && item.decision === "pending").forEach(item => item.decision = "superseded");
  entries.push({ kind: "human", text, quote });
  const round = entries.filter(item => item.kind === "revision").length + 1;
  entries.push({ kind: "revision", round, text: `已收到意见：“${text}”。${quote ? "仅围绕所引用的部分继续处理。" : "保留已认可的内容，继续讨论需要调整的部分。"}（模拟回复）`, quote, decision: "pending" });
}
function addOpinion(withAI = false) {
  if (!note.value.trim()) return;
  if (draftAnchor.value) {
    const id = nextThreadId++;
    commentThreads.value[id] = { id, ...draftAnchor.value, messages: [] }; activeThread.value = id; draftAnchor.value = null;
  }
  const thread = commentThreads.value[activeThread.value];
  if (!thread) return;
  if (withAI) replyToComment(thread.messages, note.value.trim(), threadQuote.value);
  else thread.messages.push({ kind: "human", text: note.value.trim(), quote: threadQuote.value });
  decisions.value[thread.section] = "pending"; note.value = ""; threadQuote.value = "";
  nextTick(() => { const box = document.querySelector(".prototype-comment-scroll"); if (box) box.scrollTop = box.scrollHeight; });
}
function decideRevision(message, value) {
  const thread = commentThreads.value[activeThread.value];
  if (tab.value !== "original" || thread.stale) return;
  if (value === "accepted") {
    preserveCurrent("采用批注前的当前稿");
    const replace = node => { if (node.text) node.text = node.text.replace(thread.quote, revisedText(thread.quote)); node.content?.forEach(replace); };
    replace(original.value); message.decision = value; thread.resolved = true;
    recordVersion("采用批注修订", "接受 AI 建议");
  } else message.decision = value;
}
function openThread(id) {
  const thread = shownThreads.value[id]; if (!thread) return;
  selected.value = thread.section; activeThread.value = id; draftAnchor.value = null;
  floating.value = true; selectionQuote.value = ""; threadQuote.value = ""; note.value = "";
}
function openComment(index) {
  if (window.getSelection()?.toString().trim()) return;
  const thread = sectionThreads(index)[0]; if (thread) openThread(thread.id);
}
function leaveSelectionComment() { if (tab.value === "original") startComment(selected.value, selectionQuote.value); }
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
    if (candidate) { artifact.value = candidate; seedVersions(); original.value = candidateDocument(); seedExampleComment(); recordVersion("开始编辑", "初始记录"); panel.value = variant.value === "B" ? "comments" : "versions"; return; }
  }
}
function switchVariant() { floating.value = false; panel.value = variant.value === "A" ? "comments" : "versions"; router.replace({ query: { ...route.query, variant: variant.value === "A" ? "B" : "A" } }); }
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
      <div class="history-hover-zone" @mouseenter="showHistory" @mouseleave="hideHistory" @focusin="showHistory" @focusout="hideHistory"><button class="history-handle" :aria-expanded="historyExpanded" @click="historyExpanded = !historyExpanded"><span class="history-grip"></span><span>{{ tab === "original" ? "当前教师稿" : activeTitle }}</span><span class="history-count">{{ opened.length + 1 }} 个标签 · 悬停展开</span></button><div class="history-collapse" :class="{ expanded: historyExpanded }"><div class="prototype-version-tabs"><button class="pinned-teacher-tab" role="tab" :aria-selected="tab === 'original'" :class="{ active: tab === 'original' }" @click="tab = 'original'"><FileText :size="14" />当前教师稿</button><div class="prototype-open-tabs" role="tablist"><div v-for="version in opened" :key="version.id" class="prototype-tab-chip" :class="{ active: tab === version.id }"><button role="tab" :aria-selected="tab === version.id" @click="tab = version.id">{{ version.title }}</button><button class="close-version-tab" :aria-label="`关闭${version.title}`" @click="closeVersion(version.id)"><X :size="12" /></button></div></div><button class="version-history-entry" @click="panel = 'versions'"><History :size="15" />历史版本</button></div></div></div>
      <article class="document-paper prototype-paper" @mouseup="captureSelection">
        <template v-if="activeDocument"><div class="prototype-document-note">{{ activeTitle }} · {{ tab === "original" ? "可编辑" : "历史稿 · 只读" }} <button v-if="tab !== 'original'" @click="tab = 'original'">返回当前稿</button><button v-if="tab !== 'original'" @click="overwriteOpen = true">恢复此版本</button></div><CanvasEditor v-if="activeDocument" :key="tab" :document="activeDocument" :editable="tab === 'original'" @change="saveDocument" /></template>

      </article>
    </main>
    <aside class="prototype-assistant">
      <header><button :class="{ active: panel === 'chat' }" @click="panel = 'chat'"><Sparkles :size="17" />AI</button><button :class="{ active: panel === 'versions' }" @click="panel = 'versions'"><History :size="17" />历史版本</button><button :class="{ active: panel === 'comments' }" @click="panel = 'comments'"><MessageSquareText :size="17" />批注</button><button :class="{ active: panel === 'attachments' }" @click="panel = 'attachments'"><Paperclip :size="17" />附件</button></header>
      <div v-if="panel === 'chat'" class="prototype-thread">根据我的资料帮我生成一份案例 <span>⌄</span></div>
      <div class="prototype-rail-content">
        <template v-if="panel === 'chat'"><div class="prototype-chat-user">根据我的资料生成一份完整案例。</div><div class="prototype-assistant-label">AI</div><p>初稿已保存。可以打开继续编辑，或选中文字和我讨论。</p><article class="prototype-compact-card"><div><FileText :size="17" /><b>科学家精神的时代回响</b></div><p>AI 生成稿 · {{ sections.length }} 个章节</p><button class="prototype-primary" :disabled="!artifact" @click="openGenerated(); router.replace({ query: { ...route.query, variant: 'A' } })">打开稿件</button></article><article class="prototype-compact-card"><b>AI 建议 · 演示</b><p>在文末补充一项可执行的课堂讨论要求。</p><button class="prototype-primary" :disabled="tab !== 'original'" @click="acceptChatSuggestion">接受演示建议</button></article><template v-for="(message, i) in messages" :key="i"><div :class="message.kind === 'user' ? 'prototype-chat-user' : 'prototype-chat-reply'"><blockquote v-if="message.quote">{{ message.quote }}</blockquote>{{ message.text }}</div></template></template>
        <template v-else-if="panel === 'versions'"><div class="history-heading"><div><h2>历史版本</h2><span>{{ timeline.length }}</span></div><button class="history-new" :disabled="tab !== 'original'" @click="creatingVersion = !creatingVersion">＋ 创建版本</button></div><form v-if="creatingVersion" class="history-create history-create-form" @submit.prevent="createVersion"><label for="history-version-name">版本名称</label><input id="history-version-name" v-model="versionName" aria-label="版本名称" placeholder="例如：补充教学目标" autofocus /><div><button type="button" class="history-cancel" @click="creatingVersion = false">取消</button><button type="submit" class="prototype-primary">保存版本</button></div></form><div class="prototype-timeline"><article v-for="version in timeline" :key="version.id"><span class="timeline-dot" :class="{ ai: version.origin === 'AI 生成' }" /><small>{{ displayTime(version.time) }} · {{ version.origin }}</small><button class="prototype-version-card" :disabled="version.id === 'generated' && !artifact" @click="openVersion(version.id)"><Sparkles v-if="version.origin === 'AI 生成'" :size="18" /><FileText v-else :size="18" /><span><b>{{ version.title }}</b><small>打开只读历史稿</small></span></button></article></div></template>
        <template v-else-if="panel === 'comments'"><div class="prototype-list-heading"><h2>批注列表</h2><small>{{ threadList.length }} 条</small></div><button v-for="thread in threadList" :key="thread.id" class="prototype-comment-row" @click="openThread(thread.id)"><span class="comment-row-icon"><MessageSquareText :size="17" /></span><span><b>{{ thread.title }}</b><p>{{ thread.messages.filter(item => item.kind === 'human').at(-1)?.text }}</p><small>{{ thread.messages.length }} 条消息 · {{ thread.stale ? '原文已变化' : thread.resolved ? '已解决' : '待处理' }}</small></span></button></template>
      <template v-else><h2>附件</h2><p class="prototype-muted">附件入口保留。本轮仅演示历史版本与批注，不上传真实文件。</p></template></div>
      <footer v-if="panel === 'chat'" class="prototype-composer"><div v-if="chatQuote" class="prototype-quote-chip"><span>稿件选区：{{ chatQuote.slice(0, 90) }}…</span><button @click="chatQuote = ''"><X :size="13" /></button></div><div class="prototype-compose-box"><textarea v-model="chatInput" aria-label="原型对话输入" placeholder="继续讨论，或选择稿件中的文字…" @keydown.ctrl.enter="sendOpinion" /><div><span>插入 Skill⌄</span><button class="prototype-primary" :disabled="!chatInput.trim()" @click="sendOpinion">发送 ↑</button></div></div><small>{{ status || '原型演示 · 编辑和批注仅保留在本页' }}</small></footer>
    </aside>
    <div v-if="selectionQuote" class="prototype-selection-toolbar" :style="popup" @mousedown.prevent><button @click="copySelection">复制</button><button @click="askAI">就此提问</button><button v-if="tab === 'original'" @click="leaveSelectionComment">留批注</button><button v-if="tab === 'original' && commentThreads[activeThread]?.stale" @click="commentThreads[activeThread].quote = selectionQuote; commentThreads[activeThread].stale = false; selectionQuote = ''">重新定位此批注</button></div>
    <div v-if="overwriteOpen" class="prototype-pick-backdrop"><section class="prototype-pick-dialog" role="dialog" aria-label="覆盖版本警告"><h2>恢复“{{ activeTitle }}”？</h2><p class="overwrite-warning">先保存当前正文和批注，再恢复所选历史版本的正文、批注与讨论状态。恢复操作会新增记录，已有历史保持不变。</p><button class="prototype-primary" @click="overwriteVersion">确认恢复</button><button @click="overwriteOpen = false">取消</button><small class="prototype-muted">原型操作，仅本页生效</small></section></div>
    <aside v-if="floating" class="prototype-comment-float" role="dialog" aria-label="批注与关联修改"><header><div><MessageSquareText :size="16" /><b>{{ draftAnchor ? "新增批注" : "批注与修改" }}</b></div><button aria-label="关闭批注浮窗" @click="floating = false"><X :size="17" /></button></header><div class="prototype-comment-scroll"><small class="prototype-muted">{{ current?.title }}</small><p v-if="draftAnchor" class="prototype-muted">输入意见并发送后，这条批注才会加入列表。</p><article v-for="(message, i) in threadMessages" :key="i" class="prototype-thread-message"><b v-if="message.kind === 'human'">我</b><b v-else><Sparkles :size="14" />AI · 第 {{ message.round }} 轮修改</b><blockquote v-if="message.quote" class="thread-message-quote">{{ message.quote }}</blockquote><p>{{ message.text }}</p><template v-if="message.kind === 'revision'"><details><summary>修改依据与说明</summary><p>针对上方意见调整表达。淡红删除线标出原词，淡绿下划线标出建议用词。采用前保留原文。</p><p>进一步讨论时可以引用具体文字，说明要保留或继续修改的部分。每轮意见与建议都会保留；最新建议等待确认，先前建议仍可回看。这里是交互演示，未调用真实 AI。</p></details><div v-if="message.decision === 'pending' && tab === 'original'" class="prototype-floating-decisions"><button class="prototype-primary" :disabled="commentThreads[activeThread]?.stale" @click="decideRevision(message, 'accepted')"><Check :size="14" />采用并解决</button><button @click="decideRevision(message, 'rejected')">保留原文</button></div><small v-else class="prototype-resolution">{{ message.decision === 'accepted' ? '已接受修改' : message.decision === 'rejected' ? '已保留原文' : '已有后续建议 · 保留供回看' }}</small></template></article></div><footer v-if="tab === 'original'"><p v-if="commentThreads[activeThread]?.stale" class="overwrite-warning">原文已变化，请重新选中文字定位。</p><button v-if="activeThread" @click="resolveThread">仅解决</button><div v-if="threadQuote" class="prototype-quote-chip"><span>引用选区：{{ threadQuote.slice(0, 120) }}</span><button @click="threadQuote = ''"><X :size="13" /></button></div><textarea v-model="note" aria-label="原型批注意见" placeholder="继续讨论，例如：前半句保留，只改后半句…" /><button class="prototype-primary" :disabled="!note.trim()" @click="addOpinion(false)">保存意见</button><button class="prototype-primary" :disabled="!note.trim()" @click="addOpinion(true)">发送给 AI（演示）</button></footer></aside>
    <div class="prototype-switcher"><span>交互原型 · {{ versions.length }} 版本 / {{ Object.keys(commentThreads).length }} 批注 · {{ tab === "original" ? "当前稿" : "只读历史" }}</span><button @click="switchVariant"><ArrowLeft :size="16" /></button><b>{{ variant === 'A' ? 'A · 版本与编辑' : 'B · 浮动批注精修' }}</b><button @click="switchVariant"><ArrowRight :size="16" /></button></div>
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

.prototype-version-tabs { min-width:0; gap:0; padding-right:6px; }
.prototype-version-tabs .pinned-teacher-tab { flex-shrink:0; white-space:nowrap; }
.prototype-open-tabs { display:flex; overflow-x:auto; min-width:0; flex:1; align-self:stretch; scrollbar-width:thin; }
.prototype-tab-chip { display:flex; flex-shrink:0; align-items:center; border-radius:7px 7px 0 0; max-width:210px; }
.prototype-tab-chip > button:first-child { white-space:nowrap; overflow:hidden; text-overflow:ellipsis; padding-right:5px; display:block; }
.prototype-tab-chip.active { background:white; box-shadow:0 -2px 0 var(--brand) inset; }
.prototype-tab-chip.active > button { color:var(--brand); }
.prototype-tab-chip .close-version-tab { padding:7px; margin-right:4px; border-radius:4px; }
.prototype-tab-chip .close-version-tab:hover { background:#eee8de; }
.prototype-version-tabs .version-save-entry, .prototype-version-tabs .version-history-entry { flex-shrink:0; white-space:nowrap; padding:12px 9px; }

.history-hover-zone { position: sticky; top: 0; z-index: 5; background: #faf8f3; border-radius: 10px; }
.history-handle { width:100%; height:26px; border:0; background:transparent; color:#998b78; font-size:11px; cursor:pointer; }
.history-collapse { display:grid; grid-template-rows:0fr; opacity:0; transition:grid-template-rows .22s ease, opacity .22s ease; }
.history-collapse.expanded { grid-template-rows:1fr; opacity:1; }
.history-collapse > .prototype-version-tabs { min-height:0; overflow:hidden; margin:0; padding:0 10px; }
.history-collapse.expanded > .prototype-version-tabs { padding:10px; }
.history-create { display:flex; gap:8px; }
.history-create input { min-width:0; width:60%; padding:8px; border:1px solid #ded4c3; border-radius:6px; }
.prototype-document-note button { margin-left:10px; color:var(--brand); border:0; background:transparent; }
.prototype-comment-float footer > button { margin:4px; }

.prototype-assistant > header { display:grid; grid-template-columns: .8fr 1.35fr 1fr 1fr; gap:0; padding:0 12px; flex-shrink:0; }
.prototype-assistant > header button { justify-content:center; gap:6px; padding:17px 5px; white-space:nowrap; font-size:14px; }
.history-hover-zone { border:1px solid #ebe5dc; background:rgba(255,255,255,.94); border-radius:12px; box-shadow:0 3px 12px #392c1606; }
.history-handle { height:30px; display:flex; align-items:center; gap:9px; padding:0 16px; text-align:left; color:#7d7264; }
.history-grip { width:20px; height:3px; border-radius:3px; background:#d8cbb9; }
.history-count { margin-left:auto; color:#a49889; font-size:10px; }
.history-collapse > .prototype-version-tabs { border:0; box-shadow:none; border-radius:0 0 12px 12px; background:transparent; }
.history-collapse.expanded > .prototype-version-tabs { padding:6px 10px 10px; }
.prototype-version-tabs button { border-radius:7px; font-size:12px; }
.prototype-tab-chip.active { background:#fff3f2; }
.prototype-rail-content { padding:20px; }
.prototype-list-heading h2 { font-size:18px; }
.prototype-timeline { margin-top:22px; }
.prototype-assistant > .prototype-rail-content { flex:1; }

.history-heading { display:flex; align-items:center; justify-content:space-between; gap:12px; padding:2px 0 18px; border-bottom:1px solid #ece6dd; }
.history-heading > div { display:flex; align-items:center; gap:8px; }
.history-heading h2 { margin:0; font-size:15px; font-weight:600; letter-spacing:.02em; }
.history-heading span { font-size:11px; color:#968c7e; background:#f0ece5; padding:1px 7px; border-radius:10px; }
.history-new { border:1px solid #e6d9cf; border-radius:6px; padding:7px 10px; background:#fffdfa; color:#a72228; font-size:12px; cursor:pointer; }
.history-new:hover { background:#fff3f0; border-color:#d6b5ac; }
.history-new:disabled { opacity:.45; cursor:default; }
.history-create-form { display:flex; flex-direction:column; gap:10px; background:#fff; padding:14px; margin-top:14px; border:1px solid #e8e0d6; border-radius:8px; }
.history-create-form label { color:#6e6256; font-size:12px; }
.history-create-form input { box-sizing:border-box; width:100%; font-size:12px; padding:9px 10px; }
.history-create-form > div { display:flex; gap:8px; justify-content:flex-end; }
.history-create-form button { padding:6px 12px; font-size:12px; border-radius:5px; }
.history-cancel { border:1px solid #e8e0d6; background:white; color:#7b7064; }
</style>
