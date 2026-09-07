<script setup>
import { BookMarked, LoaderCircle, X } from "@lucide/vue";
import { ref } from "vue";
import { api } from "../api.js";
import { session } from "../session.js";

const props = defineProps({
  sourceCaseId: { type: String, required: true },
  versionId: { type: String, default: "" },
  sourceTitle: { type: String, default: "" },
});
const NEW_DRAFT = "__new__";
const open = ref(false);
const loading = ref(false);
const busy = ref(false);
const error = ref("");
const drafts = ref([]);
const target = ref("");
const addedCaseId = ref("");

async function openDialog() {
  open.value = true;
  error.value = "";
  addedCaseId.value = "";
  loading.value = true;
  try {
    const mine = await api.listCases("mine");
    drafts.value = mine.filter((item) => item.workflowStatus === "draft");
    target.value = drafts.value[0]?.id || NEW_DRAFT;
  } catch (caught) {
    error.value = caught.message || "我的案例加载失败";
  } finally {
    loading.value = false;
  }
}

function close() {
  if (!busy.value) open.value = false;
}

async function resolveRevision(id, revision) {
  if (revision != null) return revision;
  return (await api.getCase(id)).revision;
}

async function resolveTarget() {
  if (target.value === NEW_DRAFT) {
    const created = await api.createCase({ title: "未命名案例" }, session.csrfToken);
    return { id: created.id, revision: await resolveRevision(created.id, created.revision) };
  }
  const draft = drafts.value.find((item) => item.id === target.value);
  return { id: draft.id, revision: await resolveRevision(draft.id, draft.revision) };
}

async function confirm() {
  if (busy.value || loading.value || !target.value) return;
  busy.value = true;
  error.value = "";
  try {
    const draft = await resolveTarget();
    await api.addCaseSource(draft.id, {
      sourceCaseId: props.sourceCaseId,
      versionId: props.versionId || undefined,
      revision: draft.revision,
    }, session.csrfToken);
    addedCaseId.value = draft.id;
  } catch (caught) {
    error.value = caught.status === 409
      ? "该来源已加入此案例，不会重复添加。" : caught.message || "加入失败";
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <button class="case-detail-collect" type="button" @click="openDialog">
    <BookMarked :size="16" aria-hidden="true" />加入我的案例
  </button>
  <Teleport to="body">
    <div v-if="open" class="review-decision-backdrop" @mousedown.self="close" @keydown.esc="close">
      <section class="review-decision-dialog collect-source-dialog" role="dialog" aria-modal="true" aria-labelledby="collect-source-title">
        <header>
          <h2 id="collect-source-title">加入我的案例</h2>
          <button type="button" title="关闭" aria-label="关闭" :disabled="busy" @click="close"><X :size="18" /></button>
        </header>
        <div v-if="addedCaseId" class="collect-source-done">
          <p>已将「{{ sourceTitle }}」的固定版本加入资料区来源。</p>
          <RouterLink :to="{ name: 'workbench', params: { id: addedCaseId } }">前往工作台继续编辑</RouterLink>
        </div>
        <form v-else @submit.prevent="confirm">
          <p class="collect-source-hint">只加入来源条目，不复制来源正文与私人对话。</p>
          <p v-if="loading" class="collect-source-hint">正在加载我的草稿…</p>
          <template v-else>
            <label v-for="draft in drafts" :key="draft.id" class="collect-source-option">
              <input v-model="target" type="radio" name="collect-target" :value="draft.id" />
              <span>{{ draft.title || "未命名案例" }}</span>
            </label>
            <label class="collect-source-option">
              <input v-model="target" type="radio" name="collect-target" :value="NEW_DRAFT" />
              <span>新建草稿</span>
            </label>
          </template>
          <p v-if="error" class="review-decision-error" role="alert">{{ error }}</p>
          <footer>
            <button type="button" :disabled="busy" @click="close">取消</button>
            <button class="primary" type="submit" :disabled="busy || loading || !target">
              <LoaderCircle v-if="busy" class="spin" :size="14" aria-hidden="true" />
              {{ busy ? "正在加入" : "确认加入" }}
            </button>
          </footer>
        </form>
      </section>
    </div>
  </Teleport>
</template>
