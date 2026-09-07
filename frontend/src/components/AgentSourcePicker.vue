<script setup>
import { computed, onMounted, ref, watch } from "vue";
import { LoaderCircle, Plus, Search, X } from "@lucide/vue";
import { api } from "../api.js";
import { session } from "../session.js";

const props = defineProps({
  caseId: { type: String, required: true },
  revision: { type: Number, default: 1 },
  versionId: { type: String, default: "" },
  readOnly: { type: Boolean, default: false },
  selected: { type: Array, default: () => [] },
  disabled: { type: Boolean, default: false },
});
const emit = defineEmits(["update:selected", "case-refreshed"]);
const entries = ref([]);
const results = ref([]);
const query = ref("");
const error = ref("");
const loading = ref(false);
const adding = ref("");
const open = ref(false);
let loadToken = 0;

function sourceKey(source) {
  return `${source.sourceType}:${source.id}`;
}

function isSelected(source) {
  return props.selected.some((item) => sourceKey(item) === sourceKey(source));
}

function toggle(source) {
  const next = isSelected(source)
    ? props.selected.filter((item) => sourceKey(item) !== sourceKey(source))
    : [...props.selected, source];
  emit("update:selected", next);
}

function remove(source) {
  emit("update:selected", props.selected.filter((item) => sourceKey(item) !== sourceKey(source)));
}

function sourceLabel(source) {
  return source.title || source.id;
}

const visibleEntries = computed(() => {
  const term = query.value.trim().toLowerCase();
  return entries.value.filter((item) => !term || sourceLabel(item).toLowerCase().includes(term));
});

async function load() {
  if (props.readOnly && !props.versionId) return;
  const token = ++loadToken;
  const scope = props.readOnly ? props.versionId : "";
  try {
    const list = (await api.listSources(props.caseId, scope)).entries || [];
    if (token === loadToken) {
      entries.value = list;
      error.value = "";
    }
  } catch {
    if (token === loadToken) error.value = "资料区加载失败";
  }
}

watch(() => props.versionId, () => {
  emit("update:selected", []);
  entries.value = [];
  results.value = [];
  query.value = "";
  void load();
});

async function search() {
  if (props.readOnly || !query.value.trim()) return;
  loading.value = true;
  error.value = "";
  try {
    results.value = (await api.search(query.value.trim(), "all", null, 10)).items || [];
  } catch (caught) {
    error.value = caught.message || "检索失败";
  } finally {
    loading.value = false;
  }
}

function addable(item) {
  return !props.readOnly && ["case", "material"].includes(item.kind) && props.revision > 0;
}

async function addCandidate(item) {
  if (!addable(item)) return;
  adding.value = item.id;
  error.value = "";
  try {
    const payload = item.kind === "material"
      ? api.mountCaseMaterial(props.caseId, item.id, props.revision, session.csrfToken)
      : api.addCaseSource(props.caseId, { sourceCaseId: item.id, revision: props.revision }, session.csrfToken);
    await payload;
    await load();
    emit("case-refreshed", await api.getCase(props.caseId));
  } catch (caught) {
    error.value = caught.message || "加入资料区失败";
  } finally {
    adding.value = "";
  }
}

onMounted(load);
</script>

<template>
  <div class="agent-source-picker" data-testid="agent-source-picker">
    <div class="agent-source-picker-head">
      <button type="button" class="agent-source-picker-toggle" @click="open = !open">
        <span>资料上下文</span><b v-if="selected.length">{{ selected.length }}</b>
      </button>
      <span v-if="selected.length" class="agent-source-summary">已选 {{ selected.length }} 条</span>
    </div>
    <div v-if="open" class="agent-source-picker-body">
      <div v-if="selected.length" class="agent-source-chips" aria-label="已选来源">
        <span v-for="source in selected" :key="sourceKey(source)" class="agent-source-chip">
          {{ sourceLabel(source) }}
          <button type="button" :aria-label="`移除${sourceLabel(source)}`" @click="remove(source)"><X :size="12" /></button>
        </span>
      </div>
      <div v-if="!readOnly" class="agent-source-search">
        <input v-model="query" aria-label="检索资料" placeholder="检索资料区或平台来源" @keydown.enter="search" />
        <button type="button" aria-label="检索资料" :disabled="disabled || loading" @click="search">
          <LoaderCircle v-if="loading" class="spin" :size="14" /><Search v-else :size="14" />
        </button>
      </div>
      <label v-for="source in visibleEntries" :key="sourceKey(source)" class="agent-source-option">
        <input type="checkbox" :checked="isSelected(source)" :disabled="disabled" @change="toggle(source)" />
        <span>{{ sourceLabel(source) }}</span><small>{{ source.sourceType }}</small>
      </label>
      <div v-for="item in results" :key="`${item.kind}:${item.id}`" class="agent-source-result">
        <span>{{ item.title || item.id }}</span>
        <button v-if="addable(item)" type="button" :disabled="Boolean(adding)" @click="addCandidate(item)">
          <Plus :size="13" />{{ adding === item.id ? "加入中" : "确认加入资料区" }}
        </button>
        <small v-else>本轮检索可读</small>
      </div>
      <p v-if="error" class="agent-source-error" role="alert">{{ error }}</p>
      <p v-if="!visibleEntries.length && !results.length" class="agent-source-empty">资料区暂无匹配来源</p>
    </div>
  </div>
</template>
