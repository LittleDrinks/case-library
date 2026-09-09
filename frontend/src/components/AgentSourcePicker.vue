<script setup>
import { BookOpen, ChevronDown, RefreshCw, Search, X } from "@lucide/vue";
import { computed, onMounted, ref, watch } from "vue";
import { ElPopover } from "element-plus";
import { api } from "../api.js";
import { conversationSourceKey, useConversationSources } from "../composables/useConversationSources.js";

const props = defineProps({
  caseId: { type: String, required: true },
  versionId: { type: String, default: "" },
  readOnly: { type: Boolean, default: false },
  disabled: { type: Boolean, default: false },
});
const { sources, has, toggle, clear } = useConversationSources();
const entries = ref([]);
const query = ref("");
const error = ref("");
const loading = ref(false);
const open = ref(false);
let loadToken = 0;

function openPicker() {
  open.value = true;
}

const visibleEntries = computed(() => {
  const term = query.value.trim().toLowerCase();
  return entries.value.filter((row) => !term || sourceLabel(row).toLowerCase().includes(term));
});

function sourceLabel(source) {
  return source.title || source.id;
}

function sourceMeta(source) {
  const kind = { attachment: "附件", material: "素材", case: "案例来源" }[source.sourceType] || "资料";
  return [source.version, String(source.publishedAt || "").slice(0, 10)].filter(Boolean).join(" · ") || kind;
}

async function load() {
  const token = ++loadToken;
  loading.value = true;
  try {
    const list = (await api.listSources(props.caseId, props.versionId || undefined)).entries || [];
    if (token === loadToken) {
      entries.value = list;
      error.value = "";
    }
  } catch {
    if (token === loadToken) error.value = "资料区加载失败";
  } finally {
    if (token === loadToken) loading.value = false;
  }
}

watch(() => props.versionId, () => {
  query.value = "";
  entries.value = [];
  clear();
  load();
});

onMounted(load);
defineExpose({ openPicker });
</script>

<template>
  <div class="agent-source-picker" data-testid="agent-source-picker">
    <ElPopover
    <ElPopover
      v-model:visible="open"
      trigger="click"
      placement="top-start"
      :width="340"
      popper-class="composer-popover source-popover"
      :show-arrow="false"
    >
      <template #reference>
        <button
          type="button"
          class="context-trigger"
          data-testid="agent-source-picker-toggle"
          aria-label="选择对话资料"
          :aria-expanded="open"
        >
          <BookOpen :size="14" aria-hidden="true" /><span>资料</span>
          <b v-if="sources.length" class="count">{{ sources.length }}</b>
          <ChevronDown :size="12" aria-hidden="true" />
        </button>
      </template>
      <div class="picker-heading">
        <div><b>本次对话参考资料</b><small>选择让 AI 重点参考的内容，不会插入正文引用</small></div>
        <button type="button" aria-label="关闭资料选择" @click="open = false"><X :size="15" /></button>
      </div>
      <div class="picker-search">
        <Search :size="15" aria-hidden="true" />
        <input v-model="query" aria-label="搜索本案例资料" placeholder="搜索本案例资料" />
      </div>
      <div class="picker-items">
        <p v-if="loading" class="empty-picker">正在加载资料</p>
        <label
          v-else
          v-for="source in visibleEntries"
          :key="conversationSourceKey(source)"
          class="picker-row"
          data-testid="agent-source-option"
        >
          <input
            type="checkbox"
            :checked="has(source)"
            :disabled="disabled"
            @change="toggle(source)"
          />
          <span><b>{{ sourceLabel(source) }}</b><small>{{ sourceMeta(source) }}</small></span>
        </label>
        <p v-if="!loading && !visibleEntries.length" class="empty-picker">没有匹配的资料</p>
        <p v-if="error" class="picker-error" role="alert">
          {{ error }}
          <button type="button" aria-label="重新加载资料" @click="load"><RefreshCw :size="12" />重试</button>
        </p>
      </div>
      <div class="picker-bottom">
        <small>已选 {{ sources.length }} 项 · 仅作为对话上下文</small>
        <button type="button" @click="open = false">完成</button>
      </div>
    </ElPopover>
  </div>
</template>
