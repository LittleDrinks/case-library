<script setup>
import { ChevronDown, LoaderCircle, MessageSquareText } from "@lucide/vue";
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";
import { api } from "../api.js";
import { renderMarkdown } from "../lib/markdown.js";
import { useAgentChat } from "../composables/useAgentChat.js";
import {
  sourceHref, sourceRefId, toolLabel, toolName, toolParamSummary,
  toolResultSummary, toolRunning, toolState, sourcesOf, elapsedBetween,
  runAnchor, runError, runForMessage, runLabel, sourceStatusLabel,
} from "../lib/agentTimeline.js";
import AgentArtifactCard from "./AgentArtifactCard.vue";
import AgentComposer from "./AgentComposer.vue";
import AgentResourceTrace from "./AgentResourceTrace.vue";
import AgentThreadList from "./AgentThreadList.vue";
import { useConversationSources } from "../composables/useConversationSources.js";

const props = defineProps({
  caseRecord: { type: Object, required: true },
  open: { type: Boolean, default: true },
  versionId: { type: String, default: "" },
  readOnly: { type: Boolean, default: false },
  review: { type: Boolean, default: false },
  writingContext: { type: Object, default: null },
});
const emit = defineEmits(["case-revised", "clear-writing-context"]);

const {
  messages, status, chatError, loading, error, settings, send, stop, retry, recovering,
  decide, artifacts, writes, threadState, threadId, stopping, retryableMessageId,
  listThreads, selectThread, createThread, renameThread, undoWrite,
  skills, catalog, reloadCatalog,
} = useAgentChat(
  props.caseRecord.id,
  props.versionId,
  props.review ? "review" : "",
);
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
const decideError = ref("");
const conversationSources = useConversationSources();
const sourceStates = reactive(new Map());
const sourceChecks = new Map();
let sourceGeneration = 0;
const syncedWrites = new Set();
const undoingWrites = reactive(new Set());
const localUndoneWrites = reactive(new Set());
let pendingWriteSync = false;
let hydratedWriteThread = "";

function sourceRefs() {
  const parts = messages.value.flatMap((message) => (message.parts || []).flatMap(sourcesOf));
  const cards = artifacts.value.flatMap((artifact) => artifact.sources || []);
  return [...new Map([...parts, ...cards].map((source) => [sourceRefId(source), source])).values()];
}

function sourceState(source) {
  return sourceStates.get(sourceRefId(source)) || { state: "checking" };
}

function sourceTitle(source) {
  return sourceState(source).title || source.title || source.id;
}

function sourceUrl(source) {
  return sourceState(source).url || "";
}

function sourceSnippet(source) {
  return sourceState(source).state === "available" ? sourceState(source).snippet || "" : "";
}

async function directSource(source, area) {
  const kind = source.kind || source.sourceType;
  const row = area.find((item) => item.id === source.id && item.sourceType === kind);
  if (row) return row;
  if (source.fromCaseArea || (source.sourceCaseId && !source.versionId)) return null;
  if (kind === "case" && source.versionId) {
    return source.sourceCaseId ? api.getPublicCase(source.sourceCaseId, source.versionId) : null;
  }
  if (kind === "case") return api.getCase(source.id);
  if (kind === "material") return api.getMaterial(source.id);
  if (kind !== "knowledge") return null;
  const result = await api.search(source.title || source.id, "knowledge", null, 100);
  return result.items?.find((item) => item.id === source.id) || null;
}

function sourceView(source, current) {
  const available = current.contentAvailable !== false;
  return {
    state: available ? "available" : "restricted",
    title: current.title || source.title,
    snippet: available ? String(current.summary ?? current.excerpt ?? "") : "",
    url: available ? current.url || sourceHref(source) : "",
  };
}

async function refreshSource(source, generation, area) {
  const key = sourceRefId(source);
  if (sourceChecks.has(key)) return sourceChecks.get(key);
  const task = (async () => {
    if (generation !== sourceGeneration) return;
    sourceStates.set(key, { state: "checking" });
    try {
      const current = await directSource(source, area);
      if (generation !== sourceGeneration) return;
      sourceStates.set(key, current ? sourceView(source, current) : { state: "unavailable" });
    } catch {
      if (generation !== sourceGeneration) return;
      sourceStates.set(key, { state: "unavailable" });
    }
    return sourceStates.get(key);
  })();
  sourceChecks.set(key, task);
  return task.finally(() => sourceChecks.delete(key));
}

async function refreshSources(generation = sourceGeneration) {
  const refs = sourceRefs();
  if (!refs.length) return;
  const area = await currentSourceArea();
  if (generation !== sourceGeneration) return;
  await Promise.all(refs.map((source) => refreshSource(source, generation, area)));
}

async function currentSourceArea() {
  try {
    return (await api.listSources(props.caseRecord.id, props.versionId || undefined)).entries || [];
  } catch {
    return [];
  }
}

function refreshSourcePermissions() {
  sourceGeneration += 1;
  sourceStates.clear();
  sourceChecks.clear();
  void refreshSources(sourceGeneration);
}

function refreshOnVisible() {
  if (document.visibilityState === "visible") refreshSourcePermissions();
}

function toolTitle(part) {
  if (toolName(part) !== "load_capability") return toolLabel(part);
  const id = part.output?.name || part.output?.skillId || part.input?.id || "";
  const loaded = part.state === "output-available";
  const label = loaded ? "已加载 Skill" : part.state === "output-error" ? "加载 Skill 失败" : "加载 Skill";
  return id ? `${label}：${skillName(id)}` : label;
}

function skillName(skillId) {
  return skills.value.find((skill) => skill.id === skillId)?.name || skillId || "";
}

function toolDurationText(part, run) {
  const timing = run?.toolTimings?.[part.toolCallId];
  return timing ? elapsedBetween(timing.startedAt, timing.finishedAt, Date.now()) : "";
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
  void refreshSources();
  void syncWrittenDocuments();
  if (nearBottom.value) void scrollToLatest();
}, { deep: true });
// 运行在本次会话内由 active 变为 completed 时，本轮若还有未同步的直接
// 写入（流式期间被跳过、或快照先于 watcher 就绪），补一次画布刷新。
watch(() => threadState.value?.latestRun?.status, (current, previous) => {
  if (previous !== "active" || !["completed", "failed", "cancelled"].includes(current)
      || !pendingWriteSync) return;
  pendingWriteSync = false;
  void refreshCaseAfterWrite();
});
watch(artifacts, () => {
  void refreshSources();
  if (nearBottom.value) void scrollToLatest();
}, { deep: true });
watch(threadId, () => {
  syncedWrites.clear();
  pendingWriteSync = false;
  hydratedWriteThread = "";
  refreshSourcePermissions();
});
watch(() => props.open, (open, wasOpen) => {
  if (open && !wasOpen) refreshSourcePermissions();
});
onMounted(() => {
  // 不在此处清空对话上下文：切页签会重挂面板，不能抹掉资料区刚勾选的内容；
  // 案例隔离由 WorkbenchView 按案例提供新实例，版本切换由 WorkbenchView 清空。
  window.addEventListener("focus", refreshSourcePermissions);
  document.addEventListener("visibilitychange", refreshOnVisible);
});

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

onBeforeUnmount(() => {
  stopThreadsPolling();
  window.removeEventListener("focus", refreshSourcePermissions);
  document.removeEventListener("visibilitychange", refreshOnVisible);
});

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

function writtenWriteIds() {
  return messages.value.flatMap((message) => message.parts || [])
    .filter((part) => part.type === "tool-write_document"
      && part.state === "output-available"
      && part.output?.status === "written" && part.output?.id)
    .map((part) => part.output.id);
}

function writeRunInFlight() {
  return Boolean(threadState.value.activeRun)
    || threadState.value.latestRun?.status === "active";
}

function writeState(part) {
  const writeId = part.output?.id;
  const server = writes.value.find((row) => row.id === writeId);
  if (server) return server.status;
  return localUndoneWrites.has(writeId) ? "undone" : "written";
}

function syncWrittenDocuments() {
  if (!threadId.value || !threadState.value) return;
  const ids = writtenWriteIds();
  if (hydratedWriteThread !== threadId.value) {
    hydratedWriteThread = threadId.value;
    [...writes.value.map((row) => row.id), ...ids]
      .forEach((writeId) => syncedWrites.add(writeId));
    pendingWriteSync = Boolean(ids.length && writeRunInFlight());
    return;
  }
  const fresh = ids.filter((writeId) => !syncedWrites.has(writeId));
  fresh.forEach((writeId) => syncedWrites.add(writeId));
  if (!fresh.length) return;
  const waitingForTerminal = writeRunInFlight() && !sending.value;
  pendingWriteSync = waitingForTerminal;
  if (!waitingForTerminal) void refreshCaseAfterWrite();
}

async function refreshCaseAfterWrite() {
  try {
    emit("case-revised", await api.getCase(props.caseRecord.id));
  } catch {
    // 画布刷新失败不阻塞对话，教师可手动刷新
  }
}

async function undoWriteRecord(writeId) {
  if (!writeId || !threadId.value || undoingWrites.has(writeId)) return;
  undoingWrites.add(writeId);
  decideError.value = "";
  try {
    const result = await undoWrite(writeId);
    localUndoneWrites.add(writeId);
    emit("case-revised", result.case);
  } catch (requestError) {
    decideError.value = requestError.message || "撤销失败";
  } finally {
    undoingWrites.delete(writeId);
  }
}

function contextParts() {
  const parts = conversationSources.sources.value.map((source) => ({
    type: "data-source", data: { sourceType: source.sourceType, id: source.id },
  }));
  const selection = props.writingContext;
  const usable = selection?.sameBlock && Number.isInteger(selection.from)
    && Number.isInteger(selection.to) && selection.to > selection.from;
  if (usable) {
    parts.push({ type: "data-selection", data: { from: selection.from, to: selection.to } });
  }
  return parts;
}

async function sendMessage({ text, skillId }) {
  await send(text, contextParts(), skillId);
}

async function rejectArtifact(artifactId) {
  decideError.value = "";
  try {
    await decide(artifactId, "rejected");
  } catch (requestError) {
    decideError.value = requestError.message || "决定失败";
  }
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
              >
                <summary><LoaderCircle v-if="part.state === 'streaming'" class="spin" :size="13" /><span>{{ part.state === "streaming" ? "思考中" : "思考过程" }}</span></summary>
                <p>{{ part.text }}</p>
              </details>
              <p v-else-if="part.type === 'text' && part.text && message.role === 'user'">{{ part.text }}</p>
              <div
                v-else-if="part.type === 'text' && part.text"
                class="markdown-body agent-answer"
                data-testid="agent-answer"
                v-html="renderMarkdown(part.text)"
              />
              <p
                v-else-if="part.type === 'data-skill' && !readOnly"
                class="ai-skill-chip"
                data-testid="message-skill"
              >使用 Skill：{{ skillName(part.data?.skillId) }}</p>
              <p
                v-else-if="part.type === 'data-selection'"
                class="ai-skill-chip"
                data-testid="message-selection"
              >正文选区：{{ part.data?.quote }}</p>
              <p v-else-if="part.type === 'data-source'" class="ai-source-chip" data-testid="message-source">
                <template v-for="source in sourcesOf(part)" :key="sourceRefId(source)">
                  <a v-if="sourceState(source).state === 'available' && sourceUrl(source)" :href="sourceUrl(source)" target="_blank" rel="noopener noreferrer">来源：{{ sourceTitle(source) }}</a>
                  <span v-else>来源：{{ sourceTitle(source) }} · {{ sourceStatusLabel(sourceState(source)) }}</span>
                </template>
              </p>
              <AgentResourceTrace
                v-else-if="part.type.startsWith('tool-read_skill_resource_')"
                :part="{ ...part }"
                :duration="toolDurationText(part, messageRun(message))"
              />
              <details
                v-else-if="part.type.startsWith('tool-')"
                class="agent-tool-trace"
                :class="{ running: toolRunning(part) }"
                :data-testid="part.type === 'tool-load_capability'
                  ? 'agent-skill-load'
                  : part.type === 'tool-read_source' ? 'agent-source-read' : 'agent-tool-trace'"
                :open="toolRunning(part) || undefined"
              >
                <summary>
                  <LoaderCircle v-if="toolRunning(part)" class="spin" :size="13" />
                  <span>{{ toolTitle(part) }} · {{ toolState(part) }}<template v-if="toolDurationText(part, messageRun(message))"> · {{ toolDurationText(part, messageRun(message)) }}</template></span>
                  <i v-if="sourcesOf(part).length">{{ sourcesOf(part).length }} 条来源</i>
                </summary>
                <p v-if="toolParamSummary(part)" class="agent-tool-line">{{ toolParamSummary(part) }}</p>
                <p
                  v-if="toolResultSummary(part)"
                  class="agent-tool-line"
                  :role="part.state === 'output-error' ? 'alert' : undefined"
                >{{ toolResultSummary(part) }}</p>
                <div v-if="sourcesOf(part).length" class="agent-sources" data-testid="agent-sources">
                  <div v-for="source in sourcesOf(part)" :key="sourceRefId(source)" class="agent-source-item" data-testid="agent-source" :data-source-ref="sourceRefId(source)" :data-source-state="sourceState(source).state">
                    <a
                      v-if="sourceState(source).state === 'available' && sourceUrl(source)"
                      :href="sourceUrl(source)"
                      target="_blank"
                      rel="noopener noreferrer"
                      :title="`在站内打开：${sourceTitle(source)}（已按当前权限核验）`"
                    ><b>{{ sourceTitle(source) }}</b><span>{{ sourceSnippet(source) }}</span><small>{{ sourceStatusLabel(sourceState(source)) }}</small></a>
                    <p v-else><b>{{ sourceTitle(source) }}</b><span>{{ sourceSnippet(source) }}</span><small>{{ sourceStatusLabel(sourceState(source)) }}</small></p>
                  </div>
                </div>
              </details>
              <AgentArtifactCard
                v-if="part.type.startsWith('tool-') && linkedArtifact(part)"
                :artifact="linkedArtifact(part)"
                :sending="sending"
                :decide-error="decideError"
                :source-state="sourceState"
                :read-only="readOnly"
                @accept="acceptArtifact"
                @reject="rejectArtifact"
              />
              <div
                v-if="part.type === 'tool-write_document' && part.output?.status === 'written' && !readOnly"
                class="agent-write-actions"
                data-testid="agent-write-actions"
              >
                <span v-if="writeState(part) === 'undone'" data-testid="agent-write-undone">已撤销写入</span>
                <button
                  v-else
                  type="button"
                  data-testid="agent-undo-write"
                  :disabled="undoingWrites.has(part.output?.id)"
                  @click="undoWriteRecord(part.output?.id)"
                >撤销写入</button>
              </div>
            </template>
            <AgentArtifactCard
              v-for="artifact in messageArtifacts(message)"
              :key="artifact.id"
              :artifact="artifact"
              :sending="sending"
              :decide-error="decideError"
              :source-state="sourceState"
              :read-only="readOnly"
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
          :source-state="sourceState"
          :read-only="readOnly"
          @accept="acceptArtifact"
          @reject="rejectArtifact"
        />
      </div>
      <button v-if="!nearBottom && messages.length" type="button" class="agent-latest" @click="scrollToLatest"><ChevronDown :size="14" />最新消息</button>
      <AgentComposer
        :case-id="caseRecord.id"
        :version-id="versionId"
        :read-only="readOnly || review"
        :configured="configured"
        :busy="loading || sending || recovering"
        :thread-id="threadId || ''"
        :writing-context="writingContext"
        :skills="skills"
        :catalog="catalog"
        @send="sendMessage"
        @clear-selection="emit('clear-writing-context')"
        @reload-catalog="reloadCatalog"
      />
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
