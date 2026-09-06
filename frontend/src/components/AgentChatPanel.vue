<script setup>
import { ChevronDown, LoaderCircle, MessageSquareText, Send, Paperclip } from "@lucide/vue";
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useAgentChat } from "../composables/useAgentChat.js";
import { api } from "../api.js";
import AgentThreadList from "./AgentThreadList.vue";

const props = defineProps({
  caseRecord: { type: Object, required: true },
  versionId: { type: String, default: "" },
  readOnly: { type: Boolean, default: false },
  writingContext: { type: Object, default: null },
});
const emit = defineEmits(["case-revised"]);

const draft = ref("");
const {
  messages, status, chatError, loading, error, settings, send, stop, retry,
  decide, artifacts, threadState, threadId, stopping, retryableMessageId,
  skills, selectedSkillId,
  listThreads, selectThread, createThread, renameThread,
} = useAgentChat(props.caseRecord.id, props.versionId);
const availableSources = ref([]);
const chosenSources = ref([]);
const sourceQuery = ref("");
const sourcePickerOpen = ref(false);
const filteredSources = computed(() => availableSources.value.filter(
  (source) => source.title.toLowerCase().includes(sourceQuery.value.toLowerCase()),
));

async function loadSources() {
  try { availableSources.value = (await api.listSources(props.caseRecord.id, props.versionId)).entries; }
  catch { availableSources.value = []; }
}

function contextParts() {
  const parts = chosenSources.value.map((source) => ({
    type: "data-source", data: { sourceType: source.sourceType, id: source.id },
  }));
  const selection = props.writingContext;
  if (selection?.quote && Number.isInteger(selection.paragraphIndex)) {
    parts.push({ type: "data-selection", data: { paragraphIndex: selection.paragraphIndex, quote: selection.quote } });
  }
  return parts;
}

function toolLabel(part) {
  const name = part.type.slice(5);
  return ({ load_capability: "加载 Skill", search_corpus: "检索案例", list_tag_catalog: "查询标签", read_source: "阅读来源", propose_revision: "生成修订建议" })[name]
    || (name.startsWith("read_skill_resource") ? "阅读 Skill 资源" : name);
}

function toolState(part) {
  if (part.state === "output-error") return part.errorText || "执行失败";
  if (part.state !== "output-available") return "进行中";
  return ({ ok: "已完成", pending: "待确认", unavailable: "无法读取", not_found: "未找到" })[part.output?.status] || "已完成";
}

function toolRunning(part) {
  return part.state !== "output-available" && part.state !== "output-error";
}

function toolTitle(part) {
  return part.type === "tool-load_capability" ? skillLoadLabel(part) : toolLabel(part);
}

function toolParamSummary(part) {
  const input = part.input || {};
  const name = part.type.slice(5);
  if (name === "search_corpus") {
    const scope = input.kind && input.kind !== "all" ? `（范围：${input.kind}）` : "";
    return `检索词：${input.query ?? ""}${scope}`;
  }
  if (name === "read_source") return `来源：${input.source_type || ""} ${input.source_id || ""}`;
  if (name === "propose_revision") {
    return Number.isInteger(input.paragraph_index) ? `目标：第 ${input.paragraph_index + 1} 段` : "";
  }
  if (name === "list_tag_catalog") return input.query ? `筛选：${input.query}` : "";
  return "";
}

function toolResultSummary(part) {
  if (part.state === "output-error") return part.errorText || "执行失败";
  if (part.state !== "output-available") return "";
  const output = part.output || {};
  if (output.artifactId) return "已创建修订候选，等待决定";
  if (part.type === "tool-search_corpus") return `${(output.sources || []).length} 条来源`;
  if (typeof output.status === "string" && output.status !== "ok") {
    const labels = { pending: "待确认", unavailable: "无法读取", not_found: "未找到", no_access: "当前身份无权限读取", empty: "内容为空", error: "读取失败" };
    return labels[output.status] || output.status;
  }
  return "";
}

function toolShowRaw(part) {
  if (part.type === "tool-load_capability") return false;
  return !toolParamSummary(part) && !toolResultSummary(part) && !sourcesOf(part).length;
}

function toolRaw(part) {
  const data = part.output ?? part.input;
  return data == null ? "" : JSON.stringify(data, null, 2);
}

function sourceHref(source) {
  const kind = source.kind || source.sourceType;
  if (kind === "material") return `#/materials/${encodeURIComponent(source.id)}`;
  if (kind === "case") return `#/cases/${encodeURIComponent(source.id)}`;
  return "";
}

onMounted(loadSources);
watch(() => props.caseRecord.revision, loadSources);
const configured = computed(() => Boolean(settings.value?.configured));
const sending = computed(() => ["submitted", "streaming"].includes(status.value));
const displayError = computed(() => chatError.value || error.value || "AI 服务暂不可用");
const canSend = computed(() => Boolean(draft.value.trim() && configured.value && !loading.value && !sending.value));
const decideError = ref("");

const mode = ref("chat");
const threads = ref([]);
const threadsLoading = ref(false);
const conversation = ref(null);
const nearBottom = ref(true);
const scrollPositions = new Map();
const currentTitle = computed(() => threadState.value?.title || "未命名对话");

function trackScroll() {
  const node = conversation.value;
  if (node) nearBottom.value = node.scrollHeight - node.scrollTop - node.clientHeight < 80;
}

async function scrollToLatest() {
  await nextTick();
  if (conversation.value) conversation.value.scrollTop = conversation.value.scrollHeight;
  nearBottom.value = true;
}

watch(messages, () => { if (nearBottom.value) void scrollToLatest(); }, { deep: true });
watch(artifacts, () => { if (nearBottom.value) void scrollToLatest(); }, { deep: true });

function artifactStatus(artifact) {
  return ({ accepted: "已接受", rejected: "已拒绝", expired: "已过期", pending: "待确认" })[artifact.status] || artifact.status;
}

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

function skillName(skillId) {
  return skills.value.find((skill) => skill.id === skillId)?.name || skillId || "";
}

function skillLoadLabel(part) {
  const name = part.output?.name || part.output?.skillId || part.input?.id || "";
  return name ? `已加载 Skill：${skillName(name)}` : "已加载 Skill";
}

function skillOptionLabel(skill) {
  return skill.version ? `${skill.name}（${skill.version}）` : skill.name;
}

function sourcesOf(part) {
  return part.state === "output-available" ? part.output?.sources || [] : [];
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
                <summary><LoaderCircle v-if="part.state === 'streaming'" class="spin" :size="13" /><span>{{ part.state === 'streaming' ? "思考中" : "思考过程" }}</span></summary>
                <p>{{ part.text }}</p>
              </details>
              <p v-else-if="part.type === 'text' && part.text">{{ part.text }}</p>
              <p
                v-else-if="part.type === 'data-skill'"
                class="ai-skill-chip"
                data-testid="message-skill"
              >使用 Skill：{{ skillName(part.data?.skillId) }}</p>
              <details
                v-else-if="part.type.startsWith('tool-')"
                class="agent-tool-trace"
                :class="{ running: toolRunning(part) }"
                data-testid="agent-skill-load"
                :open="toolRunning(part) || undefined"
              >
                <summary><LoaderCircle v-if="toolRunning(part)" class="spin" :size="13" /><span>{{ toolTitle(part) }} · {{ toolState(part) }}</span><i v-if="sourcesOf(part).length">{{ sourcesOf(part).length }} 条来源</i></summary>
                <p v-if="toolParamSummary(part)" class="agent-tool-line">{{ toolParamSummary(part) }}</p>
                <p v-if="toolResultSummary(part)" class="agent-tool-line">{{ toolResultSummary(part) }}</p>
                <div v-if="sourcesOf(part).length" class="agent-sources" data-testid="agent-sources">
                  <div v-for="source in sourcesOf(part)" :key="source.id" class="agent-source-item" data-testid="agent-source">
                    <a
                      v-if="sourceHref(source)"
                      :href="sourceHref(source)"
                      target="_blank"
                      rel="noopener noreferrer"
                      :title="`在站内打开：${source.title || source.id}`"
                    ><b>{{ source.title }}</b><span>{{ source.snippet }}</span></a>
                    <p v-else><b>{{ source.title }}</b><span>{{ source.snippet }}</span></p>
                  </div>
                </div>
                <pre v-if="toolShowRaw(part)">{{ toolRaw(part) }}</pre>
              </details>
            </template>
          </article>
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
          <b>修订候选（第 {{ artifact.target.paragraphIndex + 1 }} 段）</b>
          <p class="agent-artifact-quote">原文：{{ artifact.target.quote }}</p>
          <p class="agent-artifact-replacement">替换为：{{ artifact.replacement }}</p>
          <p v-if="artifact.reason" class="agent-artifact-reason">理由：{{ artifact.reason }}</p>
          <p class="agent-artifact-status">状态：{{ artifactStatus(artifact) }}</p>
          <template v-for="source in artifact.sources || []" :key="source.id">
            <a
              v-if="sourceHref(source)"
              class="agent-artifact-source"
              :href="sourceHref(source)"
              target="_blank"
              rel="noopener noreferrer"
              :title="`在站内打开：${source.title || source.id}`"
            >依据：{{ source.title || source.id }}</a>
            <p v-else class="agent-artifact-source">依据：{{ source.title || source.id }}</p>
          </template>
          <div v-if="artifact.status === 'pending' && !readOnly" class="agent-artifact-actions">
            <button type="button" data-testid="agent-accept" :disabled="sending" @click="acceptArtifact(artifact.id)">接受</button>
            <button type="button" data-testid="agent-reject" @click="rejectArtifact(artifact.id)">拒绝</button>
          </div>
        </div>
        <p v-if="decideError" class="ai-message-error" role="alert">{{ decideError }}</p>
      </div>
      <button v-if="!nearBottom && messages.length" type="button" class="agent-latest" @click="scrollToLatest"><ChevronDown :size="14" />最新消息</button>
      <div class="assistant-composer">
        <div class="agent-composer-tools">
          <div class="agent-context-picker">
            <button type="button" title="选择资料" @click="sourcePickerOpen = !sourcePickerOpen; loadSources()">
              <Paperclip :size="15" />资料 {{ chosenSources.length || "" }}
            </button>
            <span v-if="writingContext?.quote">已选正文</span>
            <div v-if="sourcePickerOpen" class="agent-source-options">
              <input v-model="sourceQuery" type="search" placeholder="查找资料" aria-label="查找资料" />
              <label v-for="source in filteredSources" :key="`${source.sourceType}:${source.id}`">
                <input v-model="chosenSources" type="checkbox" :value="source" />
                <span>{{ source.title }}</span>
              </label>
              <p v-if="!filteredSources.length">暂无资料</p>
            </div>
          </div>
          <div class="assistant-skill-picker">
            <label for="agent-skill-select">Skill</label>
            <select
              id="agent-skill-select"
              v-model="selectedSkillId"
              aria-label="选择 Skill"
              data-testid="skill-select"
              :disabled="loading || sending"
            >
              <option value="">不使用 Skill</option>
              <option v-for="skill in skills" :key="skill.id" :value="skill.id">
                {{ skillOptionLabel(skill) }}
              </option>
            </select>
          </div>
        </div>
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
