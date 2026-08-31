<script setup>
import { LoaderCircle, MessageSquareText, Send } from "@lucide/vue";
import { computed, ref } from "vue";
import { useAgentChat } from "../composables/useAgentChat.js";

const props = defineProps({
  caseRecord: { type: Object, required: true },
});

const draft = ref("");
const { messages, status, chatError, loading, error, settings, textParts, send } = useAgentChat(
  props.caseRecord.id,
);
const configured = computed(() => Boolean(settings.value?.configured));
const sending = computed(() => ["submitted", "streaming"].includes(status.value));
const displayError = computed(() => chatError.value || error.value || "AI 服务暂不可用");
const canSend = computed(() => Boolean(draft.value.trim() && configured.value && !loading.value && !sending.value));

function statusText() {
  if (loading.value) return "正在加载对话";
  if (sending.value) return "正在生成";
  return settings.value?.effectiveModel || "对话助手";
}

async function submit() {
  if (!canSend.value) return;
  const text = draft.value.trim();
  draft.value = "";
  await send(text);
}
</script>

<template>
  <section class="assistant-panel ai-panel agent-chat-panel">
    <div class="ai-status" role="status" :aria-busy="sending">
      <LoaderCircle v-if="loading || sending" class="spin" :size="14" />
      <span>{{ statusText() }}</span>
      <RouterLink v-if="!loading && !configured" :to="{ name: 'ai-settings' }">配置 AI 模型</RouterLink>
    </div>
    <div class="panel-scroll ai-conversation" aria-live="polite">
      <div v-if="!messages.length && !loading" class="panel-empty">
        <MessageSquareText :size="24" /><span>{{ configured ? "向 AI 提问" : "配置模型后开始对话" }}</span>
      </div>
      <article v-for="message in messages" :key="message.id" class="ai-message" :class="message.role">
        <b>{{ message.role === "user" ? "我" : "AI" }}</b>
        <p v-if="textParts(message)">{{ textParts(message) }}</p>
      </article>
      <p v-if="status === 'error' || error" class="ai-message-error" role="alert">{{ displayError }}</p>
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
