<script setup>
import { ElAlert, ElButton, ElForm, ElFormItem, ElPopconfirm, ElTable, ElTableColumn, ElTag, ElUpload } from "element-plus";
import "element-plus/es/components/alert/style/css";
import "element-plus/es/components/button/style/css";
import "element-plus/es/components/form/style/css";
import "element-plus/es/components/popconfirm/style/css";
import "element-plus/es/components/table/style/css";
import "element-plus/es/components/tag/style/css";
import "element-plus/es/components/upload/style/css";
import { computed, reactive, ref } from "vue";
import { api } from "../api.js";
import AdminPagination from "../components/AdminPagination.vue";
import { useAdminPage } from "../composables/useAdminPage.js";
import { session } from "../session.js";

const catalog = reactive(useAdminPage(params => api.listAdminSkillVersions(params)));
const searchInput = ref("");
const error = ref("");
const file = ref(null);
const uploading = ref(false);
const uploadError = ref("");
const uploaded = ref(null);
const publishing = ref("");
const deleting = ref("");
const unpublishing = ref("");
const busy = computed(() => Boolean(publishing.value || deleting.value || unpublishing.value));
const actionError = ref("");
const rows = computed(() => catalog.items.flatMap((skill) =>
  skill.versions.map((version) => ({ skill, version })),
));

function dateLabel(value) {
  return value ? String(value).slice(0, 10) : "日期待定";
}

function isPublished(row) {
  return row.skill.publishedVersionId === row.version.id;
}

function onFileChange(uploadFile) {
  file.value = uploadFile.raw || null;
  uploadError.value = "";
  uploaded.value = null;
}

async function load() { await catalog.reload(); }

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
  if (busy.value) return;
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

async function removeVersion(row) {
  if (busy.value) return;
  deleting.value = row.version.id;
  actionError.value = "";
  try {
    await api.deleteSkillVersion(row.skill.id, row.version.id, session.csrfToken);
    if (uploaded.value?.version.id === row.version.id) uploaded.value = null;
    await load();
  } catch (reason) {
    actionError.value = reason.message || "Skill 版本删除失败";
  } finally {
    deleting.value = "";
  }
}

async function unpublish(row) {
  if (busy.value) return;
  unpublishing.value = row.version.id;
  actionError.value = "";
  try {
    await api.unpublishSkillVersion(row.skill.id, row.version.id, session.csrfToken);
    await load();
  } catch (reason) {
    actionError.value = reason.message || "取消发布失败";
  } finally {
    unpublishing.value = "";
  }
}

</script>

<template>
  <section class="skills-main admin-section">
      <header class="skills-heading"><h1>Skill 管理</h1></header>

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
            :disabled="busy"
            @click="publish(uploaded.skill.id, uploaded.version.id)"
          >发布此版本</el-button>
        </header>
        <p class="skills-uploaded-desc">{{ uploaded.skill.description || "暂无描述" }}</p>
        <dl>
          <div><dt>版本</dt><dd>{{ uploaded.version.version }}</dd></div>
        </dl>
      </section>

      <section class="skills-list" aria-labelledby="skills-list-title">
        <header><h2 id="skills-list-title">Skill 版本</h2><b>{{ catalog.total }}</b></header>
        <form class="admin-list-toolbar" role="search" aria-label="搜索 Skill" @submit.prevent="catalog.search(searchInput.trim())">
          <input v-model="searchInput" aria-label="Skill 名称" placeholder="搜索 Skill 名称" maxlength="200" />
          <select :value="catalog.status" aria-label="发布状态" @change="catalog.filter($event.target.value)"><option value="all">全部状态</option><option value="published">当前发布</option><option value="unpublished">未启用</option></select>
          <button class="secondary-button" type="submit">搜索</button>
        </form>
        <el-alert v-if="actionError" :title="actionError" type="error" role="alert" :closable="false" />
        <div v-if="catalog.loading" class="skills-state">正在加载 Skill 列表</div>
        <el-alert v-else-if="error || catalog.error" type="error" :title="error || catalog.error" role="alert" show-icon :closable="false">
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
              <el-tag v-else type="info">未启用</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="190">
            <template #default="{ row }">
              <el-button
                v-if="!isPublished(row)"
                size="small"
                type="primary"
                plain
                :data-testid="`skill-publish-${row.version.id}`"
                :loading="publishing === row.version.id"
                :disabled="busy"
                @click="publish(row.skill.id, row.version.id)"
              >发布</el-button>
              <el-popconfirm
                v-if="isPublished(row)"
                :title="`取消发布 ${row.skill.name} ${row.version.version}？`"
                confirm-button-text="取消发布"
                cancel-button-text="返回"
                :width="280"
                @confirm="unpublish(row)"
              >
                <template #reference>
                  <el-button
                    size="small"
                    :data-testid="`skill-unpublish-${row.version.id}`"
                    :loading="unpublishing === row.version.id"
                    :disabled="busy"
                  >取消发布</el-button>
                </template>
              </el-popconfirm>
              <el-button v-if="isPublished(row)" size="small" disabled title="请先取消发布">删除</el-button>
              <el-popconfirm
                v-else
                :title="`删除 ${row.skill.name} ${row.version.version}？`"
                confirm-button-text="删除"
                cancel-button-text="取消"
                :width="280"
                @confirm="removeVersion(row)"
              >
                <template #reference>
                  <el-button
                    size="small"
                    type="danger"
                    plain
                    :data-testid="`skill-delete-${row.version.id}`"
                    :loading="deleting === row.version.id"
                    :disabled="busy"
                  >删除</el-button>
                </template>
              </el-popconfirm>
            </template>
          </el-table-column>
          <template #empty>
            <span class="skills-empty">{{ catalog.query || catalog.status !== "all" ? "没有匹配的 Skill 版本" : "暂无 Skill 包，请先上传" }}</span>
          </template>
        </el-table>
        <AdminPagination :total="catalog.total" :page="catalog.page" :page-size="catalog.pageSize" :loading="catalog.loading" label="Skill 版本分页"
                         @page="catalog.page = $event" @page-size="catalog.resize" />
      </section>
  </section>
</template>
