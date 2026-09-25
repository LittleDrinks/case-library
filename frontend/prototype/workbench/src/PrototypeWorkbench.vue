<script setup>
// 原型主组件：组装品牌行/工具栏、目录/纸面、AI面板/工具轨。
// 所有 AI 请求经 /prototype-ai 代理到真实模型；文档与会话仅存内存。
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";
import {
  Bold, Heading2, History, List, ListOrdered,
  Pilcrow, Redo2, Sparkles, Undo2, Wand2, PanelLeft, PanelRightClose, PanelRightOpen,
} from "@lucide/vue";
import { store, activeThread, newThread } from "./store.js";
import { findTextRange, mapAnchor, mapRevision } from "./text-range.js";
import { streamChat } from "./ai-client.js";
import PaperEditor from "./PaperEditor.vue";
import AiPane from "./components/AiPane.vue";
import RailPanes from "./components/RailPanes.vue";
import OutlinePanel from "../../../src/components/OutlinePanel.vue";

const paperRef = ref(null);
const aiPaneRef = ref(null);
const outlineCollapsed = ref(window.innerWidth < 1600);
const toast = ref("");
let toastTimer = 0;

const railTabs = [
  { id: "ai", label: "AI 对话", icon: Sparkles },
  { id: "history", label: "会话历史", icon: History },
  { id: "review", label: "修改审阅", icon: Wand2 },
];

const docEpoch = ref(0);
const outlines = computed(() => {
  void docEpoch.value;
  const ed = paperRef.value?.editor;
  if (!ed) return [];
  const items = [];
  ed.state.doc.descendants((node, pos) => {
    if (node.type.name === "heading" && node.attrs.level <= 2) {
      items.push({ index: pos, level: node.attrs.level, text: node.textContent, range: { from: pos + 1, to: pos + 1 + node.content.size } });
    }
  });
  return items;
});

function locateOutline(index) {
  const heading = outlines.value[index];
  if (!heading) return;
  paperRef.value?.focusQuote(heading.text, heading.range);
  nextTick(() => {
    const view = paperRef.value?.editor?.view;
    const dom = view?.nodeDOM(heading.index);
    dom?.scrollIntoView({ block: "start", behavior: "auto" });
  });
}
const editor = () => paperRef.value?.editor;

const snapshot = computed(() => ({
  revisions: store.revisions.filter((a) => a.kind === "revision" && a.id === store.ui.previewId),
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
    for (const ann of store.revisions) {
      mapRevision(transaction, ann);
    }
    const pending = store.runningJob?.revisionAnchor;
    if (pending) mapAnchor(transaction, pending, pending.quote);
    for (const anchor of [store.selectionChip, store.pendingSelection]) {
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
  if (store.editDemo) {
    store.aiConfig = { models: ["模拟结果"], defaultModel: "模拟结果", ready: true, error: "" };
    store.modelId = "模拟结果";
    return;
  }
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

const sourceRevision = (item) => store.revisions.find((revision) => revision.id === item.id) || item;

function reloadDemo() { location.reload(); }

function generateDemoRevision() {
  const ed = editor();
  if (!ed) return;
  const examples = [
    { prefix: "1931 年", label: "开头 · 压缩叙述", reason: "开头同时堆叠了入学成绩、转系经过和人物引语，主线容易被细节打断。这里压缩背景，保留专业选择与国家需要的联系，再用一个问题衔接课堂讨论。", replacement: "1931 年，钱伟长考入清华大学历史系。九一八事变后，他决定转学物理，希望以自己的专业选择回应国家需要。课堂可以由此追问：个人志向与时代需要之间，应当怎样作出选择？" },
    { prefix: "本案例选取", label: "教学目标 · 明确学习任务", reason: "原段说明了选材和教学意图，但学生具体要做什么还不清楚。改为找出选择、提取证据、比较解释三个动作，便于老师组织活动，也便于检查学生是否完成任务。", replacement: "本案例以转系决定与办学实践为两条主线。学生阅读材料后，分别找出人物面临的选择、支持判断的证据和可能的其他解释，再用一段话说明个人发展与国家需要的关系。" },
    { prefix: "1983 年", label: "办学实践 · 增加分析角度", reason: "原段主要介绍办学理念，最后直接概括其落实到每个环节，缺少可供学生分析的具体任务。保留“四堵墙”的内容，让学生任选一项解释障碍并提出改进办法，把人物介绍转为课堂活动。", replacement: "1983 年，钱伟长出任上海工业大学校长，提出拆除学校与社会、教学与科研、专业之间以及教与学之间的“四堵墙”。阅读这段材料时，可让学生任选一堵“墙”，解释它为什么妨碍学习，并提出一种可以在今天的校园中尝试的改进办法。" },
    { prefix: "讨论二：", label: "讨论问题 · 加入具体情境", reason: "原问题容易停留在“是否矛盾”的抽象表态。换成选择非热门专业的具体处境，并要求回应不同意见，让学生有情境可分析、有理由可比较。", replacement: "讨论二：如果你喜欢的专业暂时不属于热门领域，你会如何判断它与社会需要的关系？请结合案例，提出自己的选择及理由，并回应一种不同意见。" },
    { prefix: "课后作业", label: "课后作业 · 明确交付成果", reason: "原作业规定了访谈对象和字数，但没有说明应收集什么材料。补上研究问题、现实需求和访谈原话，并要求区分事实与判断，使访谈成果更容易交流和评价。", replacement: "课后两人一组访谈一位本校教师，记录一个研究问题、它回应的现实需求，以及访谈中的一句原话。形成八百字短文，区分访谈事实与自己的判断，下节课用三分钟交流。" },
  ];
  const candidates = [];
  ed.state.doc.descendants((node, pos) => {
    if (node.type.name !== "paragraph") return;
    const example = examples.find((item) => node.textContent.startsWith(item.prefix));
    if (!example || store.revisions.some((item) => item.original === node.textContent && item.status === "pending")) return;
    candidates.push({ id: crypto.randomUUID(), kind: "revision", original: node.textContent, anchorQuote: node.textContent,
      range: { from: pos + 1, to: pos + 1 + node.content.size }, replacement: example.replacement,
      status: "pending", title: example.label, reason: example.reason, anchorMissing: false });
  });
  if (!candidates.length) { showToast("建议已生成；可重新开始再体验"); return; }
  store.revisions.push(...candidates);
  activeThread().messages.push({ role: "user", text: "请把叙述、教学任务和讨论题改得更具体，逐处给出修改建议。" },
    ...candidates.map((item) => ({ role: "revision-card", revisionId: item.id, simulated: true })));
  store.ui.aiCollapsed = false;
  store.railTab = "ai";
  showToast(`已生成 ${candidates.length} 处模拟建议，点击卡片查看正文预览`);
}

function activateRevision(item) {
  if (item.status !== "pending") return;
  const ed = editor();
  const range = item.anchorMissing ? null : findTextRange(ed.state.doc, item.original, item.range);
  if (!range) { showToast("原文已变化，请重新生成修改建议"); return; }
  const newlySelected = store.ui.previewId !== item.id;
  store.ui.previewId = item.id;
  paperRef.value?.refresh();
  if (!newlySelected) return;
  nextTick(() => {
    const scroller = ed.view.dom.closest(".paper-scroll");
    const top = ed.view.coordsAtPos(range.from).top;
    if (scroller) scroller.scrollTo({ top: Math.max(0, scroller.scrollTop + top - scroller.getBoundingClientRect().top - 96), behavior: "auto" });
  });
}

function previewRevision(item) {
  store.ui.previewId = store.ui.previewId === item.id ? "" : item.id;
  if (store.ui.previewId) paperRef.value?.focusQuote(item.original, item.range);
  paperRef.value?.refresh();
}

// —— 修订采用/拒绝（可撤销：接受写入正文并进入撤销历史；拒绝只改状态） ——
function acceptRevision(rev) {
  const target = sourceRevision(rev);
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
  sourceRevision(rev).status = "rejected";
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
  state.assistantMsg.revisionId = id;
  store.revisions.push({
    id, author: "AI", time: "刚刚", kind: "revision", status: state.job.revisionAnchor?.anchorMissing ? "stale" : "pending",
    anchorQuote: state.revisionOf, original: state.revisionOf, replacement: cleaned, range: state.job.revisionAnchor?.range || findTextRange(editor().state.doc, state.revisionOf), anchorMissing: state.job.revisionAnchor?.anchorMissing || false,
    reason: "由 AI 命令生成（真实模型）",
  });
  store.ui.previewId = id;
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
  if (store.editDemo) { generateDemoRevision(); return; }
  if (payload.retry) {
    const idx = activeThread().messages.indexOf(payload.retry);
    if (idx >= 0) activeThread().messages.splice(Math.max(0, idx - 1), 2);
    return runChat(payload.retry.retryArgs);
  }
  if (payload.revise) {
    const target = store.selectionChip;
    const range = target?.range || { from: target?.from, to: target?.to };
    if (!target?.quote || target.anchorMissing || !findTextRange(editor().state.doc, target.quote, range)) {
      showToast("请重新选择要修改的正文"); return;
    }
    return runChat({ text: `${payload.text}\n原文：${target.quote}`, mode: "revise", revisionOf: target.quote, revisionAnchor: { quote: target.quote, range } });
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
const toolbarRow2 = [
  { icon: Bold, title: "加粗", active: (ed) => ed.isActive("bold"), run: (ed) => ed.chain().focus().toggleBold().run() },
  { icon: Heading2, title: "二级标题", active: (ed) => ed.isActive("heading", { level: 2 }), run: (ed) => ed.chain().focus().toggleHeading({ level: 2 }).run() },
  { icon: Pilcrow, title: "正文", run: (ed) => ed.chain().focus().setParagraph().run() },
  { icon: List, title: "项目列表", active: (ed) => ed.isActive("bulletList"), run: (ed) => ed.chain().focus().toggleBulletList().run() },
  { icon: ListOrdered, title: "编号列表", active: (ed) => ed.isActive("orderedList"), run: (ed) => ed.chain().focus().toggleOrderedList().run() },
  { icon: Undo2, title: "撤销", run: (ed) => ed.chain().focus().undo().run() },
  { icon: Redo2, title: "重做", run: (ed) => ed.chain().focus().redo().run() },
];

</script>

<template>
  <div class="wb">
    <header class="brand-row">
      <img src="/logo.png" alt="上海大学" class="brand-logo" />
      <span class="brand-title">思政教学案例库 · 工作台</span>
      <span class="proto-badge">{{ store.editDemo ? "修改流程原型 · 模拟 AI · 仅内存" : "交互原型 · 数据仅存内存" }}</span>
      <span class="brand-right">
        <span class="doc-status">{{ store.doc.status }}</span>
        <span class="doc-save">{{ store.doc.savedAt }}</span>
        <span class="brand-user">我</span>
      </span>
    </header>
    <div class="toolbar-row main-toolbar" role="toolbar" aria-label="文档格式">
      <button type="button" title="文档目录" aria-label="文档目录" :aria-expanded="!outlineCollapsed" @click="outlineCollapsed = !outlineCollapsed"><PanelLeft :size="16" /></button>
      <span class="toolbar-divider" />
      <button v-for="t in toolbarRow2" :key="t.title" type="button" :title="t.title" :class="{ active: editor()?.isActive && safeActive(t) }" @mousedown.prevent @click="runFormat(t.run)"><component :is="t.icon" :size="15" /></button>
      <span class="toolbar-divider" />
    </div>
    <div v-if="store.editDemo" class="edit-demo-guide">
      <span>试一遍：生成建议 → 预览差异 → 应用修改 → 工具栏撤销</span>
      <button type="button" @click="generateDemoRevision">生成 5 处修改建议</button>
      <button type="button" @click="reloadDemo">重新开始</button>
      <small>可先手动改开头，再尝试应用旧建议。</small>
    </div>
    <div class="workspace" :class="{ 'outline-collapsed': outlineCollapsed, 'ai-collapsed': store.ui.aiCollapsed }">
      <OutlinePanel :items="outlines" :collapsed="outlineCollapsed" @collapse="outlineCollapsed = !outlineCollapsed" @locate="locateOutline" />


      <main class="doc-area">
        <div class="paper-scroll">
          <div class="document-paper">
            <h1 class="doc-title">{{ store.doc.title }}</h1>
            <p class="doc-byline">{{ store.doc.byline }}</p>
            <PaperEditor ref="paperRef" :snapshot="snapshot" @selection-change="onSelectionChange" @ask-ai="onAskAi" @doc-change="onDocChange" />
          </div>
        </div>
      </main>

      <section id="assistant-panel" class="assist-area" :inert="store.ui.aiCollapsed" :aria-hidden="store.ui.aiCollapsed">
        <AiPane ref="aiPaneRef" v-show="store.railTab === 'ai'"
          @send="onSend"
          @activate="activateRevision" @preview="previewRevision" @accept="acceptRevision" @reject="rejectRevision"
          @stop="stopJob"
          @locate-chip="locateChip"
          @remove-chip="removeChip"
          @new-thread="onNewThread"

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

    <Transition name="toast"><div v-if="toast" class="toast" role="status">{{ toast }}</div></Transition>
  </div>
</template>
