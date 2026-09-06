<script setup>
import { Check, FilePlus2, LoaderCircle, RefreshCw, Upload } from "@lucide/vue";
import { onMounted, ref } from "vue";
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

function dateLabel(value) {
  return value ? String(value).slice(0, 10) : "日期待定";
}

function sizeLabel(size) {
  if (!Number.isFinite(size)) return "-";
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / 1024 / 1024).toFixed(1)} MB`;
}

function selectFile(event) {
  file.value = event.target.files?.[0] || null;
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

      <form class="skills-upload" aria-label="上传 Skill 包" @submit.prevent="submit">
        <label class="skills-file-button" title="选择 Skill 包">
          <FilePlus2 :size="19" aria-hidden="true" />
          <input
            type="file"
            accept=".zip,application/zip"
            required
            aria-label="选择 Skill 包"
            @change="selectFile"
          />
        </label>
        <span class="skills-file-selection" :title="file?.name">{{ file?.name || "未选择文件" }}</span>
        <button class="skills-upload-submit" type="submit" :disabled="uploading || !file">
          <LoaderCircle v-if="uploading" class="spin" :size="17" aria-hidden="true" />
          <Upload v-else :size="17" aria-hidden="true" />
          <span>{{ uploading ? "上传中" : "上传并识别" }}</span>
        </button>
      </form>
      <p v-if="uploadError" class="skills-error" role="alert">{{ uploadError }}</p>

      <section v-if="uploaded" class="skills-uploaded" aria-labelledby="skills-uploaded-title">
        <header>
          <div><span>识别结果</span><h2 id="skills-uploaded-title">{{ uploaded.skill.name }}</h2></div>
          <button
            type="button"
            data-testid="skill-publish-uploaded"
            :disabled="Boolean(publishing)"
            @click="publish(uploaded.skill.id, uploaded.version.id)"
          >
            <LoaderCircle v-if="publishing" class="spin" :size="15" aria-hidden="true" />
            <Check v-else :size="15" aria-hidden="true" />发布此版本
          </button>
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
        <div v-if="loading" class="skills-state"><LoaderCircle class="spin" :size="20" />正在加载 Skill 列表</div>
        <div v-else-if="error" class="skills-state skills-error" role="alert">
          {{ error }}<button type="button" @click="load"><RefreshCw :size="15" />重试</button>
        </div>
        <p v-else-if="!skills.length" class="skills-empty">暂无 Skill 包，请先上传</p>
        <article v-for="skill in skills" :key="skill.id" class="skill-card" :aria-label="`Skill：${skill.name}`">
          <header>
            <div>
              <h3>{{ skill.name }}</h3>
              <p>{{ skill.description || "暂无描述" }}</p>
            </div>
            <span v-if="skill.publishedVersionId" class="skill-published-tag">已发布</span>
          </header>
          <ul>
            <li v-for="version in skill.versions" :key="version.id">
              <b>{{ version.version }}</b>
              <span>{{ dateLabel(version.createdAt) }}</span>
              <em v-if="skill.publishedVersionId === version.id" data-testid="skill-version-published">当前发布</em>
              <button
                v-else
                type="button"
                :data-testid="`skill-publish-${version.id}`"
                :disabled="Boolean(publishing)"
                @click="publish(skill.id, version.id)"
              >
                <LoaderCircle v-if="publishing === version.id" class="spin" :size="14" aria-hidden="true" />发布
              </button>
            </li>
          </ul>
        </article>
      </section>
    </main>
  </div>
</template>
