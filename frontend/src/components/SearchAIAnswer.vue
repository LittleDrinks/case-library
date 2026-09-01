<script setup>
import { Chat } from "@ai-sdk/vue";
import { DefaultChatTransport } from "ai";
import { computed, ref, shallowRef, watch } from "vue";
import { LoaderCircle, RotateCcw } from "@lucide/vue";
import { api } from "../api.js";
import { session } from "../session.js";
import { publicUrl } from "../lib/publicUrl.js";

const props = defineProps({ query: String, items: { type: Array, required: true } });
const chat = shallowRef(null);
const settings = ref(null);
const override = ref("idle");
const signature = computed(() => props.items.map((item) => `${item.kind}:${item.id}`).join("|"));
const contextItems = computed(() => props.items.slice(0, 15));
let generation = 0;

function textParts(message) {
  return (message?.parts || []).filter((part) => part.type === "text")
    .map((part) => part.text).join("");
}

const text = computed(() => textParts(chat.value?.messages.findLast((item) => item.role === "assistant")));
const error = computed(() => "AI 服务暂不可用");
const state = computed(() => {
  if (!session.user) return "login";
  if (["checking", "skipped", "unconfigured", "error"].includes(override.value)) return override.value;
  if (!settings.value) return "checking";
  if (!settings.value.configured) return "unconfigured";
  if (chat.value?.status === "error") return "error";
  if (["submitted", "streaming"].includes(chat.value?.status)) return "streaming";
  return text.value ? "complete" : override.value;
});

function itemDestination(item) {
  if (item.kind === "case") return { name: "case-public", params: { id: item.id } };
  return item.kind === "material" ? publicUrl(item.sourceUrl) : "";
}

function shouldGenerate() {
  return contextItems.value.length < 3
    || /哪些|怎么|为什么|如何|吗|？|\?/.test(props.query)
    || props.query.length >= 15;
}

function newChat() {
  return new Chat({
    id: `search-summary-${generation}`,
    transport: new DefaultChatTransport({
      api: "/api/search/summary", credentials: "same-origin",
      headers: () => ({ "X-CSRF-Token": session.csrfToken }),
    }),
  });
}

function clear(next) {
  generation += 1;
  chat.value = null;
  override.value = next;
}

async function generate(force = false) {
  const current = ++generation;
  if (!props.query || !props.items.length) return clear("idle");
  if (!session.user) return clear("login");
  if (!force && !shouldGenerate()) return clear("skipped");
  override.value = "checking";
  try { settings.value = await api.aiSettings(); }
  catch { override.value = "error"; return; }
  if (current !== generation) return;
  if (!settings.value.configured) return;
  const next = newChat();
  chat.value = next;
  override.value = "streaming";
  try {
    await next.sendMessage({ text: props.query }, {
      body: { query: props.query, items: contextItems.value },
    });
  } catch { /* Chat exposes the transport error through its state. */ }
}

watch(() => [props.query, signature.value], () => generate(), { immediate: true });
</script>

<template>
  <section class="ai-answer" role="region" aria-label="AI 回答" aria-live="polite">
    <header>
      <span>AI 回答</span>
      <small>基于当前 {{ contextItems.length }} 条可见平台资源 · 仅供参考</small>
      <button v-if="state === 'complete' || state === 'error'" type="button" title="重新生成" aria-label="重新生成 AI 回答" @click="generate(true)">
        <RotateCcw :size="14" aria-hidden="true" />
      </button>
    </header>
    <div v-if="state === 'login'" class="ai-answer-state">
      <p>登录后可基于当前检索结果生成摘要。</p>
      <RouterLink :to="{ name: 'login', query: { redirect: `/search?q=${encodeURIComponent(query)}` } }">登录后生成 AI 回答</RouterLink>
    </div>
    <div v-else-if="state === 'unconfigured'" class="ai-answer-state">
      <p>当前账号尚未配置可用模型。</p>
      <RouterLink :to="{ name: 'ai-settings' }">配置 AI 模型</RouterLink>
    </div>
    <div v-else-if="state === 'skipped'" class="ai-answer-state">
      <p>命中明确，未生成 AI 解读（省流模式）。</p>
      <button type="button" class="ai-generate" @click="generate(true)">生成 AI 解读</button>
    </div>
    <p v-else-if="state === 'checking'" class="ai-progress"><LoaderCircle class="spin" :size="16" />检查模型配置</p>
    <p v-else-if="state === 'streaming' || state === 'complete'" class="ai-answer-text">{{ text }}<span v-if="state === 'streaming'" class="stream-caret" /></p>
    <p v-else-if="state === 'error'" class="ai-answer-error" role="alert">{{ error }}</p>
    <p v-else class="ai-answer-state">当前结果不足以生成摘要。</p>
    <ol v-if="text" class="ai-answer-sources" aria-label="AI 回答引用来源">
      <li v-for="(item, index) in contextItems" :key="`${item.kind}-${item.id}`">
        <RouterLink v-if="item.kind === 'case'" :to="itemDestination(item)">〔{{ index + 1 }}〕{{ item.title }}</RouterLink>
        <a v-else-if="itemDestination(item)" :href="itemDestination(item)" target="_blank" rel="noopener noreferrer">〔{{ index + 1 }}〕{{ item.title }}</a>
        <span v-else>〔{{ index + 1 }}〕{{ item.title }}</span>
      </li>
    </ol>
  </section>
</template>
