<script setup>
import { computed, onMounted, ref } from "vue";
import { Download, FileSearch, FileText, LockKeyhole, Paperclip, Trash2, Upload } from "@lucide/vue";
import { api } from "../api.js";

const props = defineProps({
  caseRecord: { type: Object, required: true },
  user: { type: Object, default: null },
  editable: { type: Boolean, required: true },
  beforeMutation: { type: Function, required: true },
});
const emit = defineEmits(["case-refreshed", "mutation-state"]);
const rows = ref([]);
const materials = ref([]);
const folder = ref("files");
const loading = ref(true);
const error = ref("");
const busy = ref("");
const accessLevel = ref("private");
const countLabel = computed(() => `附件 ${rows.value.length}`);
const materialLabel = computed(() => `素材 ${materials.value.length}`);

const accessLabels = {
  public: "公开访问",
  campus: "校内访问",
  private: "私密",
};

async function loadAttachments() {
  loading.value = true;
  error.value = "";
  try {
    [rows.value, materials.value] = await Promise.all([
      api.listAttachments(props.caseRecord.id), api.listCaseMaterials(props.caseRecord.id),
    ]);
  } catch (caught) {
    error.value = caught.message || "附件加载失败";
  } finally {
    loading.value = false;
  }
}

async function refreshCase() {
  const value = await api.getCase(props.caseRecord.id);
  emit("case-refreshed", value);
  await loadAttachments();
}

async function mutate(name, operation) {
  if (busy.value) return;
  busy.value = name;
  emit("mutation-state", true);
  error.value = "";
  try {
    await operation(await props.beforeMutation());
    await refreshCase();
  } catch (caught) {
    error.value = caught.message || "附件操作失败";
  } finally {
    busy.value = "";
    emit("mutation-state", false);
  }
}

async function chooseFile(event) {
  const file = event.target.files?.[0];
  event.target.value = "";
  if (!file) return;
  await mutate("upload", (revision) => api.uploadAttachment(
    props.caseRecord.id, file, accessLevel.value, revision, props.user.csrfToken,
  ));
}

function remove(row) {
  return mutate(row.id, (revision) => api.deleteAttachment(
    props.caseRecord.id, row.id, revision, props.user.csrfToken,
  ));
}

function removeMaterial(row) {
  return mutate(row.id, (revision) => api.unmountCaseMaterial(
    props.caseRecord.id, row.id, revision, props.user.csrfToken,
  ));
}

function canDownload(row) {
  if (row.accessLevel === "public") return true;
  if (row.accessLevel === "campus") return Boolean(props.user);
  return Boolean(props.user && (
    props.user.role === "admin" || props.user.id === props.caseRecord.ownerId
  ));
}

function restriction(row) {
  return row.accessLevel === "campus" ? "登录后可下载" : "仅作者与管理员可下载";
}

function sizeLabel(size) {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KiB`;
  return `${(size / 1024 / 1024).toFixed(1)} MiB`;
}

onMounted(loadAttachments);
</script>

<template>
  <section class="assistant-panel attachment-panel">
    <RouterLink
      class="material-explorer-entry"
      :to="{ name: 'materials', query: { caseId: caseRecord.id } }"
      aria-label="打开素材掌控台"
    ><FileSearch :size="16" />打开素材掌控台</RouterLink>
    <div class="folder-tabs">
      <button :class="{ active: folder === 'files' }" type="button" @click="folder = 'files'">{{ countLabel }}</button>
      <button :class="{ active: folder === 'materials' }" type="button" @click="folder = 'materials'">{{ materialLabel }}</button>
    </div>
    <div class="panel-scroll">
      <div v-if="loading" class="panel-empty"><Paperclip :size="24" /><span>正在加载案例资料</span></div>
      <div v-else-if="error" class="attachment-error" role="alert">
        <span>{{ error }}</span><button type="button" @click="loadAttachments">重试</button>
      </div>
      <div v-else-if="folder === 'files' && !rows.length" class="panel-empty"><Paperclip :size="24" /><span>暂无附件</span></div>
      <ul v-else-if="folder === 'files'" class="attachment-list">
        <li v-for="row in rows" :key="row.id">
          <FileText :size="18" aria-hidden="true" />
          <div class="attachment-copy">
            <b>{{ row.name }}</b>
            <span>{{ accessLabels[row.accessLevel] }} · {{ sizeLabel(row.size) }}</span>
            <small v-if="!canDownload(row)"><LockKeyhole :size="12" />{{ restriction(row) }}</small>
          </div>
          <a
            v-if="canDownload(row)"
            class="attachment-icon"
            :href="api.attachmentContentUrl(caseRecord.id, row.id)"
            :aria-label="`下载${row.name}`"
            :title="`下载 ${row.name}`"
            download
          ><Download :size="16" /></a>
          <button
            v-if="editable"
            class="attachment-icon"
            type="button"
            :aria-label="`删除${row.name}`"
            :title="`删除 ${row.name}`"
            :disabled="Boolean(busy)"
            @click="remove(row)"
          ><Trash2 :size="16" /></button>
        </li>
      </ul>
      <div v-else-if="!materials.length" class="panel-empty"><FileSearch :size="24" /><span>暂无素材引用</span></div>
      <ul v-else class="attachment-list material-reference-list">
        <li v-for="row in materials" :key="row.id">
          <FileSearch :size="18" aria-hidden="true" />
          <div class="attachment-copy"><b>{{ row.title }}</b><span>{{ row.source }} · {{ row.materialType }}</span></div>
          <button v-if="editable" class="attachment-icon" type="button" :aria-label="`移除${row.title}`" :disabled="Boolean(busy)" @click="removeMaterial(row)"><Trash2 :size="16" /></button>
        </li>
      </ul>
    </div>
    <div v-if="editable && folder === 'files'" class="file-actions attachment-actions">
      <select v-model="accessLevel" aria-label="附件访问级别" :disabled="Boolean(busy)">
        <option value="private">私密</option>
        <option value="campus">校内访问</option>
        <option value="public">公开访问</option>
      </select>
      <label class="upload-control" :class="{ disabled: Boolean(busy) }">
        <Upload :size="15" /><span>{{ busy === "upload" ? "上传中" : "上传" }}</span>
        <input type="file" aria-label="选择附件" :disabled="Boolean(busy)" @change="chooseFile" />
      </label>
    </div>
  </section>
</template>
