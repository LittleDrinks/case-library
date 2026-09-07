<script setup>
import { ChevronDown, LoaderCircle, MessageSquareText, Send } from "@lucide/vue";
import { computed, nextTick, onBeforeUnmount, ref, watch } from "vue";
import { CASE_EDIT_SKILL_ID, useAgentChat } from "../composables/useAgentChat.js";
import {
  durationText, sourceHref, sourceRefId, toolLabel, toolName, toolParamSummary,
  toolResultSummary, toolRunning, toolState, sourcesOf, elapsedBetween,
  runAnchor, runError, runForMessage, runLabel,
} from "../lib/agentTimeline.js";
import AgentArtifactCard from "./AgentArtifactCard.vue";
import AgentThreadList from "./AgentThreadList.vue";

const props = defineProps({
  caseRecord: { type: Object, required: true },
  writingContext: { type: Object, default: null },
});
const emit = defineEmits(["case-revised"]);

const BUILTIN_SKILL_LABEL = "单段修订工作流 v2.1";
const draft = ref("");
const {
  messages, status, chatError, loading, error, settings, send, stop, retry, recovering,
  decide, artifacts, threadState, threadId, stopping, retryableMessageId,
  listThreads, selectThread, createThread, renameThread,
  skills, selectedSkillId, catalog, reloadCatalog, skillReady,
} = useAgentChat(props.caseRecord.id);
const configured = computed(() => Boolean(settings.value?.configured));
const sending = computed(() => ["submitted", "streaming"].includes(status.value));
const displayError = computed(() => chatError.value || error.value || "AI 服务暂不可用");
const globalError = computed(() => {
  const runStatus = threadState.value?.latestRun?.status;
  return error.value || (["failed", "cancelled"].includes(runStatus) ? "" : chatError.value);
});
const runStatusAttr = computed(() => (
  sending.value || threadState.value?.activeRun
    ? "active" : threadState.value?.latestRun?.status || "none"
));
const canSend = computed(() => Boolean(
  draft.value.trim() && configured.value && skillReady.value
    && !loading.value && !sending.value && !recovering.value,
));
const decideError = ref("");

function toolTitle(part) {
  if (toolName(part) !== "load_capability") return toolLabel(part);
  const id = part.output?.name || part.output?.skillId || part.input?.id || "";
  return id ? `已加载 Skill：${skillName(id)}` : "已加载 Skill";
}

function skillName(skillId) {
  if (skillId === CASE_EDIT_SKILL_ID) return BUILTIN_SKILL_LABEL;
  return skills.value.find((skill) => skill.id === skillId)?.name || skillId || "";
}

function skillOptionLabel(skill) {
  return skill.version ? `${skill.name}（${skill.version}）` : skill.name;
}

const toolTimers = new Map();

function trackToolTimers() {
  for (const message of messages.value) {
    for (const part of message.parts || []) {
      if (!part.type.startsWith("tool-") || !part.toolCallId) continue;
      const timer = toolTimers.get(part.toolCallId);
      if (toolRunning(part)) {
        if (!timer) toolTimers.set(part.toolCallId, { startedAt: Date.now() });
      } else if (timer && timer.elapsedMs === undefined) {
        timer.elapsedMs = Date.now() - timer.startedAt;
      }
    }
  }
}

function toolDurationText(part) {
  const timer = toolTimers.get(part.toolCallId);
  if (!timer || timer.elapsedMs === undefined) return "";
  return durationText(timer.elapsedMs / 1000);
}

function runDurationText(run = threadState.value?.latestRun) {
  if (!run) return "";
  return elapsedBetween(run.startedAt, run.finishedAt, Date.now());
}

function messageRun(message) {
  return runForMessage(message, threadRuns.value);
}

function showRunStatus(message) {
  const run = messageRun(message);
  return runAnchor(message, run, messages.value);
}

function linkedArtifact(part) {
  const artifactId = part.output?.artifactId;
  return artifactId ? artifacts.value.find((artifact) => artifact.id === artifactId) : null;
}

function linkedArtifactIds() {
  return new Set(messages.value.flatMap((message) => (message.parts || [])
    .map((part) => part.output?.artifactId).filter(Boolean)));
}

function messageArtifacts(message) {
  const run = messageRun(message);
  if (!run) return [];
  const linked = linkedArtifactIds();
  return artifacts.value.filter((artifact) => artifact.runId === run.id && !linked.has(artifact.id));
}

function tailArtifacts() {
  const linked = linkedArtifactIds();
  const placed = new Set(messages.value.flatMap(messageArtifacts).map((artifact) => artifact.id));
  return artifacts.value.filter((artifact) => !linked.has(artifact.id) && !placed.has(artifact.id));
}

const mode = ref("chat");
const threads = ref([]);
const threadsLoading = ref(false);
const conversation = ref(null);
const nearBottom = ref(true);
const scrollPositions = new Map();
const currentTitle = computed(() => threadState.value?.title || "未命名对话");
const threadRuns = computed(() => {
  const runs = threadState.value?.runs || [];
  return runs.length ? runs : [threadState.value?.latestRun].filter(Boolean);
});

function trackScroll() {
  const node = conversation.value;
  if (node) nearBottom.value = node.scrollHeight - node.scrollTop - node.clientHeight < 80;
}

async function scrollToLatest() {
  await nextTick();
  if (conversation.value) conversation.value.scrollTop = conversation.value.scrollHeight;
  nearBottom.value = true;
}

watch(messages, () => {
  trackToolTimers();
  if (nearBottom.value) void scrollToLatest();
}, { deep: true });
watch(artifacts, () => { if (nearBottom.value) void scrollToLatest(); }, { deep: true });

const THREADS_POLL_MS = 2000;
let threadsTimer = null;

function stopThreadsPolling() {
  clearInterval(threadsTimer);
  threadsTimer = null;
}

async function refreshThreads() {
  try {
    threads.value = await listThreads();
  } catch {
    // 轮询失败时保留当前列表，等待下一轮刷新
  }
}

async function openThreads() {
  rememberScroll();
  mode.value = "threads";
  threadsLoading.value = true;
  try {
    await refreshThreads();
  } finally {
    threadsLoading.value = false;
    stopThreadsPolling();
    threadsTimer = setInterval(refreshThreads, THREADS_POLL_MS);
  }
}

function closeThreads() {
  stopThreadsPolling();
  mode.value = "chat";
}

onBeforeUnmount(stopThreadsPolling);

function rememberScroll() {
  if (threadId.value) scrollPositions.set(threadId.value, conversation.value?.scrollTop ?? 0);
}

async function restoreScroll(id) {
  await nextTick();
  if (conversation.value) conversation.value.scrollTop = scrollPositions.get(id) ?? 0;
}

async function chooseThread(id) {
  stopThreadsPolling();
  if (id !== threadId.value) {
    await selectThread(id);
  }
  mode.value = "chat";
  await restoreScroll(id);
}

async function addThread() {
  stopThreadsPolling();
  await createThread();
  mode.value = "chat";
  await restoreScroll(threadId.value);
}

async function applyRename(id, title) {
  await renameThread(id, title);
  threads.value = await listThreads();
}

function statusText() {
  if (recovering.value) return "正在恢复连接";
  if (loading.value) return "正在加载对话";
  if (sending.value) return "正在生成";
  return settings.value?.effectiveModel || "对话助手";
}

async function acceptArtifact(artifactId) {
  decideError.value = "";
  try {
    const result = await decide(artifactId, "accepted");
    emit("case-revised", result.case);
  } catch (requestError) {
    decideError.value = requestError.message || "决定失败";
  }
}

async function rejectArtifact(artifactId) {
  decideError.value = "";
  try {
    await decide(artifactId, "rejected");
  } catch (requestError) {
    decideError.value = requestError.message || "决定失败";
  }
}

async function submit() {
  if (!canSend.value) return;
  const text = draft.value.trim();
  draft.value = "";
  await send(text, contextParts());
}

function contextParts() {
  const selection = props.writingContext;
  if (!selection?.quote || !Number.isInteger(selection.from) || !Number.isInteger(selection.to)) return [];
  return [{ type: "data-selection", data: {
    from: selection.from, to: selection.to, quote: selection.quote,
    quoteHash: selection.quoteHash, revision: selection.revision,
  } }];
}

async function stopRun() {
  decideError.value = "";
  await stop();
}

async function retryRun() {
  decideError.value = "";
  const messageId = retryableMessageId.value;
  if (!messageId) return;
  try {
    await retry(messageId);
  } catch (requestError) {
    decideError.value = requestError.message || "重试失败";
  }
}
</script>

<template>
  <section
    class="assistant-panel ai-panel agent-chat-panel"
    :data-event-seq="threadState?.eventSeq ?? 0"
    :data-run-id="threadState?.latestRun?.id || ''"
    :data-run-status="runStatusAttr"
  >
    <template v-if="mode === 'chat'">
      <div class="agent-thread-header">
        <button
          type="button"
          class="agent-thread-current"
          data-testid="agent-thread-list-open"
          :title="currentTitle"
          @click="openThreads"
        >
          <MessageSquareText :size="13" aria-hidden="true" />
          <span>{{ currentTitle }}</span>
          <ChevronDown :size="13" aria-hidden="true" />
        </button>
      </div>
      <div class="ai-status" role="status" :aria-busy="sending || recovering">
        <LoaderCircle v-if="loading || sending || recovering" class="spin" :size="14" />
        <span>{{ statusText() }}<template v-if="runDurationText()"> · 耗时 {{ runDurationText() }}</template></span>
        <button
          v-if="sending"
          type="button"
          data-testid="agent-stop"
          title="停止生成"
          :disabled="stopping"
          @click="stopRun"
        >停止</button>
        <RouterLink v-if="!loading && !configured" :to="{ name: 'ai-settings' }">配置 AI 模型</RouterLink>
      </div>
      <div ref="conversation" class="panel-scroll ai-conversation" aria-live="polite" @scroll="trackScroll">
        <div v-if="!messages.length && !loading" class="panel-empty">
          <MessageSquareText :size="24" /><span>{{ configured ? "向 AI 提问" : "配置模型后开始对话" }}</span>
        </div>
        <template v-for="message in messages" :key="message.id">
          <article class="ai-message" :class="message.role">
            <b>{{ message.role === "user" ? "我" : "AI" }}</b>
            <template v-for="(part, index) in message.parts" :key="index">
              <details
                v-if="part.type === 'reasoning'"
                class="agent-reasoning"
                :class="{ streaming: part.state === 'streaming' }"
                :open="part.state === 'streaming' || undefined"
              >
                <summary><LoaderCircle v-if="part.state === 'streaming'" class="spin" :size="13" /><span>{{ part.state === "streaming" ? "思考中" : "思考过程" }}</span></summary>
                <p>{{ part.text }}</p>
              </details>
              <p v-else-if="part.type === 'text' && part.text">{{ part.text }}</p>
              <p
                v-else-if="part.type === 'data-skill'"
                class="ai-skill-chip"
                data-testid="message-skill"
              >使用 Skill：{{ skillName(part.data?.skillId) }}</p>
              <p
                v-else-if="part.type === 'data-selection'"
                class="ai-skill-chip"
                data-testid="message-selection"
              >正文选区：{{ part.data?.quote }}</p>
              <details
                v-else-if="part.type.startsWith('tool-')"
                class="agent-tool-trace"
                :class="{ running: toolRunning(part) }"
                data-testid="agent-skill-load"
                :open="toolRunning(part) || undefined"
              >
                <summary>
                  <LoaderCircle v-if="toolRunning(part)" class="spin" :size="13" />
                  <span>{{ toolTitle(part) }} · {{ toolState(part) }}<template v-if="toolDurationText(part)"> · {{ toolDurationText(part) }}</template></span>
                  <i v-if="sourcesOf(part).length">{{ sourcesOf(part).length }} 条来源</i>
                </summary>
                <p v-if="toolParamSummary(part)" class="agent-tool-line">{{ toolParamSummary(part) }}</p>
                <p
                  v-if="toolResultSummary(part)"
                  class="agent-tool-line"
                  :role="part.state === 'output-error' ? 'alert' : undefined"
                >{{ toolResultSummary(part) }}</p>
                <div v-if="sourcesOf(part).length" class="agent-sources" data-testid="agent-sources">
                  <div v-for="source in sourcesOf(part)" :key="sourceRefId(source)" class="agent-source-item" data-testid="agent-source" :data-source-ref="sourceRefId(source)">
                    <a
                      v-if="sourceHref(source)"
                      :href="sourceHref(source)"
                      target="_blank"
                      rel="noopener noreferrer"
                      :title="`在站内打开：${source.title || source.id}（以当前权限为准）`"
                    ><b>{{ source.title }}</b><span>{{ source.snippet }}</span></a>
                    <p v-else><b>{{ source.title }}</b><span>{{ source.snippet }}</span></p>
                  </div>
                </div>
              </details>
              <AgentArtifactCard
                v-if="part.type.startsWith('tool-') && linkedArtifact(part)"
                :artifact="linkedArtifact(part)"
                :sending="sending"
                :decide-error="decideError"
                @accept="acceptArtifact"
                @reject="rejectArtifact"
              />
            </template>
            <AgentArtifactCard
              v-for="artifact in messageArtifacts(message)"
              :key="artifact.id"
              :artifact="artifact"
              :sending="sending"
              :decide-error="decideError"
              @accept="acceptArtifact"
              @reject="rejectArtifact"
            />
            <div
              v-if="showRunStatus(message)"
              class="agent-run-status"
              :data-run-id="messageRun(message).id"
              :data-run-status="messageRun(message).status"
              data-testid="agent-run-status"
            >
              <LoaderCircle v-if="messageRun(message).status === 'active'" class="spin" :size="13" />
              <span>{{ runLabel(messageRun(message)) }}</span>
              <span v-if="runDurationText(messageRun(message))"> · 耗时 {{ runDurationText(messageRun(message)) }}</span>
              <p v-if="runError(messageRun(message))" class="agent-run-error" role="alert">{{ runError(messageRun(message)) }}</p>
            </div>
            <button
              v-if="message.id === retryableMessageId"
              type="button"
              class="agent-retry"
              data-testid="agent-retry"
              @click="retryRun"
            >重试这条消息</button>
          </article>
        </template>
        <p v-if="globalError" class="ai-message-error" role="alert">{{ displayError }}</p>
        <AgentArtifactCard
          v-for="artifact in tailArtifacts()"
          :key="artifact.id"
          :artifact="artifact"
          :sending="sending"
          :decide-error="decideError"
          @accept="acceptArtifact"
          @reject="rejectArtifact"
        />
      </div>
      <button v-if="!nearBottom && messages.length" type="button" class="agent-latest" @click="scrollToLatest"><ChevronDown :size="14" />最新消息</button>
      <div class="assistant-skill-picker">
        <label for="agent-skill-select">Skill</label>
        <select
          id="agent-skill-select"
          v-model="selectedSkillId"
          aria-label="选择 Skill"
          data-testid="skill-select"
          :disabled="loading || sending || catalog === 'loading'"
        >
          <option :value="CASE_EDIT_SKILL_ID">平台内置（单段修订）</option>
          <option v-for="skill in skills" :key="skill.id" :value="skill.id">
            {{ skillOptionLabel(skill) }}
          </option>
        </select>
        <span v-if="catalog === 'loading'" class="skill-catalog-state" data-testid="skill-catalog-loading">正在加载目录</span>
        <template v-else-if="catalog === 'error'">
          <span class="skill-catalog-state error" data-testid="skill-catalog-error">目录加载失败</span>
          <button type="button" class="skill-catalog-retry" data-testid="skill-catalog-retry" @click="reloadCatalog">重试</button>
        </template>
        <span v-else-if="!skills.length" class="skill-catalog-state" data-testid="skill-catalog-empty">暂无已发布 Skill</span>
      </div>
      <div class="assistant-composer">
        <div
          v-if="writingContext?.quote"
          class="assistant-context-summary"
          data-testid="composer-selection"
          :title="`正文上下文：${writingContext.quote}`"
        >正文上下文：{{ writingContext.quote }}</div>
        <textarea
          v-model="draft"
          aria-label="向 AI 提问"
          :placeholder="configured ? '输入问题' : '请先配置 AI 模型'"
          :disabled="!configured || loading || sending || recovering"
          @keydown.enter.exact.prevent="submit"
        />
        <button type="button" title="发送" aria-label="发送" :disabled="!canSend" @click="submit">
          <Send :size="16" />
        </button>
      </div>
    </template>
    <AgentThreadList
      v-else
      :threads="threads"
      :current-id="threadId"
      :loading="threadsLoading"
      @back="closeThreads"
      @select="chooseThread"
      @create="addThread"
      @rename="applyRename"
    />
  </section>
</template>
