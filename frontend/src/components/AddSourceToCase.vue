<script setup>
import { BookMarked, LoaderCircle, Search, X } from "@lucide/vue";
import { computed, ref } from "vue";
import { api } from "../api.js";
import { session } from "../session.js";

const props = defineProps({
  sourceCaseId: { type: String, required: true },
  versionId: { type: String, default: "" },
  sourceTitle: { type: String, default: "" },
});
const NEW_DRAFT = "__new__";
const PAGE_SIZE = 20;
const open = ref(false);
const loading = ref(false);
const busy = ref(false);
const error = ref("");
const drafts = ref([]);
const total = ref(0);
const page = ref(1);
const query = ref("");
const target = ref("");
const newTitle = ref("");
const addedCaseId = ref("");
const totalPages = computed(() => Math.max(1, Math.ceil(total.value / PAGE_SIZE)));
const targetLabel = computed(() => {
  if (target.value === NEW_DRAFT) return newTitle.value.trim() || "新建草稿";
  const draft = drafts.value.find((item) => item.id === target.value);
  return draft?.title || "未命名案例";
});

let requestSeq = 0;
let searchTimer = 0;

async function loadDrafts() {
  const seq = ++requestSeq;
  loading.value = true;
  error.value = "";
  try {
    const result = await api.listDrafts(query.value, page.value, PAGE_SIZE);
    if (seq !== requestSeq) return;
    drafts.value = result.items;
    total.value = result.total;
    if (!target.value) target.value = result.items[0]?.id || NEW_DRAFT;
  } catch (caught) {
    if (seq === requestSeq) error.value = caught.message || "草稿加载失败";
  } finally {
    if (seq === requestSeq) loading.value = false;
  }
}

function onSearchInput() {
  page.value = 1;
  clearTimeout(searchTimer);
  searchTimer = setTimeout(loadDrafts, 250);
}

function flipPage(delta) {
  page.value = Math.min(Math.max(1, page.value + delta), totalPages.value);
  loadDrafts();
}

function formatTime(iso) {
  if (!iso) return "";
  return new Date(iso).toLocaleString("zh-CN", {
    month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false,
  });
}

async function openDialog() {
  open.value = true;
  error.value = "";
  addedCaseId.value = "";
  target.value = "";
  page.value = 1;
  await loadDrafts();
}

function close() {
  if (!busy.value) open.value = false;
}

async function resolveTarget() {
  if (target.value === NEW_DRAFT) {
    const created = await api.createCase(
      { title: newTitle.value.trim() || "未命名案例" }, session.csrfToken,
    );
    const revision = created.revision ?? (await api.getCase(created.id)).revision;
    return { id: created.id, revision };
  }
  const record = await api.getCase(target.value);
  return { id: record.id, revision: record.revision };
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
  <button class="source-collect" type="button" @click="openDialog">
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
          <div class="collect-source-search">
            <Search :size="15" aria-hidden="true" />
            <input
              v-model="query"
              type="search"
              aria-label="按标题搜索草稿"
              placeholder="按标题搜索草稿"
              @input="onSearchInput"
            />
          </div>
          <p v-if="loading" class="collect-source-hint">正在加载我的草稿…</p>
          <p v-else-if="!drafts.length" class="collect-source-hint">
            {{ query ? "没有匹配标题的可编辑草稿。" : "还没有可编辑的本人草稿。" }}
          </p>
          <div v-else class="collect-source-list" role="radiogroup" aria-label="选择目标草稿">
            <label v-for="draft in drafts" :key="draft.id" class="collect-source-option">
              <input v-model="target" type="radio" name="collect-target" :value="draft.id" />
              <span class="collect-source-title">{{ draft.title || "未命名案例" }}</span>
              <small class="collect-source-time">更新于 {{ formatTime(draft.updatedAt) }}</small>
            </label>
            <label class="collect-source-option collect-source-new">
              <input v-model="target" type="radio" name="collect-target" :value="NEW_DRAFT" />
              <span class="collect-source-title">新建草稿</span>
              <input
                v-model="newTitle"
                class="collect-source-new-name"
                type="text"
                maxlength="80"
                aria-label="新草稿名称"
                placeholder="输入新草稿名称"
                @focus="target = NEW_DRAFT"
              />
            </label>
          </div>
          <div class="collect-source-pagination">
            <button type="button" :disabled="page <= 1 || loading" @click="flipPage(-1)">上一页</button>
            <span>第 {{ page }} / {{ totalPages }} 页 · 共 {{ total }} 个可编辑草稿</span>
            <button type="button" :disabled="page >= totalPages || loading" @click="flipPage(1)">下一页</button>
          </div>
          <p v-if="error" class="review-decision-error" role="alert">{{ error }}</p>
          <footer class="collect-source-footer">
            <button type="button" :disabled="busy" @click="close">取消</button>
            <button class="primary collect-source-confirm" type="submit" :disabled="busy || loading || !target">
              <LoaderCircle v-if="busy" class="spin" :size="14" aria-hidden="true" />
              {{ busy ? "正在加入" : `确认加入「${targetLabel}」` }}
            </button>
          </footer>
        </form>
      </section>
    </div>
  </Teleport>
</template>
