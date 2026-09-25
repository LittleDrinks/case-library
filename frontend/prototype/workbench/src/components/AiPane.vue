<script setup>
import { computed, nextTick, onBeforeUnmount, ref, watch } from "vue";
import { Check, Plus, Sparkles, X } from "@lucide/vue";

import { activeThread, store } from "../store.js";
import AiComposer from "./AiComposer.vue";

const emit = defineEmits(["send", "stop", "locate-chip", "remove-chip", "new-thread", "rename-thread", "accept", "reject", "preview", "activate"]);
const scrollEl = ref(null);
const titleFlash = ref(false);
const composerRef = ref(null);
const followBottom = ref(true);
const scrollPositions = new Map();
let titleTimer = 0;
let titleFrame = 0;

const thread = computed(() => activeThread());
const elapsed = computed(() => {
  void store.elapsedTick;
  const job = store.runningJob;
  return job ? globalThis.performance.now() - job.startedAt : 0;
});


function finishTitleFlash() {
  titleFlash.value = false;
}
watch(() => thread.value?.titleAnimation, async (anim) => {
  if (!anim) return;
  const target = thread.value;
  target.titleAnimation = false;
  clearTimeout(titleTimer);
  cancelAnimationFrame(titleFrame);
  titleFlash.value = false;
  await nextTick();
  titleFrame = requestAnimationFrame(() => {
    titleFlash.value = !matchMedia("(prefers-reduced-motion: reduce)").matches;
    titleTimer = setTimeout(finishTitleFlash, 650);
  });
});
function rememberScroll() {
  const el = scrollEl.value;
  if (!el) return;
  followBottom.value = el.scrollHeight - el.clientHeight - el.scrollTop < 48;
  if (thread.value) scrollPositions.set(thread.value.id, el.scrollTop);
}
async function followMessages() {
  await nextTick();
  if (followBottom.value && scrollEl.value) scrollEl.value.scrollTop = scrollEl.value.scrollHeight;
}
watch(() => thread.value?.messages.map((m) => `${m.text || ""}${m.reasoning || ""}${m.error || ""}`).join("\n"), followMessages);
watch(() => thread.value?.id, async (id) => {
  clearTimeout(titleTimer); cancelAnimationFrame(titleFrame); finishTitleFlash();
  await nextTick();
  if (scrollEl.value) scrollEl.value.scrollTop = scrollPositions.get(id) ?? scrollEl.value.scrollHeight;
  rememberScroll();
});
function send(payload) {
  followBottom.value = true;
  emit("send", payload);
}
function revision(msg) {
  return store.revisions.find((item) => item.id === msg.revisionId) || msg;
}
function revisionStatus(msg) {
  if (msg.aborted) return "已停止";
  if (msg.error) return "请求失败";
  if (!msg.revisionId) return msg.ms == null ? "正在生成修改建议…" : "没有可用的修改";
  return { accepted: "已采用", rejected: "已拒绝", stale: "原文已变化", pending: "待你确认" }[revision(msg).status] || "待你确认";
}
function revisionError(msg) {
  return msg.aborted ? "已停止生成，未应用任何修改。" : `请求失败：${msg.error}。请重新输入修改要求生成建议。`;
}
onBeforeUnmount(() => { clearTimeout(titleTimer); cancelAnimationFrame(titleFrame); });
defineExpose({ focusComposer: () => composerRef.value?.focusInput() });
</script>

<template>
  <section class="ai-pane">
    <header class="ai-head">
      <Sparkles :size="15" class="ai-head-ic" />
      <b :title="thread?.title" :class="{ 'title-flash': titleFlash }" @animationend="finishTitleFlash">{{ thread?.title || "AI" }}</b>
      <small v-if="thread?.auto" class="ai-head-auto">AI 摘要</small>
      <button type="button" class="new-chat" @click="emit('new-thread')"><Plus :size="13" /> 新会话</button>
    </header>
    <div ref="scrollEl" class="ai-messages" @scroll="rememberScroll">
      <p v-if="!thread?.messages.length" class="ai-welcome">输入问题，或选择正文后与 AI 讨论。</p>
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
          <p v-if="msg.error" class="ai-msg-error" :class="{ stopped: msg.aborted }" role="status">{{ msg.aborted ? "已停止生成，已收到的内容保留在这里。" : `请求失败：${msg.error}` }} <button v-if="!msg.aborted" type="button" @click="send({ retry: msg })">重试</button></p>
          <small v-if="msg.ms != null" class="ai-msg-meta">{{ msg.model }} · {{ (msg.ms / 1000).toFixed(1) }}s{{ msg.aborted ? " · 已停止" : "" }}</small>
        </div>
        <div v-else-if="msg.role === 'revision-card'" class="ai-msg assistant">
          <div class="ai-rev-card" :class="{ 'is-previewing': store.ui.previewId === msg.revisionId }"
            tabindex="0" role="group" aria-label="修改建议，聚焦以预览正文变化"
            @click="emit('activate', revision(msg))" @focusin="emit('activate', revision(msg))">
            <header><span class="revision-heading"><Sparkles :size="15" /> 修改建议</span><span class="revision-source">{{ msg.simulated ? "模拟结果" : "AI" }}</span></header>
            <div class="revision-copy"><p class="rev-replacement">{{ revision(msg).replacement || msg.text }}</p></div>
            <details class="revision-original"><summary>查看原文</summary><p>{{ revision(msg).original }}</p></details>
            <p v-if="msg.error" class="ai-msg-error" :class="{ stopped: msg.aborted }" role="status">{{ revisionError(msg) }}</p>
            <footer>
              <div v-if="msg.revisionId && revision(msg).status === 'pending'" class="rev-actions">
                <button type="button" @click.stop="emit('accept', revision(msg))"><Check :size="12" /> 应用修改</button>
                <button type="button" @click.stop="emit('reject', revision(msg))"><X :size="12" /> 保留原文</button>
              </div>
              <small v-if="msg.ms != null" class="ai-msg-meta">{{ msg.model }} · {{ (msg.ms / 1000).toFixed(1) }}s</small>
            </footer>
          </div>
        </div>
      </template>
    </div>
    <AiComposer
      ref="composerRef"
      :busy="Boolean(store.runningJob)"
      :elapsed="elapsed"
      :model-supported-thinking="Boolean(store.aiConfig.thinking?.[store.modelId])"
      @send="send"
      @stop="emit('stop')"
      @locate-chip="emit('locate-chip')"
      @remove-chip="emit('remove-chip')"
    />
  </section>
</template>

<style scoped>
.ai-msg-error.stopped { color: var(--ink-3); }
.ai-head b { flex: 1; min-width: 0; }
.ai-head-auto { flex: none; color: var(--ink-3); font-size: 10px; }
.ai-msg { overflow-wrap: anywhere; }
</style>
