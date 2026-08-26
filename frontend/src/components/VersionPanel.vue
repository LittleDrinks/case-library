<script setup>
import { computed, onMounted, ref } from "vue";
import { History, RotateCcw, Save } from "@lucide/vue";
import { api } from "../api.js";

const props = defineProps({
  caseRecord: { type: Object, required: true },
  user: { type: Object, required: true },
  editable: { type: Boolean, required: true },
  mutationBusy: { type: Boolean, default: false },
  beforeMutation: { type: Function, required: true },
});
const emit = defineEmits(["case-refreshed", "case-restored", "version-mutation-state"]);
const history = ref({ versions: [], snapshots: [] });
const loading = ref(true);
const error = ref("");
const busy = ref("");
const running = computed(() => Boolean(busy.value || props.mutationBusy));
const snapshotLabel = computed(() => (running.value ? "处理中" : "创建快照"));
const entries = computed(() => orderedEntries());

function label(entry) {
  if (entry.kind === "submission") return `提交版本 v${entry.number}`;
  return entry.kind === "manual" ? "手动快照" : "回滚前快照";
}

function orderedEntries() {
  return [...history.value.versions, ...history.value.snapshots]
    .sort((left, right) => right.createdAt.localeCompare(left.createdAt));
}

function time(value) {
  return new Date(value).toLocaleString("zh-CN", { hour12: false });
}

async function loadHistory() {
  loading.value = true;
  error.value = "";
  try {
    history.value = await api.caseHistory(props.caseRecord.id);
  } catch (caught) {
    error.value = caught.message || "版本历史加载失败";
  } finally {
    loading.value = false;
  }
}

async function run(command, targetId) {
  if (running.value) return;
  busy.value = command;
  emit("version-mutation-state", true);
  error.value = "";
  try {
    const revision = await props.beforeMutation();
    const result = await api.lifecycleCase(props.caseRecord.id, {
      command, revision, targetId,
    }, props.user.csrfToken);
    emit(command === "rollback" ? "case-restored" : "case-refreshed", result.case);
    await loadHistory();
  } catch (caught) {
    error.value = caught.message || "版本操作失败";
  } finally {
    busy.value = "";
    emit("version-mutation-state", false);
  }
}

function rollback(entry) {
  if (!window.confirm(`回滚到${label(entry)}？当前内容会自动保存为回滚前快照。`)) return;
  void run("rollback", entry.id);
}

onMounted(loadHistory);
</script>

<template>
  <section class="assistant-panel version-panel">
    <div class="panel-head version-head">
      <b>版本历史</b>
      <button v-show="editable || running" type="button" :disabled="!editable || running" @click="run('snapshot')">
        <Save :size="14" />{{ snapshotLabel }}
      </button>
    </div>
    <div class="panel-scroll">
      <div v-if="loading" class="panel-empty"><History :size="24" /><span>正在加载版本</span></div>
      <div v-else-if="error" class="attachment-error" role="alert">
        <span>{{ error }}</span><button type="button" @click="loadHistory">重试</button>
      </div>
      <div v-else-if="!entries.length" class="panel-empty"><History :size="24" /><span>暂无版本</span></div>
      <ul v-else class="version-list">
        <li v-for="entry in entries" :key="entry.id">
          <div><b>{{ label(entry) }}</b><span>{{ time(entry.createdAt) }}</span></div>
          <button
            v-show="editable || running"
            type="button"
            :aria-label="`回滚到${label(entry)}`"
            :title="`回滚到${label(entry)}`"
            :disabled="!editable || running"
            @click="rollback(entry)"
          ><RotateCcw :size="15" /></button>
        </li>
      </ul>
    </div>
  </section>
</template>
