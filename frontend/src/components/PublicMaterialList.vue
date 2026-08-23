<script setup>
import { onMounted, ref } from "vue";
import { ExternalLink, FileSearch, LockKeyhole } from "@lucide/vue";
import { api } from "../api.js";
import { publicUrl } from "../lib/publicUrl.js";
import MaterialDownloadAction from "./MaterialDownloadAction.vue";

const props = defineProps({
  caseId: { type: String, required: true },
  versionId: { type: String, required: true },
});
const rows = ref([]);
const loading = ref(true);
const error = ref("");

async function loadMaterials() {
  try { rows.value = await api.listCaseMaterials(props.caseId, props.versionId); }
  catch (reason) { error.value = reason.message || "素材加载失败"; }
  finally { loading.value = false; }
}

function sourceUrl(row) {
  return row.contentAvailable ? publicUrl(row.sourceUrl) : "";
}

onMounted(loadMaterials);
</script>

<template>
  <section class="public-attachments public-materials" aria-labelledby="public-materials-title">
    <h2 id="public-materials-title"><FileSearch :size="16" />素材</h2>
    <p v-if="loading">正在加载素材</p>
    <p v-else-if="error" class="error-state">{{ error }}</p>
    <p v-else-if="!rows.length">暂无素材</p>
    <ul v-else>
      <li v-for="row in rows" :key="row.id">
        <FileSearch :size="16" aria-hidden="true" />
        <span>{{ row.title }}</span>
        <MaterialDownloadAction :material="row" />
        <a v-if="sourceUrl(row)" :href="sourceUrl(row)" target="_blank" rel="noopener noreferrer" :aria-label="`查看${row.title}来源`"><ExternalLink :size="15" /></a>
        <small v-else-if="!row.contentAvailable"><LockKeyhole :size="12" />内容按权限开放</small>
      </li>
    </ul>
  </section>
</template>
