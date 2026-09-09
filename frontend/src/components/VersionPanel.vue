<script setup>
import { computed, onMounted, ref, watch } from "vue";
import { History } from "@lucide/vue";
import { api } from "../api.js";
import { versionLabel } from "../lib/version.js";

const props = defineProps({
  caseRecord: { type: Object, required: true },
  refreshKey: { type: Number, default: 0 },
});
const emit = defineEmits(["open-version"]);
const versions = ref([]);
const loading = ref(true);
const error = ref("");

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

watch(() => [props.caseRecord.id, props.caseRecord.versionNumber, props.refreshKey], loadHistory);
onMounted(loadHistory);
</script>

<template>
  <section class="assistant-panel version-panel">
    <div class="panel-head version-head">
      <b>版本时间线</b>
    </div>
    <div class="panel-scroll">
      <p class="version-note">提交审核或 AI 完整生成时创建版本；普通聊天、局部修订、普通编辑与保存不新增版本。</p>
      <div v-if="loading" class="panel-empty"><History :size="24" /><span>正在加载版本</span></div>
      <div v-else-if="error" class="attachment-error" role="alert">
        <span>{{ error }}</span><button type="button" @click="loadHistory">重试</button>
      </div>
      <p v-else-if="!timeline.length" class="version-note">还没有历史版本，提交或完整生成后会出现在这里。</p>
      <ol v-else class="version-timeline">
        <li v-for="version in timeline" :key="version.id">
          <span class="timeline-dot" aria-hidden="true" />
          <div class="version-meta">
            <small>{{ time(version.createdAt) }}</small>
            <b>{{ versionLabel(version) }}</b>
          </div>
          <button type="button" :aria-label="`打开 ${versionLabel(version)} 版本`" @click="emit('open-version', version)">
            打开
          </button>
        </li>
      </ol>
    </div>
  </section>
</template>
