<script setup>
import { computed, nextTick, ref, watch } from "vue";
import { Plus, Sparkles } from "@lucide/vue";

import { activeThread, store } from "../store.js";
import AiComposer from "./AiComposer.vue";

const emit = defineEmits(["send", "stop", "locate-chip", "remove-chip", "new-thread", "open-ai-menu", "rename-thread"]);
const scrollEl = ref(null);
const titleFlash = ref(false);

const thread = computed(() => activeThread());
const elapsed = computed(() => {
  void store.elapsedTick;
  const job = store.runningJob;
  return job ? globalThis.performance.now() - job.startedAt : 0;
});
const suggestions = [
  { id: "summarize", label: "总结文档" },
  { id: "improve", label: "改进写作" },
  { id: "review", label: "审查文档" },
];

watch(() => thread.value?.titleAnimation, async (anim) => {
  if (!anim) return;
  titleFlash.value = true;
  await nextTick();
  titleFlash.value = false;
  thread.value.titleAnimation = false;
});

watch(() => thread.value?.messages.length, async () => {
  await nextTick();
  if (scrollEl.value) scrollEl.value.scrollTop = scrollEl.value.scrollHeight;
});
</script>

<template>
  <section class="ai-pane">
    <header class="ai-head">
      <Sparkles :size="15" class="ai-head-ic" />
      <b :class="{ 'title-flash': titleFlash }">{{ thread?.title || "AI" }}</b>
      <small v-if="thread?.auto" class="ai-head-auto">AI 摘要</small>
      <button type="button" class="new-chat" @click="emit('new-thread')"><Plus :size="13" /> 新会话</button>
    </header>
    <div ref="scrollEl" class="ai-messages">
      <div v-if="!thread || !thread.messages.length" class="ai-welcome">
        <div class="ai-welcome-actions">
          <button v-for="s in suggestions" :key="s.id" type="button" class="ai-suggestion" @click="emit('send', { text: s.label, via: 'suggestion' })">
            <Sparkles :size="13" /> {{ s.label }}
          </button>
        </div>
      </div>
      <template v-for="(msg, i) in thread?.messages || []" :key="i">
        <div v-if="msg.role === 'user'" class="ai-msg user">
          <blockquote v-if="msg.quote">“{{ msg.quote }}”</blockquote>
          <p>{{ msg.text }}</p>
          <small v-if="msg.skills?.length" class="msg-skills">Skill：{{ msg.skills.map((s) => s.name).join("、") }}</small>
        </div>
        <div v-else-if="msg.role === 'assistant'" class="ai-msg assistant">
          <details v-if="msg.reasoning" class="ai-reasoning">
            <summary>思考过程（模型返回）</summary>
            <p>{{ msg.reasoning }}</p>
          </details>
          <p v-if="msg.text" class="pre-wrap">{{ msg.text }}</p>
          <p v-if="msg.error" class="ai-msg-error">请求失败：{{ msg.error }} <button type="button" @click="emit('send', { retry: msg })">重试</button></p>
          <small v-if="msg.ms != null" class="ai-msg-meta">{{ msg.model }} · {{ (msg.ms / 1000).toFixed(1) }}s{{ msg.aborted ? " · 已停止" : "" }}</small>
        </div>
        <div v-else-if="msg.role === 'revision-card'" class="ai-msg assistant">
          <div class="ai-rev-card">
            <header><Sparkles :size="12" /> 修改建议（真实模型生成）</header>
            <p class="rev-original"><s>{{ msg.original }}</s></p>
            <p class="rev-replacement">{{ msg.replacement }}</p>
            <small v-if="msg.reason">{{ msg.reason }}</small>
            <footer>
              <span class="tag" :class="msg.status">{{ msg.status === "accepted" ? "已采用" : msg.status === "rejected" ? "已拒绝" : "待处理" }}</span>
            </footer>
          </div>
        </div>
      </template>
    </div>
    <AiComposer
      :busy="Boolean(store.runningJob)"
      :elapsed="elapsed"
      :model-supported-thinking="Boolean(store.aiConfig.thinking?.[store.modelId])"
      @send="(payload) => emit('send', payload)"
      @stop="emit('stop')"
      @locate-chip="emit('locate-chip')"
      @remove-chip="emit('remove-chip')"
      @open-ai-menu="emit('open-ai-menu')"
    />
  </section>
</template>
