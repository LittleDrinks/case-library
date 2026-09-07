<script setup>
import { ElAlert, ElButton, ElForm, ElFormItem, ElTable, ElTableColumn, ElTag, ElUpload } from "element-plus";
import "element-plus/es/components/alert/style/css";
import "element-plus/es/components/button/style/css";
import "element-plus/es/components/form/style/css";
import "element-plus/es/components/table/style/css";
import "element-plus/es/components/tag/style/css";
import "element-plus/es/components/upload/style/css";
import { computed, onMounted, ref } from "vue";
import { api } from "../api.js";
import SiteHeader from "../components/SiteHeader.vue";
import { session } from "../session.js";

const skills = ref([]);
const loading = ref(true);
const error = ref("");
const file = ref(null);
const uploading = ref(false);
const uploadError = ref("");
const uploaded = ref(null);
const publishing = ref("");
const rows = computed(() => skills.value.flatMap((skill) =>
  skill.versions.map((version) => ({ skill, version })),
));

function dateLabel(value) {
  return value ? String(value).slice(0, 10) : "日期待定";
}

function sizeLabel(size) {
  if (!Number.isFinite(size)) return "-";
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / 1024 / 1024).toFixed(1)} MB`;
}

function isPublished(row) {
  return row.skill.publishedVersionId === row.version.id;
}

function onFileChange(uploadFile) {
  file.value = uploadFile.raw || null;
  uploadError.value = "";
  uploaded.value = null;
}

async function load() {
  loading.value = true;
  error.value = "";
  try { skills.value = await api.listAdminSkills(); }
  catch (reason) { error.value = reason.message || "Skill 列表加载失败"; }
  finally { loading.value = false; }
}

async function submit() {
  if (!file.value || uploading.value) return;
  uploading.value = true;
  uploadError.value = "";
  uploaded.value = null;
  try {
    uploaded.value = await api.uploadSkillPackage(file.value, session.csrfToken);
    await load();
  } catch (reason) {
    uploadError.value = reason.message || "Skill 包上传失败";
  } finally {
    uploading.value = false;
  }
}

async function publish(skillId, versionId) {
  if (publishing.value) return;
  publishing.value = versionId;
  error.value = "";
  try {
    await api.publishSkillVersion(skillId, versionId, session.csrfToken);
    uploaded.value = null;
    await load();
  } catch (reason) {
    error.value = reason.message || "Skill 发布失败";
  } finally {
    publishing.value = "";
  }
}

onMounted(load);
</script>

<template>
  <div class="admin-page">
    <SiteHeader />
    <main id="main-content" class="skills-main">
      <header class="skills-heading">
        <div><span>Skill 管理</span><h1>Skill 包发布</h1></div>
        <RouterLink :to="{ name: 'admin-dashboard' }">返回管理后台</RouterLink>
      </header>

      <el-form class="skills-upload" aria-label="上传 Skill 包" @submit.prevent="submit">
        <el-form-item label="Skill 包">
          <el-upload
            :auto-upload="false"
            :show-file-list="false"
            accept=".zip,application/zip"
            @change="onFileChange"
          >
            <el-button aria-label="选择 Skill 包">选择文件</el-button>
          </el-upload>
          <span class="skills-file-selection" :title="file?.name">{{ file?.name || "未选择文件" }}</span>
        </el-form-item>
        <el-button
          class="skills-upload-submit"
          type="primary"
          native-type="submit"
          :loading="uploading"
          :disabled="!file"
        >上传并识别</el-button>
      </el-form>
      <el-alert
        v-if="uploadError"
        class="skills-error"
        type="error"
        :title="uploadError"
        role="alert"
        show-icon
        :closable="false"
      />

      <section v-if="uploaded" class="skills-uploaded" aria-labelledby="skills-uploaded-title">
        <header>
          <div><span>识别结果</span><h2 id="skills-uploaded-title">{{ uploaded.skill.name }}</h2></div>
          <el-button
            type="primary"
            data-testid="skill-publish-uploaded"
            :loading="Boolean(publishing)"
            @click="publish(uploaded.skill.id, uploaded.version.id)"
          >发布此版本</el-button>
        </header>
        <p class="skills-uploaded-desc">{{ uploaded.skill.description || "暂无描述" }}</p>
        <dl>
          <div><dt>版本</dt><dd>{{ uploaded.version.version }}</dd></div>
          <div><dt>文件数</dt><dd>{{ uploaded.version.fileCount }}</dd></div>
          <div><dt>大小</dt><dd>{{ sizeLabel(uploaded.version.size) }}</dd></div>
        </dl>
      </section>

      <section class="skills-list" aria-labelledby="skills-list-title">
        <header><div><span>已上传</span><h2 id="skills-list-title">Skill 列表</h2></div><b>{{ skills.length }}</b></header>
        <div v-if="loading" class="skills-state">正在加载 Skill 列表</div>
        <el-alert v-else-if="error" type="error" :title="error" role="alert" show-icon :closable="false">
          <el-button size="small" @click="load">重试</el-button>
        </el-alert>
        <el-table v-else :data="rows" aria-label="Skill 版本列表">
          <el-table-column prop="skill.name" label="Skill" min-width="140" />
          <el-table-column label="描述" min-width="180">
            <template #default="{ row }">{{ row.skill.description || "暂无描述" }}</template>
          </el-table-column>
          <el-table-column prop="version.version" label="版本" width="80" />
          <el-table-column label="上传时间" width="110">
            <template #default="{ row }">{{ dateLabel(row.version.createdAt) }}</template>
          </el-table-column>
          <el-table-column label="状态" width="110">
            <template #default="{ row }">
              <el-tag v-if="isPublished(row)" type="success" data-testid="skill-version-published">当前发布</el-tag>
              <el-tag v-else-if="row.skill.publishedVersionId" type="info">已发布</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="100">
            <template #default="{ row }">
              <el-button
                v-if="!isPublished(row)"
                size="small"
                type="primary"
                plain
                :data-testid="`skill-publish-${row.version.id}`"
                :loading="publishing === row.version.id"
                @click="publish(row.skill.id, row.version.id)"
              >发布</el-button>
            </template>
          </el-table-column>
          <template #empty>
            <span class="skills-empty">暂无 Skill 包，请先上传</span>
          </template>
        </el-table>
      </section>
    </main>
  </div>
</template>
