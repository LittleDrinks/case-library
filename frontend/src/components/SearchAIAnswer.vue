<script setup>
import { Chat } from "@ai-sdk/vue";
import { DefaultChatTransport } from "ai";
import { computed, onBeforeUnmount, ref, shallowRef, watch } from "vue";
import { ChevronDown, LoaderCircle, RotateCcw } from "@lucide/vue";
import { api } from "../api.js";
import { renderAnswer } from "../lib/markdown.js";
import { session } from "../session.js";

const props = defineProps({
  snapshot: { type: Object, required: true },
  hrefFor: { type: Function, required: true },
});
const chat = shallowRef(null);
const settings = ref(null);
const override = ref("idle");
const expanded = ref(false);
const contextItems = computed(() => props.snapshot.items.slice(0, 15));
let generation = 0;

function textParts(message) {
  return (message?.parts || []).filter((part) => part.type === "text")
    .map((part) => part.text).join("");
}

const text = computed(() => textParts(chat.value?.messages.findLast((item) => item.role === "assistant")));
const error = computed(() => "AI 服务暂不可用");
const state = computed(() => {
  if (!session.user) return "login";
  if (["checking", "unconfigured", "error", "idle"].includes(override.value)) return override.value;
  if (!settings.value) return "checking";
  if (!settings.value.configured) return "unconfigured";
  if (chat.value?.status === "error") return "error";
  if (["submitted", "streaming"].includes(chat.value?.status)) return "streaming";
  return text.value ? "complete" : override.value;
});

function resolveMarker(raw) {
  const marker = raw.trim();
  const ordered = /^\d+$/.test(marker) ? contextItems.value[Number(marker) - 1] : null;
  const item = ordered || contextItems.value.find((entry) => entry.id === marker);
  return item
    ? { item, order: contextItems.value.indexOf(item) + 1, href: props.hrefFor(item) }
    : null;
}

const answer = computed(() => renderAnswer(text.value, resolveMarker));
const answerHtml = computed(() => answer.value.html
  + (state.value === "streaming" ? '<span class="stream-caret" aria-hidden="true"></span>' : ""));
const citedSources = computed(() => {
  const cited = new Map();
  for (const resolved of answer.value.citations) {
    const key = `${resolved.item.kind}:${resolved.item.id}`;
    if (!cited.has(key)) cited.set(key, resolved);
  }
  return [...cited.values()];
});

function newChat() {
  return new Chat({
    id: `search-summary-${generation}`,
    transport: new DefaultChatTransport({
      api: "/api/search/summary", credentials: "same-origin",
      headers: () => ({ "X-CSRF-Token": session.csrfToken }),
    }),
  });
}

function retire(next) {
  generation += 1;
  chat.value?.stop();
  chat.value = null;
  settings.value = null;
  override.value = next;
}

async function generate() {
  retire("checking");
  expanded.value = false;
  if (!props.snapshot.query || !contextItems.value.length) return retire("idle");
  if (!session.user) return retire("login");
  const current = generation;
  const loaded = await api.aiSettings().catch(() => null);
  if (current !== generation) return;
  settings.value = loaded;
  if (!loaded) { override.value = "error"; return; }
  if (!loaded.configured) { override.value = "unconfigured"; return; }
  chat.value = newChat();
  override.value = "streaming";
  try { await chat.value.sendMessage({ text: props.snapshot.query }, { body: { query: props.snapshot.query, items: contextItems.value } }); }
  catch { /* Chat exposes the transport error through its state. */ }
}

watch(() => props.snapshot.revision, () => generate(), { immediate: true });
onBeforeUnmount(() => retire("idle"));
</script>

<template>
  <section class="ai-answer" role="region" aria-label="AI 回答" aria-live="polite">
    <header>
      <span>AI 回答</span>
      <small>基于当前 {{ contextItems.length }} 条可见平台资源 · 仅供参考</small>
      <button v-if="state === 'complete' || state === 'error'" type="button" title="重新生成" aria-label="重新生成 AI 回答" @click="generate()">
        <RotateCcw :size="14" aria-hidden="true" />
      </button>
    </header>
    <div v-if="state === 'login'" class="ai-answer-state">
      <p>登录后可基于当前检索结果生成摘要。</p>
      <RouterLink :to="{ name: 'login', query: { redirect: `/search?q=${encodeURIComponent(snapshot.query)}` } }">登录后生成 AI 回答</RouterLink>
    </div>
    <div v-else-if="state === 'unconfigured'" class="ai-answer-state">
      <p>当前账号尚未配置可用模型。</p>
      <RouterLink :to="{ name: 'ai-settings' }">配置 AI 模型</RouterLink>
    </div>
    <p v-else-if="state === 'checking'" class="ai-progress"><LoaderCircle class="spin" :size="16" />检查模型配置</p>
    <template v-else-if="state === 'streaming' || state === 'complete'">
      <div class="ai-answer-text markdown-body" :class="{ collapsed: !expanded }" v-html="answerHtml" />
      <button type="button" class="ai-answer-toggle" :aria-expanded="expanded" @click="expanded = !expanded">
        {{ expanded ? "收起" : "展开全文" }}
        <ChevronDown :size="14" aria-hidden="true" :class="{ flipped: expanded }" />
      </button>
    </template>
    <p v-else-if="state === 'error'" class="ai-answer-error" role="alert">{{ error }}</p>
    <p v-else class="ai-answer-state">当前结果不足以生成摘要。</p>
    <ol v-if="citedSources.length" class="ai-answer-sources" aria-label="AI 回答引用来源">
      <li v-for="cited in citedSources" :key="`${cited.item.kind}-${cited.item.id}`">
        <a :href="cited.href" target="_blank" rel="noopener noreferrer" :title="`打开来源：${cited.item.title}`">〔{{ cited.order }}〕 {{ cited.item.title }}</a>
      </li>
    </ol>
  </section>
</template>
