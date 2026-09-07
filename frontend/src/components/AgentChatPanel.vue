<script setup>
import { ChevronDown, LoaderCircle, MessageSquareText, Send } from "@lucide/vue";
import { computed, nextTick, onBeforeUnmount, ref } from "vue";
import { useAgentChat } from "../composables/useAgentChat.js";
import AgentSourcePicker from "./AgentSourcePicker.vue";
import AgentResourceTrace from "./AgentResourceTrace.vue";
import AgentThreadList from "./AgentThreadList.vue";

const props = defineProps({
  caseRecord: { type: Object, required: true },
  versionId: { type: String, default: "" },
  readOnly: { type: Boolean, default: false },
  writingContext: { type: Object, default: null },
});
const emit = defineEmits(["case-revised", "case-refreshed"]);

const draft = ref("");
const {
  messages, status, chatError, loading, error, settings, textParts, send, stop, retry,
  decide, artifacts, threadState, threadId, stopping, retryableMessageId,
  listThreads, selectThread, createThread, renameThread,
  skills, selectedSkillId, catalog, reloadCatalog, skillReady,
} = useAgentChat(props.caseRecord.id, props.versionId);
const configured = computed(() => Boolean(settings.value?.configured));
const sending = computed(() => ["submitted", "streaming"].includes(status.value));
const displayError = computed(() => chatError.value || error.value || "AI 服务暂不可用");
const canSend = computed(() => Boolean(
  draft.value.trim() && configured.value && skillReady.value && !loading.value && !sending.value,
));
const decideError = ref("");
const selectedSources = ref([]);

const mode = ref("chat");
const threads = ref([]);
const threadsLoading = ref(false);
const conversation = ref(null);
const scrollPositions = new Map();
const currentTitle = computed(() => threadState.value?.title || "未命名对话");

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
  if (loading.value) return "正在加载对话";
  if (sending.value) return "正在生成";
  return settings.value?.effectiveModel || "对话助手";
}

function toolParts(message) {
  return (message.parts || []).filter((part) => part.type.startsWith("tool-"));
}

function skillName(skillId) {
  return skills.value.find((skill) => skill.id === skillId)?.name || skillId || "";
}

function skillOptionLabel(skill) {
  return skill.version ? `${skill.name}（${skill.version}）` : skill.name;
}

function skillLoadLabel(part) {
  const id = part.output?.name || part.output?.skillId || part.input?.id || "";
  return id ? `已加载 Skill：${skillName(id)}` : "已加载 Skill";
}

function skillParts(message) {
  return (message.parts || []).filter((part) => part.type === "data-skill");
}

function resourceParts(message) {
  return toolParts(message).filter((part) => part.type.startsWith("tool-read_skill_resource_"));
}

function sourcesOf(part) {
  return part.state === "output-available" ? part.output?.sources || [] : [];
}

function artifactSourceLink(source) {
  if (source.kind !== "case" || !source.sourceCaseId || !source.versionId) return null;
  return {
    name: "case-public",
    params: { id: source.sourceCaseId },
    query: { versionId: source.versionId },
  };
}

function artifactStatus(artifact) {
  return ({ accepted: "已接受", rejected: "已拒绝", expired: "已过期", pending: "待确认" })[artifact.status] || artifact.status;
}

function contextParts() {
  const parts = selectedSources.value.map((source) => ({
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
    :data-run-status="threadState?.activeRun ? 'active' : threadState?.latestRun?.status || 'none'"
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
      <div class="ai-status" role="status" :aria-busy="sending">
        <LoaderCircle v-if="loading || sending" class="spin" :size="14" />
        <span>{{ statusText() }}</span>
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
      <div ref="conversation" class="panel-scroll ai-conversation" aria-live="polite">
        <div v-if="!messages.length && !loading" class="panel-empty">
          <MessageSquareText :size="24" /><span>{{ configured ? "向 AI 提问" : "配置模型后开始对话" }}</span>
        </div>
        <template v-for="message in messages" :key="message.id">
          <article class="ai-message" :class="message.role">
            <b>{{ message.role === "user" ? "我" : "AI" }}</b>
            <p v-if="textParts(message)">{{ textParts(message) }}</p>
          </article>
          <p
            v-if="!readOnly"
            v-for="(part, index) in skillParts(message)"
            :key="`${message.id}-skill-${index}`"
            class="ai-skill-chip"
            data-testid="message-skill"
          >使用 Skill：{{ skillName(part.data?.skillId) }}</p>
          <template v-if="message.role === 'assistant'">
            <p
              v-for="part in toolParts(message).filter((item) => item.type === 'tool-load_capability')"
              :key="part.toolCallId"
              class="agent-tool-trace"
              data-testid="agent-skill-load"
            >{{ skillLoadLabel(part) }}</p>
            <div
              v-for="part in toolParts(message).filter((item) => item.type === 'tool-search_corpus')"
              :key="part.toolCallId"
              class="agent-sources"
              data-testid="agent-sources"
            >
              <span v-if="sourcesOf(part).length">{{ sourcesOf(part).length }} 条来源</span>
              <p v-for="source in sourcesOf(part)" :key="source.id" data-testid="agent-source">
                <b>{{ source.title }}</b><span>{{ source.snippet }}</span>
              </p>
            </div>
            <p
              v-for="part in toolParts(message).filter((item) => item.type === 'tool-read_source')"
              :key="part.toolCallId"
              class="agent-tool-trace"
              data-testid="agent-source-read"
            >{{ part.state === "output-available" && part.output?.status === "ok" ? "已读取并固定来源证据" : "来源当前不可读" }}</p>
            <AgentResourceTrace
              v-for="part in resourceParts(message)"
              :key="part.toolCallId"
              :part="{ ...part }"
            />
          </template>
        </template>
        <p v-if="status === 'error' || error" class="ai-message-error" role="alert">{{ displayError }}</p>
        <button
          v-if="retryableMessageId"
          type="button"
          data-testid="agent-retry"
          @click="retryRun"
        >重试</button>
        <div
          v-for="artifact in artifacts"
          :key="artifact.id"
          class="agent-artifact"
          :data-artifact-id="artifact.id"
          :data-artifact-status="artifact.status"
          data-testid="agent-artifact"
        >
          <b>修订候选</b>
          <p class="agent-artifact-quote">原文：{{ artifact.target.quote }}</p>
          <p class="agent-artifact-replacement">替换为：{{ artifact.replacement }}</p>
          <p v-if="artifact.reason" class="agent-artifact-reason">理由：{{ artifact.reason }}</p>
          <p class="agent-artifact-status">状态：{{ artifactStatus(artifact) }}</p>
          <p
            v-for="source in artifact.sources || []"
            :key="`${source.kind}:${source.id}:${source.versionId || ''}`"
            class="agent-artifact-source"
          >
            <template v-if="artifactSourceLink(source)">依据：<RouterLink :to="artifactSourceLink(source)" data-testid="agent-artifact-source-link">{{ source.title || source.id }}</RouterLink></template>
            <template v-else>依据：{{ source.title || source.id }}<span class="agent-artifact-source-status" data-testid="agent-artifact-source-status">（公开版本当前不可读）</span></template>
          </p>
          <div v-if="artifact.status === 'pending' && !readOnly" class="agent-artifact-actions">
            <button type="button" data-testid="agent-accept" @click="acceptArtifact(artifact.id)">接受</button>
            <button type="button" data-testid="agent-reject" @click="rejectArtifact(artifact.id)">拒绝</button>
          </div>
        </div>
        <p v-if="decideError" class="ai-message-error" role="alert">{{ decideError }}</p>
      </div>
      <div v-if="!readOnly" class="assistant-skill-picker">
        <label for="agent-skill-select">Skill</label>
        <select
          id="agent-skill-select"
          v-model="selectedSkillId"
          aria-label="选择 Skill"
          data-testid="skill-select"
          :disabled="loading || sending || catalog === 'loading'"
        >
          <option value="">不使用 Skill</option>
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
        <AgentSourcePicker
          :case-id="caseRecord.id"
          :revision="caseRecord.revision"
          :version-id="versionId"
          :read-only="readOnly"
          :selected="selectedSources"
          :disabled="loading || sending"
          @update:selected="selectedSources = $event"
          @case-refreshed="emit('case-refreshed', $event)"
        />
        <p v-if="writingContext?.quote" class="agent-selection-context" data-testid="agent-selection-context">
          正文选区：{{ writingContext.quote }}
        </p>
        <textarea
          v-model="draft"
          aria-label="向 AI 提问"
          :placeholder="configured ? '输入问题' : '请先配置 AI 模型'"
          :disabled="!configured || loading || sending"
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
