<script setup>
// 原型主组件：组装品牌行/菜单/双排工具栏 + 目录/纸面/批注轨 + AI面板/工具轨。
// 所有 AI 请求经 /prototype-ai 代理到真实模型；文档与会话仅存内存。
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";
import {
  Bold, FolderOpen, Heading2, History, List, ListOrdered, MessageSquarePlus,
  Pilcrow, Redo2, Sparkles, Undo2, Wand2, PanelLeft, PanelRightClose, PanelRightOpen,
} from "@lucide/vue";
import { store, activeThread, newThread } from "./store.js";
import { findTextRange, mapAnchor, mapRevision, annotationQuote } from "./text-range.js";
import { useAnnotationLayout } from "./annotation-layout.js";
import { streamChat } from "./ai-client.js";
import PaperEditor from "./PaperEditor.vue";
import AnnotationLane from "./components/AnnotationLane.vue";
import AiPane from "./components/AiPane.vue";
import RailPanes from "./components/RailPanes.vue";
import AiCommandMenu from "./components/AiCommandMenu.vue";

const paperRef = ref(null);
const aiPaneRef = ref(null);
const aiMenuOpen = ref(false);
const activeAnnId = ref("");
const outlineCollapsed = ref(window.innerWidth < 1600);
const annotationDraft = ref(null);
const aiMenuPosition = ref({});
const toast = ref("");
let toastTimer = 0;

const railTabs = [
  { id: "ai", label: "AI 对话", icon: Sparkles },
  { id: "history", label: "会话历史", icon: History },
  { id: "review", label: "修改审阅", icon: Wand2 },
  { id: "resources", label: "资料", icon: FolderOpen },
];

const docEpoch = ref(0);
const outlines = computed(() => {
  void docEpoch.value;
  const ed = paperRef.value?.editor;
  if (!ed) return [];
  const items = [];
  ed.state.doc.descendants((node) => {
    if (node.type.name === "heading" && node.attrs.level <= 2) {
      items.push({ level: node.attrs.level, text: node.textContent });
    }
  });
  return items;
});

const editor = () => paperRef.value?.editor;

const snapshot = computed(() => ({
  annotations: store.annotations,
  revisions: store.annotations.filter((a) => a.kind === "revision" && a.id === store.ui.previewId),
  chip: store.selectionChip,
}));
function safeActive(t) {
  try { return Boolean(t.active?.(editor())); } catch { return false; }
}
function onAskAi(selection) {
  attachChip(selection);
  store.ui.aiCollapsed = false; // 问AI自动展开面板，避免输入落到不可见区
  store.railTab = "ai";
  nextTick(() => aiPaneRef.value?.focusComposer());
}
function onDocChange(transaction) {
  docEpoch.value++;
  if (transaction?.docChanged) {
    for (const ann of store.annotations) {
      if (ann.kind === "revision") mapRevision(transaction, ann);
      else mapAnchor(transaction, ann, ann.anchorQuote);
    }
    const pending = store.runningJob?.revisionAnchor;
    if (pending) mapAnchor(transaction, pending, pending.quote);
    for (const anchor of [store.selectionChip, store.pendingSelection, annotationDraft.value]) {
      if (anchor) mapAnchor(transaction, anchor, anchor.quote);
    }
  }

}
const docPlainText = () => editor()?.state.doc.textBetween(0, editor().state.doc.content.size, "\n") || "";

function showToast(text) {
  toast.value = text;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { toast.value = ""; }, 2600);
}

// —— AI 配置加载（真实模型清单） ——
onMounted(async () => {
  try {
    const res = await fetch("/prototype-ai/config");
    if (!res.ok) throw new Error((await res.json()).message || `HTTP ${res.status}`);
    const cfg = await res.json();
    store.aiConfig = { ...cfg, ready: true, error: "" };
    store.modelId = cfg.defaultModel || cfg.models[0] || "";
    store.runningJob = null;
  } catch (error) {
    store.aiConfig = { models: [], defaultModel: "", thinking: {}, ready: false, error: String(error.message || error) };
  }
  if (!store.threads.length) newThread();
});
onBeforeUnmount(() => store.runningJob?.controller?.abort());

// —— 选区上下文 ——
function onSelectionChange(ed) {
  const { from, to, empty } = ed.state.selection;
  if (empty || from === to) return;
  const quote = ed.state.doc.textBetween(from, to, " ");
  if (quote.trim()) store.pendingSelection = { quote, from, to };
}
function attachChip(selection) {
  store.selectionChip = selection ? { ...selection, range: selection.range || { from: selection.from, to: selection.to } } : null;
  paperRef.value?.refresh();
}
function locateChip() {
  if (!store.selectionChip) return;
  const ok = paperRef.value.focusQuote(store.selectionChip.quote, store.selectionChip.range);
  if (!ok) showToast("原文已变化，定位失败");
}
function removeChip() {
  store.selectionChip = null;
  paperRef.value?.refresh();
}

// —— 批注 ——
const findAnnotationRange = findTextRange;
const { lane, lanePlaceholder, schedule: remeasureLane } = useAnnotationLayout(editor);

const sourceAnnotation = (item) => store.annotations.find((annotation) => annotation.id === item.id) || item;

// 展开（同时只一条）：展开并滚动定位原文；再次点击收起（不移动正文位置）。
function toggleAnnotation(ann) {
  const target = sourceAnnotation(ann);
  if (store.ui.expandedAnnId === target.id) {
    store.ui.expandedAnnId = "";
    return;
  }
  store.ui.expandedAnnId = target.id;
  activeAnnId.value = target.id;
  if (target.anchorQuote) {
    const ok = paperRef.value?.focusQuote(annotationQuote(target), target.range);
    if (!ok) showToast("原文已变化，锚点失效");
  }
}
function locateAnnotation(ann) {
  activeAnnId.value = ann.id;
  const ok = paperRef.value.focusQuote(ann.anchorQuote, ann.range);
  if (!ok) showToast("原文已变化，锚点失效");
}
function resolveAnnotation(ann) {
  const target = sourceAnnotation(ann);
  target.resolved = !target.resolved;
  paperRef.value?.refresh();
}
function replyAnnotation({ item, text }) {
  const target = sourceAnnotation(item);
  (target.replies ||= []).push({ id: crypto.randomUUID(), author: "我", time: "刚刚", text });
}
function addAnnotation(selection) {
  if (!selection?.quote) return;
  annotationDraft.value = { ...selection, range: selection.range || { from: selection.from, to: selection.to }, text: "" };
  store.ui.expandedAnnId = "";
}
function saveAnnotation(text) {
  const selection = annotationDraft.value;
  if (selection.anchorMissing) { showToast("原文已变化，请重新选择批注内容"); return; }
  const id = `a${Date.now()}`;
  store.annotations.push({ id, author: "我", time: "刚刚", kind: "comment",
    anchorQuote: selection.quote, range: selection.range,
    text, resolved: false, replies: [] });
  annotationDraft.value = null;
  store.ui.expandedAnnId = id;
  paperRef.value?.refresh();
}
function previewRevision(item) {
  store.ui.previewId = store.ui.previewId === item.id ? "" : item.id;
  paperRef.value?.refresh();
}

// —— 修订采用/拒绝（可撤销：接受写入正文并进入撤销历史；拒绝只改状态） ——
function acceptRevision(rev) {
  const target = sourceAnnotation(rev);
  const ed = editor();
  target.range = target.anchorMissing ? null : findTextRange(ed.state.doc, target.original, target.range);
  if (!target.range) {
    showToast("原文已变化，修订失效");
    target.status = "stale";
    paperRef.value?.refresh();
    return;
  }
  ed.chain().focus().insertContentAt(target.range, { type: "text", text: target.replacement }).run();
  store.ui.previewId = "";
  target.status = "accepted";
  paperRef.value?.refresh();
  showToast("已采用修订（Ctrl+Z 可撤销）");
}
function rejectRevision(rev) {
  sourceAnnotation(rev).status = "rejected";
  store.ui.previewId = "";
  paperRef.value?.refresh();
  showToast("已拒绝修订");
}

// —— AI 执行（真实模型） ——
function baseMessages(extra) {
  const doc = docPlainText();
  return [
    { role: "system", content: "你是高校思政教学案例写作助手。回答用中文，简洁务实。当前是交互原型：文档仅存于内存。" },
    { role: "system", content: `教学案例正文：\n${doc}` },
    ...extra,
  ];
}

function startJob(kind) {
  const job = { id: Date.now(), startedAt: performance.now(), kind, controller: new AbortController() };
  job.timer = setInterval(() => {
    store.elapsedTick++;
    job.elapsed = performance.now() - job.startedAt;
  }, 100);
  store.runningJob = job;
  return job;
}
function finishJob(job) {
  clearInterval(job.timer);
  if (store.runningJob?.id === job.id) store.runningJob = null;
}

async function summarizeTitle(thread, firstUserText, replyText) {
  if (thread.auto && thread.title !== "新会话") return; // 手动改名后不覆盖
  try {
    const { text } = await streamChat({
      model: store.modelId || store.aiConfig.defaultModel,
      messages: [
        { role: "system", content: "用不超过 12 个汉字概括这次对话主题，只输出标题本身，不要标点。" },
        { role: "user", content: `用户：${firstUserText.slice(0, 300)}\n助手：${replyText.slice(0, 300)}` },
      ],
      signal: AbortSignal.timeout(30000),
    });
    const title = text.trim().split("\n")[0].slice(0, 16);
    if (title && !thread.manualRenamed) {
      thread.title = title;
      thread.auto = true;
      thread.titleAnimation = true; // 一次性动画；历史重开不重复
    }
  } catch { /* 标题失败不阻塞对话 */ }
}

function prepareChat(args) {
  const { text, skills, quote, mode = "chat", revisionOf, requestText = text } = args;
  const thread = activeThread() || (newThread(), activeThread());
  const job = startJob(mode);
  job.threadId = thread.id;
  job.revisionAnchor = args.revisionAnchor;
  const started = performance.now();
  const userMsg = { role: "user", text, requestText, quote: quote || store.selectionChip?.quote || "", skills: skills || [] };
  if (mode === "chat") thread.messages.push(userMsg);
  const history = thread.messages.filter((m) => m.role === "user" || m.role === "assistant").filter((m) => !m.error)
    .map((m) => ({ role: m.role, content: (m.quote ? `引用：“${m.quote}”\n` : "") + (m.requestText || m.text) }));
  const assistantMsg = reactive({ role: "assistant", text: "", reasoning: "", model: store.modelId || store.aiConfig.defaultModel });
  if (mode === "chat") thread.messages.push(assistantMsg);
  else { Object.assign(assistantMsg, { role: "revision-card", status: "pending", original: revisionOf, text: "" }); thread.messages.push(assistantMsg); }
  assistantMsg.retryArgs = { ...args };
  return { thread, job, started, mode, text, revisionOf, history, assistantMsg, append: args.append };
}

async function requestModel(state) {
  const reviseMode = state.mode === "revise";
  return streamChat({
    model: state.assistantMsg.model, thinking: store.thinking && !reviseMode, signal: state.job.controller.signal,
    messages: reviseMode ? [
      { role: "system", content: "你是文本改写器，严格只输出改写后的文字本身，禁止解释、点评、前言或引号。" },
      { role: "user", content: state.text },
    ] : baseMessages(state.history),
    onDelta: (text) => { state.assistantMsg.text = text; },
    onReasoning: (reasoning) => { state.assistantMsg.reasoning = reasoning; },
  });
}

function recordRevision(result, state) {
  if (state.mode !== "revise") return;
  const output = result.text.trim().replace(/^["“]|["”]$/g, "");
  const cleaned = state.append ? state.revisionOf + output : output;
  state.assistantMsg.replacement = cleaned;
  if (!state.revisionOf || !cleaned) return;
  const id = `rev${Date.now()}`;
  state.assistantMsg.annotationId = id;
  store.annotations.push({
    id, author: "AI 助手", time: "刚刚", kind: "revision", status: state.job.revisionAnchor?.anchorMissing ? "stale" : "pending",
    anchorQuote: state.revisionOf, original: state.revisionOf, replacement: cleaned, range: state.job.revisionAnchor?.range || findTextRange(editor().state.doc, state.revisionOf), anchorMissing: state.job.revisionAnchor?.anchorMissing || false,
    reason: "由 AI 命令生成（真实模型）", resolved: false, replies: [],
  });
  store.ui.previewId = id;
  store.ui.expandedAnnId = id; // 新修订自动展开便于采用/拒绝，其余收起
  paperRef.value?.refresh();
}

function markChatError(error, state) {
  state.assistantMsg.ms = performance.now() - state.started;
  if (state.job.controller.signal.aborted) state.assistantMsg.aborted = true;
  state.assistantMsg.error = String(error.message || error);
}

async function runChat(args) {
  if (store.runningJob) { showToast("请等待当前回复完成，或先停止生成"); return; }
  store.ui.aiCollapsed = false;
  store.railTab = "ai";
  const state = prepareChat(args);
  try {
    const result = await requestModel(state);
    state.assistantMsg.ms = performance.now() - state.started;
    recordRevision(result, state);
    if (state.mode === "chat" && !state.thread.auto) summarizeTitle(state.thread, state.text, result.text);
    showToast("AI 回复完成");
  } catch (error) { markChatError(error, state); } finally { finishJob(state.job); }
}

async function onSend(payload) {
  if (payload.retry) {
    const idx = activeThread().messages.indexOf(payload.retry);
    if (idx >= 0) activeThread().messages.splice(Math.max(0, idx - 1), 2);
    return runChat(payload.retry.retryArgs);
  }
  if (payload.via === "suggestion") {
    return runChat({ text: payload.text, mode: "chat" });
  }
  // 发送前快照选区引用：清 chip 后历史消息仍保留 quote（同一 quote 也作为模型上下文）。
  const quote = store.selectionChip?.quote || "";
  attachChip(null);
  await runChat({ text: payload.text, skills: payload.skills, quote, mode: "chat" });
}

function stopJob() {
  store.runningJob?.controller?.abort();
  showToast("已停止生成");
}

// —— AI 命令菜单分发：prefill / chat / revise ——
function prefillCommand(selection) {
  if (selection) attachChip(selection);
  store.ui.aiCollapsed = false;
  store.railTab = "ai";
  store.composerDraft = store.composerDraft ? `${store.composerDraft}\n` : "";
  nextTick(() => aiPaneRef.value?.focusComposer());
  showToast("已带入选区，输入后发送");
}

function commandQuote(selection) {
  return selection?.quote || store.selectionChip?.quote;
}

function commandPrompt(item, quote) {
  return quote ? `${item.prompt}\n引用：“${quote}”` : `${item.prompt}\n${docPlainText().slice(0, 800)}`;
}

function revisionPrompt(item, quote) {
  const instruction = item.prompt || "请改写下面这段教学案例文字，保持事实与语气。";
  return `${instruction}\n严格只输出改写后的文字本身：不要任何解释、点评、前言、引号或标注重复。直接输出替换文本。\n原文：${quote}`;
}

async function onCommandRun({ item, selection }) {
  aiMenuOpen.value = false;
  if (item.mode === "prefill") { prefillCommand(selection); return; }
  const quote = commandQuote(selection);
  if (item.mode === "chat") return runChat({ text: item.label, requestText: commandPrompt(item, quote), quote, mode: "chat" });
  if (!quote) { showToast("请先选中要修改的文字"); return; }
  const target = selection || store.selectionChip;
  const range = target?.range || { from: target.from, to: target.to };
  if (target?.anchorMissing || !findTextRange(editor().state.doc, quote, range)) { showToast("原文已变化，请重新选择修改范围"); return; }
  return runChat({ text: revisionPrompt(item, quote), mode: "revise", revisionOf: quote, revisionAnchor: { quote, range }, append: item.id === "continue" });
}

function openThread(t) {
  if (activeThread()) { activeThread().draft = store.composerDraft; activeThread().selectionChip = store.selectionChip; }
  store.activeThreadId = t.id;
  attachChip(t.selectionChip || null);
  store.composerDraft = t.draft || "";
  store.railTab = "ai";
  store.ui.aiCollapsed = false;
}
watch(() => store.activeThreadId, () => {
  const t = activeThread();
  if (t) store.composerDraft = t.draft || "";
  store.railTab = "ai";
  store.ui.aiCollapsed = false;
});
watch(() => store.composerDraft, (v) => { const t = activeThread(); if (t) t.draft = v; });

function onNewThread() {
  if (activeThread()) activeThread().selectionChip = store.selectionChip;
  newThread();
  attachChip(null);
  store.railTab = "ai";
  store.ui.aiCollapsed = false;
}

function runFormat(fn) {
  const ed = editor();
  if (ed) fn(ed);
}
// 侧轨 tab：AI tab 收起态下即恢复面板；其余 tab 打开各自浮层，再点回 AI。
function onRailTab(id) {
  store.ui.aiCollapsed = store.railTab === id && !store.ui.aiCollapsed;
  store.railTab = id;
}
function openAiMenu(event) {
  const rect = event?.rect || event?.currentTarget?.getBoundingClientRect?.();
  aiMenuPosition.value = rect ? { left: `${Math.min(rect.left, innerWidth - 290)}px`, top: `${Math.max(90, Math.min(rect.bottom + 8, innerHeight - 460))}px` } : {};
  if (event?.quote) store.pendingSelection = event;
  aiMenuOpen.value = !aiMenuOpen.value;
}
const toolbarRow1 = [
  { icon: MessageSquarePlus, title: "批注（选中文字后）", run: () => onAnnotateFromToolbar() },
];
const toolbarRow2 = [
  { icon: Bold, title: "加粗", active: (ed) => ed.isActive("bold"), run: (ed) => ed.chain().focus().toggleBold().run() },
  { icon: Heading2, title: "二级标题", active: (ed) => ed.isActive("heading", { level: 2 }), run: (ed) => ed.chain().focus().toggleHeading({ level: 2 }).run() },
  { icon: Pilcrow, title: "正文", run: (ed) => ed.chain().focus().setParagraph().run() },
  { icon: List, title: "项目列表", active: (ed) => ed.isActive("bulletList"), run: (ed) => ed.chain().focus().toggleBulletList().run() },
  { icon: ListOrdered, title: "编号列表", active: (ed) => ed.isActive("orderedList"), run: (ed) => ed.chain().focus().toggleOrderedList().run() },
  { icon: Undo2, title: "撤销", run: (ed) => ed.chain().focus().undo().run() },
  { icon: Redo2, title: "重做", run: (ed) => ed.chain().focus().redo().run() },
];

function onAnnotateFromToolbar() {
  const sel = store.pendingSelection;
  if (!sel?.quote) { showToast("请先选中文字"); return; }
  addAnnotation(sel);
}
</script>

<template>
  <div class="wb">
    <header class="brand-row">
      <img src="/logo.png" alt="上海大学" class="brand-logo" />
      <span class="brand-title">思政教学案例库 · 工作台</span>
      <span class="proto-badge">交互原型 · 数据仅存内存</span>
      <span class="brand-right">
        <span class="doc-status">{{ store.doc.status }}</span>
        <span class="doc-save">{{ store.doc.savedAt }}</span>
        <span class="brand-user">王老师（演示）</span>
      </span>
    </header>
    <div class="toolbar-row main-toolbar" role="toolbar" aria-label="文档格式">
      <button type="button" title="文档目录" aria-label="文档目录" :aria-expanded="!outlineCollapsed" @click="outlineCollapsed = !outlineCollapsed"><PanelLeft :size="16" /></button>
      <span class="toolbar-divider" />
      <button v-for="t in toolbarRow2" :key="t.title" type="button" :title="t.title" :class="{ active: editor()?.isActive && safeActive(t) }" @mousedown.prevent @click="runFormat(t.run)"><component :is="t.icon" :size="15" /></button>
      <span class="toolbar-divider" />
      <button v-for="t in toolbarRow1" :key="t.title" type="button" :title="t.title" @mousedown.prevent @click="t.run()"><component :is="t.icon" :size="15" /></button>
      <button type="button" class="ai-cmd-btn" title="AI 命令菜单" @click="openAiMenu"><Sparkles :size="15" /><span class="caret" /></button>
    </div>
    <div class="workspace" :class="{ 'outline-collapsed': outlineCollapsed, 'ai-collapsed': store.ui.aiCollapsed }">
      <aside class="outline-pane">
        <button type="button" class="outline-toggle" title="折叠目录" @click="outlineCollapsed = true"><span class="chev" /></button>
        <b class="outline-label">文档目录</b>
        <ul>
          <li v-for="(o, i) in outlines" :key="i" :class="`level-${o.level}`">
            <button type="button" @click="paperRef?.focusQuote(o.text)">{{ o.text }}</button>
          </li>
        </ul>
      </aside>


      <main class="doc-area">
        <div class="paper-scroll">
          <div class="document-paper">
            <h1 class="doc-title">{{ store.doc.title }}</h1>
            <p class="doc-byline">{{ store.doc.byline }}</p>
            <PaperEditor ref="paperRef" :snapshot="snapshot" @selection-change="onSelectionChange" @annotate="addAnnotation" @ask-ai="onAskAi" @doc-change="onDocChange" @anchor="toggleAnnotation" @open-ai-menu="openAiMenu" />
          </div>
          <AnnotationLane :items="lane" :active-id="activeAnnId" :expanded-id="store.ui.expandedAnnId" :placeholder-height="lanePlaceholder" :draft="annotationDraft" :preview-id="store.ui.previewId" @save="saveAnnotation" @cancel="annotationDraft = null" @preview="previewRevision" @toggle="toggleAnnotation" @resolve="resolveAnnotation" @reply="replyAnnotation" @accept="acceptRevision" @reject="rejectRevision" />
        </div>
      </main>

      <section id="assistant-panel" class="assist-area" :inert="store.ui.aiCollapsed" :aria-hidden="store.ui.aiCollapsed">
        <AiPane ref="aiPaneRef" v-show="store.railTab === 'ai'"
          @send="onSend"
          @preview="previewRevision" @accept="acceptRevision" @reject="rejectRevision"
          @stop="stopJob"
          @locate-chip="locateChip"
          @remove-chip="removeChip"
          @new-thread="onNewThread"
          @open-ai-menu="openAiMenu"
        />
        <div v-show="store.railTab !== 'ai'" class="auxiliary-panel">
          <RailPanes :tab="store.railTab" @open-thread="openThread" @new-thread="onNewThread" @preview="previewRevision" @accept="acceptRevision" @reject="rejectRevision" />
        </div>
      </section>

      <nav class="tool-rail" aria-label="辅助功能">
        <button type="button" class="panel-toggle" :title="store.ui.aiCollapsed ? '展开右侧面板' : '收起右侧面板'"
          :aria-label="store.ui.aiCollapsed ? '展开右侧面板' : '收起右侧面板'" :aria-expanded="!store.ui.aiCollapsed"
          aria-controls="assistant-panel" @click="store.ui.aiCollapsed = !store.ui.aiCollapsed">
          <component :is="store.ui.aiCollapsed ? PanelRightOpen : PanelRightClose" :size="17" />
          <span>{{ store.ui.aiCollapsed ? '展开' : '收起' }}</span>
        </button>
        <button v-for="t in railTabs" :key="t.id" type="button" :class="{ active: store.railTab === t.id && !store.ui.aiCollapsed }" :title="store.ui.aiCollapsed ? `展开${t.label}` : t.label" :aria-label="t.label" :aria-expanded="store.railTab === t.id && !store.ui.aiCollapsed" aria-controls="assistant-panel" @click="onRailTab(t.id)">
          <component :is="t.icon" :size="17" />
        </button>
      </nav>

    </div>

    <AiCommandMenu v-if="aiMenuOpen" class="ai-menu-float" :style="aiMenuPosition" :command="{ selection: store.pendingSelection }" @close="aiMenuOpen = false" @run="onCommandRun" />
    <Transition name="toast"><div v-if="toast" class="toast" role="status">{{ toast }}</div></Transition>
  </div>
</template>
