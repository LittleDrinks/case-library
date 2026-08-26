<script setup>
import {
  BookOpenCheck, ChevronDown, ChevronUp, FileSearch, Globe2, Link2,
  LoaderCircle, MessageSquareText, Paperclip, Search, Send, Sparkles, WandSparkles,
  Square,
} from "@lucide/vue";
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { api } from "../api.js";
import { candidatePrompt, parseCandidateResponse } from "../lib/writingCandidate.js";
import AttachmentPanel from "./AttachmentPanel.vue";
import CommentPanel from "./CommentPanel.vue";
import VersionPanel from "./VersionPanel.vue";
import WritingCandidateCard from "./WritingCandidateCard.vue";

const props = defineProps({
  active: { type: String, required: true },
  open: { type: Boolean, required: true },
  caseRecord: { type: Object, required: true },
  caseTitle: { type: String, required: true },
  caseDocument: { type: Object, required: true },
  user: { type: Object, default: null },
  editable: { type: Boolean, required: true },
  beforeAttachmentMutation: { type: Function, required: true },
  beforeVersionMutation: { type: Function, required: true },
  selection: { type: Object, default: null },
  writingContext: { type: Object, default: null },
  applyCandidate: { type: Function, required: true },
  rollbackCandidateBatch: { type: Function, required: true },
  candidateInvalidation: { type: Number, default: 0 },
});
const emit = defineEmits([
  "select", "toggle", "case-refreshed", "case-restored", "mutation-state",
  "candidate-previews", "annotations",
]);

const tabs = [
  { id: "ai", label: "AI", icon: Sparkles },
  { id: "comments", label: "批注", icon: MessageSquareText },
  { id: "files", label: "附件", icon: Paperclip },
];
const aiTools = [
  { label: "理论", icon: BookOpenCheck, prompt: "请为当前案例梳理可采用的思政理论框架。" },
  { label: "平台", icon: Search, prompt: "请给出适合检索平台资料的关键词组合。" },
  { label: "联网", icon: Globe2, prompt: "请列出需要通过联网资料核验的关键事实。" },
  { label: "网页", icon: Link2, prompt: "请帮我设计一份网页资料可信度核验清单。" },
  { label: "润色", icon: WandSparkles, prompt: "请提出让当前案例表述更清晰的修改建议，不要直接改写正文。" },
  { label: "教学版", icon: FileSearch, prompt: "请为当前案例设计教学目的、阅读思考题和教学安排。" },
];
const aiSettings = ref(null);
const aiLoading = ref(true);
const aiError = ref("");
const draft = ref("");
const messages = ref([]);
const sending = ref(false);
const writingTarget = ref("");
const candidateBusy = ref(0);
const candidateSequence = ref(0);
const generationOverride = ref(false);
let controller;
const aiConfigured = computed(() => Boolean(aiSettings.value?.configured));
const pendingCandidates = computed(() => messages.value.filter(
  (item) => item.candidate?.status === "pending",
));
const candidateLimitReached = computed(() => pendingCandidates.value.length >= 3);
const candidateBlocked = computed(() => candidateLimitReached.value && !generationOverride.value);
const canSend = computed(() => {
  if (!draft.value.trim() || !aiConfigured.value || candidateBlocked.value) return false;
  return writingTarget.value !== "selection"
    || Boolean(props.selection?.quote && props.selection?.quoteHash);
});

function select(tab) {
  emit("select", tab);
}

async function loadAISettings() {
  aiLoading.value = true;
  try { aiSettings.value = await api.aiSettings(); }
  catch (reason) { aiError.value = reason.message || "AI 状态加载失败"; }
  finally { aiLoading.value = false; }
}

function usePrompt(tool) {
  draft.value = tool.prompt;
}

function nodeText(node) {
  if (typeof node?.text === "string") return node.text;
  return (node?.content || []).map(nodeText).join("");
}

function caseContext() {
  const text = nodeText(props.caseDocument).slice(0, 12000);
  return `当前案例标题：${props.caseTitle}\n当前案例正文：${text}`;
}

function requestMessages(request) {
  const history = messages.value.filter((item) => item.content)
    .map((item) => ({ role: item.role, content: item.content })).slice(-99);
  const latest = history.at(-1);
  latest.content = request.context
    ? `${request.requestContent}\n\n当前正文修订号：${request.context.revision}`
    : `${latest.content}\n\n${caseContext()}`;
  return history;
}

function addAssistant() {
  const message = { role: "assistant", content: "", pending: true, error: "" };
  messages.value.push(message);
  return messages.value.at(-1);
}

function selectWritingTarget(target) {
  if (sending.value || candidateBlocked.value) return;
  writingTarget.value = target;
}

function candidateSourceContext() {
  return writingTarget.value === "selection" ? props.selection : props.writingContext;
}

function candidateContext() {
  const source = candidateSourceContext();
  if (!source) return null;
  const fields = [
    "quote", "section", "sectionText", "from", "to", "headingFrom",
    "sectionFrom", "sectionTo", "quoteHash", "revision",
  ];
  return Object.fromEntries(fields.map((field) => [field, source[field]]));
}

function candidateStatus(generation) {
  return generation === props.candidateInvalidation ? "pending" : "expired";
}

function finishCandidate(message, context, generation) {
  try {
    message.candidate = {
      id: ++candidateSequence.value, ...parseCandidateResponse(message.content),
      invalidation: generation,
      context, mode: writingTarget.value === "selection"
        ? "replace-selection" : "replace-section", status: candidateStatus(generation),
    };
    message.content = "写作候选已生成，确认前不会修改正文。";
    syncCandidatePreviews();
  } catch (reason) { message.error = reason.message; }
  writingTarget.value = "";
}

function streamHandlers(message, context, generation) {
  return {
    onToken: (text) => { message.content += text; },
    onDone: () => {
      if (context) finishCandidate(message, context, generation);
      message.pending = false;
    },
    onError: (text) => { message.error = text; message.pending = false; },
  };
}

function buildAIRequest() {
  const content = draft.value.trim();
  if (!content || sending.value || !aiConfigured.value || candidateBlocked.value) return null;
  const context = writingTarget.value ? candidateContext() : null;
  const generation = props.candidateInvalidation;
  if (writingTarget.value && !context) return null;
  const requestContent = context ? candidatePrompt(content, writingTarget.value, context) : content;
  return { content, context, generation, requestContent };
}

function beginAIRequest(request) {
  generationOverride.value = false;
  messages.value.push({ role: "user", content: request.content, requestContent: request.requestContent });
  const answer = addAssistant();
  draft.value = "";
  return answer;
}

async function streamAnswer(answer, request) {
  sending.value = true;
  controller = new AbortController();
  try {
    await api.streamAI(
      requestMessages(request), props.user.csrfToken,
      streamHandlers(answer, request.context, request.generation), controller.signal,
    );
  } catch (reason) {
    answer.error = reason.message || "AI 服务暂不可用";
  } finally { answer.pending = false; sending.value = false; controller = null; }
}

async function send() {
  const request = buildAIRequest();
  if (!request) return;
  await streamAnswer(beginAIRequest(request), request);
}

function setCandidateMode(candidate, mode) {
  candidate.mode = mode;
  syncCandidatePreviews();
}

function rejectCandidate(candidate) {
  candidate.status = "rejected";
  generationOverride.value = false;
  syncCandidatePreviews();
}

function syncCandidatePreviews() {
  const visible = pendingCandidates.value
    .map((item) => item.candidate).filter((candidate) => candidate.previewing !== false);
  emit("candidate-previews", visible);
}

function continueGeneration() {
  generationOverride.value = true;
}

function expireCandidates() {
  messages.value.forEach((item) => {
    const candidate = item.candidate;
    if (!candidate) return;
    if (candidate.status === "pending") candidate.status = "expired";
    if (candidate.status === "accepted") candidate.rollbackExpired = true;
  });
  generationOverride.value = false;
  syncCandidatePreviews();
}

function expireOtherPending(accepted) {
  messages.value.forEach((item) => {
    const candidate = item.candidate;
    if (candidate?.status === "pending" && candidate !== accepted) candidate.status = "expired";
  });
}

function candidateIsCurrent(candidate) {
  if (candidate.invalidation === props.candidateInvalidation) return true;
  candidate.status = "expired";
  syncCandidatePreviews();
  return false;
}

function beginCandidateAcceptance(candidate) {
  candidateBusy.value = candidate.id;
  candidate.previewing = false;
  syncCandidatePreviews();
}

function finishCandidateAcceptance(candidate, result) {
  candidate.snapshotId = result.snapshotId;
  candidate.acceptedRevision = result.acceptedRevision;
  candidate.status = "accepted";
  candidate.rollbackExpired = false;
  expireOtherPending(candidate);
  generationOverride.value = false;
  syncCandidatePreviews();
}

function failCandidateAcceptance(candidate, reason) {
  candidate.previewing = true;
  candidate.error = reason.message || "修订接受失败";
  syncCandidatePreviews();
}

async function acceptCandidate(candidate) {
  if (candidateBusy.value || !candidateIsCurrent(candidate)) return;
  beginCandidateAcceptance(candidate);
  try {
    finishCandidateAcceptance(candidate, await props.applyCandidate(candidate));
  } catch (reason) {
    failCandidateAcceptance(candidate, reason);
  } finally {
    candidateBusy.value = 0;
  }
}

async function rollbackCandidate(candidate) {
  if (candidateBusy.value || !candidate.snapshotId) return;
  candidateBusy.value = candidate.id;
  try {
    if (await props.rollbackCandidateBatch(candidate.snapshotId)) {
      messages.value.forEach((item) => {
        if (item.candidate?.snapshotId === candidate.snapshotId) item.candidate.status = "rolledback";
      });
    }
  } catch (reason) { candidate.error = reason.message || "批次回滚失败"; }
  finally { candidateBusy.value = 0; }
}

function cancel() {
  controller?.abort();
  const answer = messages.value.at(-1);
  if (answer?.role === "assistant" && answer.pending) answer.error = "已停止生成";
  if (answer) answer.pending = false;
  sending.value = false;
  controller = null;
}

onMounted(loadAISettings);
onBeforeUnmount(() => controller?.abort());
watch(() => props.candidateInvalidation, expireCandidates);
watch(() => props.selection, (value) => {
  if (!value && writingTarget.value === "selection") writingTarget.value = "";
});
</script>

<template>
  <aside class="assistant-rail" :class="{ open }">
    <nav class="assistant-tabs" aria-label="辅助面板">
      <button
        v-for="tab in tabs"
        :key="tab.id"
        type="button"
        :class="{ active: active === tab.id }"
        @click="select(tab.id)"
      >
        <component :is="tab.icon" :size="17" aria-hidden="true" />
        <b>{{ tab.label }}</b>
      </button>
      <button class="drawer-toggle" type="button" :title="open ? '收起面板' : '展开面板'" @click="emit('toggle')">
        <ChevronDown v-if="open" :size="18" aria-hidden="true" />
        <ChevronUp v-else :size="18" aria-hidden="true" />
      </button>
    </nav>

    <section v-if="active === 'ai'" class="assistant-panel ai-panel">
      <div class="ai-status">
        <template v-if="aiLoading"><LoaderCircle class="spin" :size="14" />正在检查 AI 服务</template>
        <template v-else-if="aiConfigured"><span class="ai-status-dot" />{{ aiSettings.effectiveModel }}</template>
        <template v-else><span>{{ aiError || "AI 服务尚未配置" }}</span><RouterLink :to="{ name: 'ai-settings' }">配置 AI 模型</RouterLink></template>
      </div>
      <div class="panel-scroll ai-conversation" aria-live="polite">
        <div v-if="!messages.length" class="panel-empty"><Sparkles :size="24" /><span>{{ aiConfigured ? "向 AI 提问" : "配置模型后开始对话" }}</span></div>
        <article v-for="(message, index) in messages" :key="index" class="ai-message" :class="message.role">
          <b>{{ message.role === 'user' ? '我' : 'AI' }}</b>
          <p v-if="message.content">{{ message.content }}</p>
          <p v-if="message.error" class="ai-message-error" role="alert">{{ message.error }}</p>
          <LoaderCircle v-if="message.pending && !message.content" class="spin" :size="14" />
          <WritingCandidateCard
            v-if="message.candidate"
            :candidate="message.candidate"
            :busy="candidateBusy === message.candidate.id"
            @mode="setCandidateMode(message.candidate, $event)"
            @accept="acceptCandidate(message.candidate)"
            @reject="rejectCandidate(message.candidate)"
            @rollback="rollbackCandidate(message.candidate)"
          />
          <p v-if="message.candidate?.error" class="ai-message-error" role="alert">{{ message.candidate.error }}</p>
        </article>
      </div>
      <div class="candidate-targets" aria-label="AI 写作范围">
        <button
          type="button"
          aria-label="改写选区"
          :class="{ active: writingTarget === 'selection' }"
          :disabled="!editable || !selection?.quote || !selection?.quoteHash || sending || candidateBlocked"
          @click="selectWritingTarget('selection')"
        >改写选区</button>
        <button
          type="button"
          aria-label="改写本节"
          :class="{ active: writingTarget === 'section' }"
          :disabled="!editable || !writingContext?.sectionText || sending || candidateBlocked"
          @click="selectWritingTarget('section')"
        >改写本节</button>
        <span v-if="writingTarget">{{ writingTarget === 'selection' ? '候选将作用于所选文字' : `候选将作用于「${writingContext.section}」` }}</span>
        <span v-else-if="!selection?.quote || !selection?.quoteHash">请先在正文中重新选择一段文字</span>
      </div>
      <p v-if="candidateLimitReached" class="candidate-blocked" role="status">
        <span>{{ generationOverride ? "已放行一次生成" : "3 条修订待确认，请先接受或拒绝" }}</span>
        <button v-if="!generationOverride" type="button" aria-label="继续生成" :disabled="sending" @click="continueGeneration">继续生成</button>
      </p>
      <div class="ai-tools">
        <button v-for="tool in aiTools" :key="tool.label" type="button" :disabled="!aiConfigured || sending" :title="tool.label" @click="usePrompt(tool)">
          <component :is="tool.icon" :size="15" /><span>{{ tool.label }}</span>
        </button>
      </div>
      <div class="assistant-composer">
        <textarea v-model="draft" aria-label="向 AI 提问" :placeholder="aiConfigured ? '输入问题' : '请先配置 AI 模型'" :disabled="!aiConfigured || sending || candidateBlocked" @keydown.enter.exact.prevent="send" />
        <button v-if="sending" type="button" title="停止生成" aria-label="停止生成" @click="cancel"><Square :size="15" /></button>
        <button v-else type="button" title="发送" aria-label="发送" :disabled="!canSend" @click="send"><Send :size="16" /></button>
      </div>
    </section>

    <CommentPanel
      v-else-if="active === 'comments'"
      :case-record="caseRecord"
      :user="user"
      :selection="selection"
      @annotations="emit('annotations', $event)"
    />

    <AttachmentPanel
      v-else-if="active === 'files'"
      :case-record="caseRecord"
      :user="user"
      :editable="editable"
      :before-mutation="beforeAttachmentMutation"
      @case-refreshed="emit('case-refreshed', $event)"
      @mutation-state="emit('mutation-state', $event)"
    />
    <VersionPanel
      v-else-if="active === 'history'"
      :case-record="caseRecord"
      :user="user"
      :editable="editable"
      :before-mutation="beforeVersionMutation"
      @case-refreshed="emit('case-refreshed', $event)"
      @case-restored="emit('case-restored', $event)"
      @mutation-state="emit('mutation-state', $event)"
    />
  </aside>
</template>
