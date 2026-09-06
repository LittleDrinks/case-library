<script setup>
import {
  BookOpenCheck, FileSearch, Globe2, Link2, LoaderCircle, Search, Send,
  Sparkles, WandSparkles,
} from "@lucide/vue";
import { Chat } from "@ai-sdk/vue";
import { DefaultChatTransport } from "ai";
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { api } from "../api.js";
import { session } from "../session.js";
import { candidatePrompt, parseCandidateResponse } from "../lib/writingCandidate.js";
import WritingCandidateCard from "./WritingCandidateCard.vue";

const props = defineProps({
  caseTitle: { type: String, required: true },
  caseDocument: { type: Object, required: true },
  caseId: { type: String, required: true },
  revision: { type: Number, required: true },
  user: { type: Object, default: null },
  editable: { type: Boolean, required: true },
  selection: { type: Object, default: null },
  writingContext: { type: Object, default: null },
  applyCandidate: { type: Function, required: true },
  rollbackCandidateBatch: { type: Function, required: true },
  candidateInvalidation: { type: Number, default: 0 },
});
const emit = defineEmits(["candidate-previews"]);

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
const chat = new Chat({
  id: `workbench-ai-${props.caseId}`,
  transport: new DefaultChatTransport({
    api: `/api/cases/${encodeURIComponent(props.caseId)}/ai/chat`,
    credentials: "same-origin",
    headers: () => ({ "X-CSRF-Token": session.csrfToken }),
  }),
});
let activeAnswer;
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

function textParts(message) {
  return (message?.parts || []).filter((part) => part.type === "text")
    .map((part) => part.text).join("");
}

function latestAssistant() {
  const message = chat.messages.at(-1);
  return message?.role === "assistant" ? message : null;
}

function selectWritingTarget(target) {
  if (sending.value || candidateBlocked.value) return;
  writingTarget.value = target;
}

function usePrompt(tool) {
  draft.value = tool.prompt;
}

function addAssistant() {
  const message = { role: "assistant", content: "", pending: true, error: "" };
  messages.value.push(message);
  return messages.value.at(-1);
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

function finishCandidate(message, context, generation, target) {
  try {
    message.candidate = {
      id: ++candidateSequence.value, ...parseCandidateResponse(message.content),
      invalidation: generation,
      context, mode: target === "selection" ? "replace-selection" : "replace-section",
      status: candidateStatus(generation),
    };
    message.content = "写作候选已生成，确认前不会修改正文。";
    syncCandidatePreviews();
  } catch (reason) { message.error = reason.message; }
  writingTarget.value = "";
}

function candidateRequest() {
  const content = draft.value.trim();
  if (!content || sending.value || !aiConfigured.value || candidateBlocked.value) return null;
  const context = writingTarget.value ? candidateContext() : null;
  const generation = props.candidateInvalidation;
  if (writingTarget.value && !context) return null;
  const requestContent = context ? candidatePrompt(content, writingTarget.value, context) : content;
  return { content, context, generation, requestContent, target: writingTarget.value };
}

function serverContext(request) {
  const source = request.context;
  const section = source && {
    heading: source.section,
    from: source.sectionFrom,
    to: source.sectionTo,
    text: source.sectionText,
  };
  const selection = source && request.target === "selection"
    ? { from: source.from, to: source.to, quote: source.quote } : null;
  return { revision: props.revision, section, selection };
}

function beginRequest(request) {
  generationOverride.value = false;
  messages.value.push({ role: "user", content: request.content, requestContent: request.requestContent });
  const answer = addAssistant();
  draft.value = "";
  return answer;
}

async function streamAnswer(answer, request) {
  sending.value = true;
  activeAnswer = answer;
  try {
    await chat.sendMessage({ text: request.requestContent }, {
      body: {
        mode: request.target === "selection" ? "rewrite_selection" : request.target === "section" ? "rewrite_section" : "chat",
        instruction: request.requestContent,
        context: serverContext(request),
      },
    });
    if (chat.status === "error") throw chat.error || new Error("AI 请求失败");
    answer.content = textParts(latestAssistant());
    if (request.context) finishCandidate(answer, request.context, request.generation, request.target);
  } catch {
    answer.error = "AI 服务暂不可用";
  } finally { answer.pending = false; sending.value = false; activeAnswer = null; }
}

async function send() {
  const request = candidateRequest();
  if (!request) return;
  await streamAnswer(beginRequest(request), request);
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

async function loadAISettings() {
  aiLoading.value = true;
  try { aiSettings.value = await api.aiSettings(); }
  catch (reason) { aiError.value = reason.message || "AI 状态加载失败"; }
  finally { aiLoading.value = false; }
}

onMounted(loadAISettings);
onBeforeUnmount(() => { void chat.stop(); });
watch(() => textParts(latestAssistant()), (value) => {
  if (activeAnswer && sending.value) activeAnswer.content = value;
});
watch(() => props.candidateInvalidation, expireCandidates);
watch(() => props.selection, (value) => {
  if (!value && writingTarget.value === "selection") writingTarget.value = "";
});
</script>

<template>
  <section class="assistant-panel ai-panel">
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
      <textarea v-model="draft" aria-label="向 AI 提问" :placeholder="aiConfigured ? '输入问题' : '请先配置 AI 模型'" :disabled="!aiConfigured || aiLoading || sending || candidateBlocked" @keydown.enter.exact.prevent="send" />
      <button type="button" title="发送" aria-label="发送" :disabled="!canSend" @click="send"><Send :size="16" /></button>
    </div>
  </section>
</template>
