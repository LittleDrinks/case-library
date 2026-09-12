<script setup>
import { computed, onMounted, ref, watch } from "vue";
import { History, Plus, Save, X } from "@lucide/vue";
import { api } from "../api.js";
import { versionLabel } from "../lib/version.js";

const props = defineProps({
  caseRecord: { type: Object, required: true },
  refreshKey: { type: Number, default: 0 },
  editable: { type: Boolean, default: false },
  csrfToken: { type: String, default: "" },
});
const emit = defineEmits(["open-version", "version-created"]);
const versions = ref([]);
const loading = ref(true);
const error = ref("");
const formOpen = ref(false);
const versionTitle = ref("");
const creating = ref(false);
const createError = ref("");

const timeline = computed(() => [...versions.value].sort((left, right) => right.number - left.number));

function time(value) {
  return new Date(value).toLocaleString("zh-CN", {
    month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false,
  });
}

async function loadHistory() {
  loading.value = true;
  error.value = "";
  try {
    const history = await api.caseHistory(props.caseRecord.id);
    versions.value = history.versions;
  } catch (caught) {
    error.value = caught.message || "版本历史加载失败";
  } finally {
    loading.value = false;
  }
}

function toggleForm() {
  if (creating.value) return;
  formOpen.value = !formOpen.value;
  createError.value = "";
}

function cancelCreate() {
  formOpen.value = false;
  versionTitle.value = "";
  createError.value = "";
}

async function saveVersion() {
  const title = versionTitle.value.trim();
  if (!title) { createError.value = "请填写版本名称"; return; }
  creating.value = true;
  createError.value = "";
  try {
    const version = await api.createManualVersion(
      props.caseRecord.id, title, props.caseRecord.revision, props.csrfToken,
    );
    versions.value = [version, ...versions.value.filter((item) => item.id !== version.id)];
    cancelCreate();
    emit("version-created", version);
  } catch (caught) {
    createError.value = caught.message || "版本保存失败";
  } finally {
    creating.value = false;
  }
}

watch(() => [props.caseRecord.id, props.caseRecord.versionNumber, props.refreshKey], loadHistory);
onMounted(loadHistory);
</script>

<template>
  <section class="assistant-panel version-panel">
    <div class="panel-head version-head">
      <div class="version-heading"><b>历史版本</b><span class="version-count">{{ timeline.length }}</span></div>
      <button v-if="editable" type="button" aria-label="新建版本" :aria-expanded="formOpen" @click="toggleForm">
        <Plus :size="14" aria-hidden="true" />新建版本
      </button>
    </div>
    <div class="panel-scroll">
      <form v-if="formOpen" class="version-create-form" @submit.prevent="saveVersion">
        <label for="version-title">版本名称</label>
        <input id="version-title" v-model="versionTitle" maxlength="80" autocomplete="off" placeholder="例如：补充教学目标" />
        <p v-if="createError" class="version-create-error" role="alert">{{ createError }}</p>
        <footer>
          <button type="button" @click="cancelCreate"><X :size="14" aria-hidden="true" />取消</button>
          <button class="primary" type="submit" :disabled="creating"><Save :size="14" aria-hidden="true" />{{ creating ? "保存中" : "保存版本" }}</button>
        </footer>
      </form>
      <p class="version-note">提交、完整生成、接受 AI 建议或手动命名后会生成历史版本。</p>
      <div v-if="loading" class="panel-empty"><History :size="24" /><span>正在加载版本</span></div>
      <div v-else-if="error" class="attachment-error" role="alert">
        <span>{{ error }}</span><button type="button" @click="loadHistory">重试</button>
      </div>
      <p v-else-if="!timeline.length" class="version-note">还没有历史版本；提交、完整生成、接受 AI 建议或手动命名后会显示。</p>
      <ol v-else class="version-timeline">
        <li v-for="version in timeline" :key="version.id">
          <span class="timeline-dot" aria-hidden="true" />
          <div class="version-meta">
            <small>{{ time(version.createdAt) }}</small>
            <b>{{ versionLabel(version) }}</b>
          </div>
          <button type="button" :aria-label="`查看历史版本 ${versionLabel(version)}`" @click="emit('open-version', version)">
            查看历史版本
          </button>
        </li>
      </ol>
    </div>
  </section>
</template>
