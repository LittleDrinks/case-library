<script setup>
import { CheckCircle2, ChevronLeft, ClipboardCheck, Download, History, Paperclip, Sparkles } from "@lucide/vue";
import { computed, reactive, ref, shallowRef } from "vue";
import { api } from "../api.js";
import WorkbenchAiVariantA from "../components/prototype/WorkbenchAiVariantA.vue";
import "../styles/prototype-agent-sidebar.css";

const action = ref("等待选择操作");
const activeThread = ref("goals");
const controller = shallowRef(null);
const liveTurns = ref([]);
const selected = "形成对学术诚信、数据安全与教师责任的基本判断。";
const promptParts = ref([
  { type: "skill", id: "skill-sizheng", skillId: "sizheng-case-generator.v2.1.m1", label: "思政案例生成", version: "v2.1" },
  { type: "text", id: "text-1", text: "请用 " },
  { type: "context", id: "token-1", resourceId: "material-1", kind: "material", label: "人工智能赋能教育的伦理边界" },
  { type: "text", id: "text-2", text: " 改写教学目的，再用 " },
  { type: "context", id: "token-2", resourceId: "material-2", kind: "material", label: "生成式 AI 与学术诚信" },
  { type: "text", id: "text-3", text: " 补充阅读思考题。" },
]);
const selectedTools = ref(["search_corpus", "propose_revision"]);
const contexts = ref([
  { id: "goal-selection", kind: "selection", label: "教学目的", excerpt: selected },
  { id: "question-selection", kind: "selection", label: "阅读思考题", excerpt: "比较不同角色的责任，并形成一份可执行的课堂使用约定。" },
  { id: "material-1", kind: "material", label: "人工智能赋能教育的伦理边界", excerpt: "案例 · 平台资料" },
  { id: "material-2", kind: "material", label: "生成式 AI 与学术诚信", excerpt: "案例 · 平台资料" },
  { id: "material-3", kind: "material", label: "课堂教学设计规范", excerpt: "知识 · 平台资料" },
  { id: "material-4", kind: "material", label: "教育数字化战略行动", excerpt: "政策 · 平台资料" },
  { id: "material-5", kind: "material", label: "高校课堂数据安全指引", excerpt: "知识 · 平台资料" },
  { id: "material-6", kind: "material", label: "教师使用生成式 AI 的责任", excerpt: "案例 · 平台资料" },
  { id: "material-7", kind: "material", label: "学生 AI 使用行为调查", excerpt: "素材 · 平台资料" },
  { id: "material-8", kind: "material", label: "课程评价行为动词表", excerpt: "知识 · 平台资料" },
  { id: "material-9", kind: "material", label: "人工智能伦理治理框架", excerpt: "政策 · 平台资料" },
  { id: "material-10", kind: "material", label: "课堂研讨任务设计示例", excerpt: "案例 · 平台资料" },
]);
const threads = ref([
  { id: "goals", title: "完善教学目标", short: "教学目标", time: "刚刚", preview: "收紧学习结果，使目标可观察、可评价" },
  { id: "evidence", title: "补充课堂案例依据", short: "案例依据", time: "昨天", preview: "从平台资料中补充课堂治理案例" },
  { id: "questions", title: "设计研讨问题", short: "研讨问题", time: "8月28日", preview: "围绕角色责任设计分组研讨问题" },
  { id: "intro", title: "润色课程导语", short: "课程导语", time: "8月27日", preview: "让导语更贴近真实课堂情境" },
  { id: "sources", title: "检查素材引用", short: "素材引用", time: "8月26日", preview: "核对当前案例中的引用与访问权限" },
  { id: "review", title: "整理提交前问题", short: "提交检查", time: "8月25日", preview: "汇总仍需确认的内容和附件" },
]);
const liveState = computed(() => liveTurns.value.at(-1)?.state || "idle");
const insertedSkillIds = computed(() => promptParts.value.filter((part) => part.type === "skill").map((part) => part.skillId));

function setPromptParts(value) { promptParts.value = value; }
function toggleTool(id) { selectedTools.value = selectedTools.value.includes(id) ? selectedTools.value.filter((item) => item !== id) : [...selectedTools.value, id]; }
function selectThread(id) { activeThread.value = id; action.value = `已切换到：${threads.value.find((item) => item.id === id)?.title}`; }
function accept() { action.value = "已接受修订；正文将增加一次 revision"; }
function reject() { action.value = "已拒绝修订；正文未修改"; }
function retry() { send(); }

function promptText() {
  return promptParts.value.map((part) => part.type === "text" ? part.text : part.type === "context" ? `「${part.label}」` : "").join("").trim();
}

function referencedContexts() {
  const ids = new Set(promptParts.value.filter((part) => part.type === "context").map((part) => part.resourceId));
  return contexts.value.filter((item) => ids.has(item.id));
}

function handlers(turn) {
  return {
    onToken: (text) => { turn.answer += text; },
    onDone: () => { turn.state = "complete"; action.value = "真实模型回答完成"; },
    onError: (message) => { turn.state = "error"; turn.error = message; },
  };
}

async function runTurn(turn) {
  controller.value = new AbortController();
  try {
    await api.streamPrototypeAgent(
      { instruction: turn.question, references: referencedContexts(), skillIds: turn.skillIds, toolIds: turn.toolIds }, handlers(turn), controller.value.signal,
    );
  } catch (reason) {
    if (reason.name !== "AbortError") { turn.state = "error"; turn.error = reason.message; }
  }
}

function send() {
  const question = promptText();
  if (!question || liveState.value === "streaming") return;
  const turn = reactive({ id: `live-${Date.now()}`, question, answer: "", error: "", skillIds: [...insertedSkillIds.value], toolIds: [...selectedTools.value], state: "streaming" });
  liveTurns.value.push(turn);
  action.value = "正在调用 .env 配置的真实模型";
  runTurn(turn);
}

function stop() {
  controller.value?.abort();
  const turn = liveTurns.value.at(-1);
  if (turn?.state === "streaming") turn.state = "stopped";
  action.value = "已停止本轮真实模型请求";
}

function newThread() {
  const id = `new-${threads.value.length + 1}`;
  threads.value.unshift({ id, title: "未命名对话", short: "新对话", time: "刚刚" });
  activeThread.value = id;
  action.value = "已新建对话";
}

</script>

<template>
  <div class="prototype-workbench-page">
    <header class="prototype-site-header"><div class="prototype-brand"><span class="brand-mark">上大</span><b>“强国有我”思政案例库</b></div><nav><span>首页</span><span>我的案例</span><span>资源检索</span><span>管理后台</span></nav><div class="prototype-account">演示管理员</div></header>
    <header class="prototype-workspace-header"><div><span>我的案例</span><i>/</i><b>AI 进课堂案例</b></div><p><em>草稿</em> 已保存</p><div><button type="button" aria-label="AI"><Sparkles :size="17" /></button><button type="button" aria-label="历史版本"><History :size="17" /></button><button type="button" aria-label="附件"><Paperclip :size="17" /></button><button type="button" aria-label="提交前自检"><ClipboardCheck :size="17" /></button><button type="button" aria-label="导出"><Download :size="17" /></button><button class="prototype-submit" type="button">提交审核</button></div></header>
    <div class="prototype-workbench-layout"><aside class="prototype-outline"><p>一、教学说明<br />（800字左右）</p><p>（一）教学目的</p><p>（二）阅读思考题<br />（2～3个）</p><p>（三）教学安排</p><p>（四）注意事项</p><p>二、文本内容<br />（2500字左右）</p><button type="button" aria-label="收起大纲"><ChevronLeft :size="17" /></button></aside><main class="prototype-canvas"><article class="prototype-document"><div class="prototype-toolbar"><b>B</b><b>H₂</b><b>¶</b><b>☷</b><b>1.</b></div><h1>生成式人工智能进课堂：<br />使用边界与课堂治理研讨</h1><div class="prototype-byline">课程未设置　教学案例</div><h2>一、教学说明（800字左右）</h2><h3>（一）教学目的</h3><p>帮助学生识别人工智能辅助学习的合理边界，<mark>{{ selected }}</mark></p><h3>（二）阅读思考题（2～3个）</h3><p>学生以小组为单位分析真实课堂案例，比较不同角色的责任，并形成一份可执行的课堂使用约定。</p><h3>（三）教学安排</h3><p>围绕技术便利、学术诚信、数据安全与教师责任展开研讨。</p></article></main><aside class="prototype-rail"><nav class="prototype-rail-tabs"><button class="active" type="button"><Sparkles :size="17" />AI</button><button type="button">批注</button></nav><WorkbenchAiVariantA :active-thread="activeThread" :contexts="contexts" :live-state="liveState" :live-turns="liveTurns" :prompt-parts="promptParts" :selected="selected" :skill-ids="insertedSkillIds" :tool-ids="selectedTools" :threads="threads" @accept="accept" @new-thread="newThread" @prompt-parts="setPromptParts" @reject="reject" @retry="retry" @select-thread="selectThread" @send="send" @stop="stop" @toggle-tool="toggleTool" /></aside></div>
    <output class="prototype-state agent-prototype-state"><CheckCircle2 :size="15" /><span>{{ action }}</span><span>thread={{ activeThread }} · model={{ liveState }}</span></output>
  </div>
</template>
