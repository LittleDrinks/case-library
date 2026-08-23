<script setup>
import { onMounted, ref } from "vue";
import { Download, FileText, LockKeyhole, Paperclip } from "@lucide/vue";
import { api } from "../api.js";
import { session } from "../session.js";

const props = defineProps({
  caseId: { type: String, required: true },
  versionId: { type: String, required: true },
  isOwner: { type: Boolean, default: false },
});
const rows = ref([]);
const loading = ref(true);
const error = ref("");

async function loadAttachments() {
  try {
    rows.value = await api.listAttachments(props.caseId, props.versionId);
  } catch (reason) {
    error.value = reason.message || "附件加载失败";
  } finally {
    loading.value = false;
  }
}

function canDownload(row) {
  if (row.accessLevel === "public") return true;
  if (row.accessLevel === "campus") return Boolean(session.user);
  return session.user?.role === "admin" || props.isOwner;
}

function downloadUrl(row) {
  return api.attachmentContentUrl(props.caseId, row.id, props.versionId);
}

onMounted(loadAttachments);
</script>

<template>
  <section class="public-attachments" aria-labelledby="public-attachments-title">
    <h2 id="public-attachments-title"><Paperclip :size="16" />附件</h2>
    <p v-if="loading">正在加载附件</p>
    <p v-else-if="error" class="error-state">{{ error }}</p>
    <p v-else-if="!rows.length">暂无附件</p>
    <ul v-else>
      <li v-for="row in rows" :key="row.id">
        <FileText :size="16" aria-hidden="true" />
        <span>{{ row.name }}</span>
        <a v-if="canDownload(row)" :href="downloadUrl(row)" :aria-label="`下载${row.name}`" download><Download :size="15" /></a>
        <small v-else><LockKeyhole :size="12" />仅作者与管理员可下载</small>
      </li>
    </ul>
  </section>
</template>
