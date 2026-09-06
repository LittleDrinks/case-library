<script setup>
import { LoaderCircle, MessageSquareText, Send } from "@lucide/vue";
import { computed, ref } from "vue";
import { useAgentChat } from "../composables/useAgentChat.js";

const props = defineProps({
  caseRecord: { type: Object, required: true },
});
const emit = defineEmits(["case-revised"]);

const draft = ref("");
const {
  messages, status, chatError, loading, error, settings, textParts, send, stop, retry,
  decide, artifacts, threadState, stopping, retryableMessageId,
} = useAgentChat(props.caseRecord.id);
const configured = computed(() => Boolean(settings.value?.configured));
const sending = computed(() => ["submitted", "streaming"].includes(status.value));
const displayError = computed(() => chatError.value || error.value || "AI 服务暂不可用");
const canSend = computed(() => Boolean(draft.value.trim() && configured.value && !loading.value && !sending.value));
const decideError = ref("");

function statusText() {
  if (loading.value) return "正在加载对话";
  if (sending.value) return "正在生成";
  return settings.value?.effectiveModel || "对话助手";
}

function toolParts(message) {
  return (message.parts || []).filter((part) => part.type.startsWith("tool-"));
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
  await send(text);
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
    <div class="panel-scroll ai-conversation" aria-live="polite">
      <div v-if="!messages.length && !loading" class="panel-empty">
        <MessageSquareText :size="24" /><span>{{ configured ? "向 AI 提问" : "配置模型后开始对话" }}</span>
      </div>
      <template v-for="message in messages" :key="message.id">
        <article class="ai-message" :class="message.role">
          <b>{{ message.role === "user" ? "我" : "AI" }}</b>
          <p v-if="textParts(message)">{{ textParts(message) }}</p>
        </article>
        <template v-if="message.role === 'assistant'">
          <p
            v-for="part in toolParts(message).filter((item) => item.type === 'tool-load_capability')"
            :key="part.toolCallId"
            class="agent-tool-trace"
            data-testid="agent-skill-load"
          >已加载 Skill：单段修订工作流 v2.1</p>
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
        <b>修订候选（第 {{ artifact.target.paragraphIndex + 1 }} 段）</b>
        <p class="agent-artifact-quote">原文：{{ artifact.target.quote }}</p>
        <p class="agent-artifact-replacement">替换为：{{ artifact.replacement }}</p>
        <p v-if="artifact.reason" class="agent-artifact-reason">理由：{{ artifact.reason }}</p>
        <p class="agent-artifact-status">状态：{{ artifact.status === "accepted" ? "已接受" : artifact.status === "rejected" ? "已拒绝" : "待确认" }}</p>
        <div v-if="artifact.status === 'pending'" class="agent-artifact-actions">
          <button type="button" data-testid="agent-accept" @click="acceptArtifact(artifact.id)">接受</button>
          <button type="button" data-testid="agent-reject" @click="rejectArtifact(artifact.id)">拒绝</button>
        </div>
      </div>
      <p v-if="decideError" class="ai-message-error" role="alert">{{ decideError }}</p>
    </div>
    <div class="assistant-composer">
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
  </section>
</template>
