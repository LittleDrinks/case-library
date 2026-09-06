<script setup>
import { LoaderCircle, Pencil, Plus, RefreshCw, Tags } from "@lucide/vue";
import { onMounted, ref } from "vue";
import { api } from "../api.js";
import SiteHeader from "../components/SiteHeader.vue";
import { session } from "../session.js";

const groups = ref([]);
const loading = ref(true);
const error = ref("");
const actionError = ref("");
const newGroupName = ref("");
const newTagNames = ref({});
const editing = ref(null);

async function load() {
  loading.value = true;
  error.value = "";
  try { groups.value = await api.listTagGroups(); }
  catch (reason) { error.value = reason.message || "标签目录加载失败"; }
  finally { loading.value = false; }
}

async function run(action) {
  actionError.value = "";
  try {
    await action();
    groups.value = await api.listTagGroups();
  } catch (reason) {
    actionError.value = reason.message || "操作失败";
  }
}

function createGroup() {
  const name = newGroupName.value.trim();
  if (!name) return;
  newGroupName.value = "";
  void run(() => api.createTagGroup({ name }, session.csrfToken));
}

function toggleRequired(group) {
  void run(() => api.updateTagGroup(group.id, {
    requiredForSubmission: !group.requiredForSubmission,
  }, session.csrfToken));
}

function toggleGroupEnabled(group) {
  void run(() => api.updateTagGroup(group.id, { enabled: !group.enabled }, session.csrfToken));
}

function createTag(group) {
  const name = (newTagNames.value[group.id] || "").trim();
  if (!name) return;
  newTagNames.value = { ...newTagNames.value, [group.id]: "" };
  void run(() => api.createTag(group.id, { name }, session.csrfToken));
}

function toggleTagEnabled(tag) {
  void run(() => api.updateTag(tag.id, { enabled: !tag.enabled }, session.csrfToken));
}

function startEdit(kind, item) {
  editing.value = { kind, id: item.id, name: item.name };
}

function saveEdit() {
  const current = editing.value;
  editing.value = null;
  if (!current) return;
  const name = current.name.trim();
  if (!name) return;
  const request = current.kind === "group"
    ? api.updateTagGroup(current.id, { name }, session.csrfToken)
    : api.updateTag(current.id, { name }, session.csrfToken);
  void run(() => request);
}

onMounted(load);
</script>

<template>
  <div class="admin-page">
    <SiteHeader />
    <main id="main-content" class="admin-main">
      <header class="admin-heading">
        <div><span>平台管理</span><h1>标签目录</h1></div>
        <nav aria-label="管理工具">
          <RouterLink :to="{ name: 'admin-dashboard' }"><Tags :size="16" />管理后台</RouterLink>
        </nav>
      </header>
      <form class="tag-group-create" @submit.prevent="createGroup">
        <input v-model="newGroupName" aria-label="新标签组名称" placeholder="新标签组名称，如学科、课程" maxlength="80" />
        <button type="submit"><Plus :size="15" />新建标签组</button>
      </form>
      <p v-if="actionError" class="tag-catalog-error" role="alert">{{ actionError }}</p>
      <div v-if="loading" class="admin-state"><LoaderCircle class="spin" :size="20" />正在加载标签目录</div>
      <div v-else-if="error" class="admin-state error-state" role="alert">
        {{ error }}<button type="button" @click="load"><RefreshCw :size="15" />重试</button>
      </div>
      <p v-else-if="!groups.length" class="admin-empty">暂无标签组，先创建一个标签组</p>
      <section v-for="group in groups" :key="group.id" class="tag-group" :class="{ 'tag-disabled': !group.enabled }" :aria-label="`标签组：${group.name}`">
        <header>
          <input v-if="editing?.kind === 'group' && editing.id === group.id" v-model="editing.name" aria-label="标签组名称" maxlength="80" @keyup.enter="saveEdit" @blur="saveEdit" />
          <h2 v-else>{{ group.name }}<b v-if="group.requiredForSubmission">投稿必填</b><b v-if="!group.enabled" class="tag-disabled-mark">已停用</b></h2>
          <label><input type="checkbox" :checked="group.requiredForSubmission" :disabled="!group.enabled" @change="toggleRequired(group)" />投稿必填</label>
          <button type="button" :aria-label="`重命名标签组：${group.name}`" @click="startEdit('group', group)"><Pencil :size="13" />重命名</button>
          <button type="button" :aria-label="`${group.enabled ? '停用' : '启用'}标签组：${group.name}`" @click="toggleGroupEnabled(group)">
            {{ group.enabled ? "停用" : "启用" }}
          </button>
        </header>
        <ul>
          <li v-for="tag in group.tags" :key="tag.id" :class="{ 'tag-disabled': !tag.enabled }">
            <input v-if="editing?.kind === 'tag' && editing.id === tag.id" v-model="editing.name" aria-label="标签名称" maxlength="80" @keyup.enter="saveEdit" @blur="saveEdit" />
            <span v-else>{{ tag.name }}<b v-if="!tag.enabled" class="tag-disabled-mark">已停用</b></span>
            <button type="button" :aria-label="`重命名标签：${tag.name}`" @click="startEdit('tag', tag)"><Pencil :size="12" /></button>
            <button type="button" :aria-label="`${tag.enabled ? '停用' : '启用'}标签：${tag.name}`" @click="toggleTagEnabled(tag)">
              {{ tag.enabled ? "停用" : "启用" }}
            </button>
          </li>
        </ul>
        <form v-if="group.enabled" @submit.prevent="createTag(group)">
          <input v-model="newTagNames[group.id]" :aria-label="`在${group.name}添加标签`" placeholder="新标签名称" maxlength="80" />
          <button type="submit"><Plus :size="13" />添加标签</button>
        </form>
      </section>
    </main>
  </div>
</template>
