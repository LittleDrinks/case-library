<template>
  <div class="case-library">
    <!-- Header -->
    <div class="library-header">
      <h1 class="page-title">案例库</h1>
      <p class="page-desc">浏览和搜索已公开的思政案例资源。</p>
    </div>

    <!-- Search and filters -->
    <div class="filter-bar">
      <div class="search-box">
        <BaseInput
          v-model="searchInput"
          placeholder="搜索案例标题、内容..."
          @keydown.enter="applySearch"
        >
          <template #suffix>
            <BaseButton variant="primary" size="md" @click="applySearch">
              搜索
            </BaseButton>
          </template>
        </BaseInput>
      </div>
      <div class="filter-selects">
        <BaseSelect
          v-model="filterType"
          :options="typeOptions"
          placeholder="全部类型"
          @change="applyFilters"
        />
        <BaseSelect
          v-model="filterTheme"
          :options="themes"
          placeholder="全部主题"
          @change="applyFilters"
        />
      </div>
    </div>

    <!-- Active filter chips -->
    <div v-if="hasActiveFilters" class="filter-chips">
      <span v-if="appliedKeyword" class="chip">
        搜索: {{ appliedKeyword }}
        <button type="button" class="chip-remove" @click="clearSearch">×</button>
      </span>
      <span v-if="filterType" class="chip">
        类型: {{ typeLabel(filterType) }}
        <button type="button" class="chip-remove" @click="clearType">×</button>
      </span>
      <span v-if="filterTheme" class="chip">
        主题: {{ filterTheme }}
        <button type="button" class="chip-remove" @click="clearTheme">×</button>
      </span>
      <BaseButton variant="ghost" size="sm" @click="clearAllFilters">
        清除全部
      </BaseButton>
    </div>

    <!-- Results count -->
    <div v-if="!loading && cases.length > 0" class="results-count">
      共 {{ total }} 条结果
    </div>

    <!-- Loading -->
    <EmptyState
      v-if="loading"
      variant="loading"
      title="加载中…"
      message="请稍候"
    />

    <!-- Error -->
    <EmptyState
      v-else-if="error"
      variant="error"
      :title="error"
      message="加载案例失败，请稍后重试"
    >
      <template #action>
        <BaseButton variant="secondary" size="md" @click="loadCases">
          重试
        </BaseButton>
      </template>
    </EmptyState>

    <!-- Empty -->
    <EmptyState
      v-else-if="cases.length === 0"
      variant="empty"
      title="暂无案例"
      message="当前条件下没有找到公开案例"
    />

    <!-- Case grid -->
    <div v-else class="case-grid">
      <BaseCard
        v-for="c in cases"
        :key="c.id"
        class="case-card"
        hoverable
        padding="md"
        :data-case-id="c.id"
      >
        <div class="case-card-main" @click="openDetail(c.id)">
          <div class="case-card-top">
            <BaseBadge variant="brand" class="case-type">
              {{ typeLabel(c.type) }}
            </BaseBadge>
            <BaseBadge v-if="c.theme" variant="secondary" class="case-theme">
              {{ c.theme }}
            </BaseBadge>
          </div>
          <h3 class="case-title">{{ c.title }}</h3>
          <div class="case-meta-row">
            <span v-if="c.author" class="meta-item">作者: {{ c.author }}</span>
            <span v-if="c.department" class="meta-item">部门: {{ c.department }}</span>
            <span class="meta-item">日期: {{ formatDate(c.created_at) }}</span>
          </div>
          <p class="case-preview">{{ preview(c.content) }}</p>
          <div class="case-stats-row">
            <span>浏览 {{ c.view_count || 0 }}</span>
            <span>点赞 {{ c.like_count || 0 }}</span>
          </div>
        </div>
        <div class="case-card-actions">
          <BaseButton
            type="button"
            :class="['btn-like', { liked: isLiked(c.id) }]"
            variant="ghost"
            size="sm"
            @click.stop="toggleLike(c.id)"
          >
            {{ isLiked(c.id) ? '已点赞' : '点赞' }}
          </BaseButton>
          <BaseButton
            type="button"
            class="btn-view"
            variant="ghost"
            size="sm"
            @click.stop="openDetail(c.id)"
          >
            查看详情
          </BaseButton>
        </div>
      </BaseCard>
    </div>

    <!-- Detail Modal -->
    <BaseModal
      :model-value="detailCase !== null"
      :title="detailCase?.title"
      @update:model-value="closeDetail"
    >
      <template #body>
        <div class="detail-badges">
          <BaseBadge variant="brand" class="badge-type">
            {{ typeLabel(detailCase.type) }}
          </BaseBadge>
          <BaseBadge v-if="detailCase.theme" variant="secondary" class="badge-theme">
            {{ detailCase.theme }}
          </BaseBadge>
          <BaseBadge variant="success" shape="pill" class="badge-status">
            已通过
          </BaseBadge>
        </div>
        <div class="detail-meta">
          <span v-if="detailCase.author">作者: {{ detailCase.author }}</span>
          <span v-if="detailCase.department">部门: {{ detailCase.department }}</span>
          <span>日期: {{ formatDate(detailCase.created_at) }}</span>
          <span>浏览 {{ detailCase.view_count || 0 }}</span>
          <span>点赞 {{ detailLikeCount }}</span>
        </div>
        <div class="detail-content">
          <div class="detail-content-body">{{ detailCase.content || '暂无内容' }}</div>
        </div>
        <div v-if="detailCase.source_material" class="detail-source">
          <strong>来源材料：</strong>
          <div class="detail-source-body">{{ detailCase.source_material }}</div>
        </div>
        <div v-if="detailCase.keywords && detailCase.keywords.length" class="detail-keywords">
          <strong>关键词：</strong>
          <BaseBadge
            v-for="k in detailCase.keywords"
            :key="k"
            variant="brand"
            class="keyword-tag"
          >
            {{ k }}
          </BaseBadge>
        </div>
      </template>
      <template #footer>
        <BaseButton
          type="button"
          :class="['btn-like-lg', { liked: isLiked(detailCase.id) }]"
          variant="secondary"
          size="md"
          @click="toggleLike(detailCase.id)"
        >
          {{ isLiked(detailCase.id) ? '已点赞' : '点赞' }}
        </BaseButton>
        <BaseButton variant="secondary" size="md" @click="closeDetail">
          关闭
        </BaseButton>
      </template>
    </BaseModal>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue';
import {
  fetchCaseConstants,
  listPublicCases,
  searchPublicCases,
  fetchPublicCaseDetail,
  likeCase,
  unlikeCase,
} from '../api/cases.js';
import { notify } from '../utils/toast.js';
import BaseButton from '../components/ui/BaseButton.vue';
import BaseInput from '../components/ui/BaseInput.vue';
import BaseSelect from '../components/ui/BaseSelect.vue';
import BaseCard from '../components/ui/BaseCard.vue';
import BaseBadge from '../components/ui/BaseBadge.vue';
import BaseModal from '../components/ui/BaseModal.vue';
import EmptyState from '../components/ui/EmptyState.vue';

const props = defineProps({
  searchTrigger: { type: Object, default: () => ({ keyword: '', nonce: 0 }) },
});

const cases = ref([]);
const total = ref(0);
const loading = ref(false);
const error = ref('');

const searchInput = ref('');
const appliedKeyword = ref('');
const filterType = ref('');
const filterTheme = ref('');

const caseTypes = ref({
  TYPE_A: '思政课教学案例',
  TYPE_B: '课程思政共享资源案例',
  TYPE_C: '实践育人案例',
});
const themes = ref(['强国建设', '实践育人', '数字赋能', '铸魂育人']);

const detailCase = ref(null);
const detailLikeCount = ref(0);

const likedCases = ref(new Set());
const likeProcessing = ref(new Set());

const hasActiveFilters = computed(() => {
  return Boolean(appliedKeyword.value || filterType.value || filterTheme.value);
});

const typeOptions = computed(() =>
  Object.entries(caseTypes.value).map(([value, label]) => ({ value, label }))
);

// Track last handled search trigger nonce to avoid re-applying stale keywords
let lastHandledNonce = 0;

function applyExternalSearch() {
  const t = props.searchTrigger;
  if (!t || t.nonce <= lastHandledNonce) return false;
  lastHandledNonce = t.nonce;

  // Clear type/theme filters for global header search to avoid confusing stale filters
  filterType.value = '';
  filterTheme.value = '';

  if (t.keyword) {
    searchInput.value = t.keyword;
    appliedKeyword.value = t.keyword;
  } else {
    searchInput.value = '';
    appliedKeyword.value = '';
  }

  loadCases();
  return true;
}

watch(() => props.searchTrigger, applyExternalSearch, { deep: true });

function typeLabel(type) {
  return caseTypes.value[type] || type || '未知类型';
}

function formatDate(value) {
  if (!value) return '';
  const d = new Date(value);
  if (isNaN(d.getTime())) return String(value);
  return d.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function preview(content) {
  const text = (content || '').replace(/\s+/g, ' ').trim();
  if (text.length <= 150) return text;
  return text.slice(0, 150) + '…';
}

function loadLikedState() {
  try {
    const raw = localStorage.getItem('likedCases');
    const arr = raw ? JSON.parse(raw) : [];
    likedCases.value = new Set(arr.map(String));
  } catch {
    likedCases.value = new Set();
  }
}

function saveLikedState() {
  localStorage.setItem('likedCases', JSON.stringify(Array.from(likedCases.value)));
}

function isLiked(caseId) {
  return likedCases.value.has(String(caseId));
}

async function toggleLike(caseId) {
  if (likeProcessing.value.has(caseId)) return;
  likeProcessing.value.add(caseId);

  const idStr = String(caseId);
  const currentlyLiked = likedCases.value.has(idStr);

  try {
    if (currentlyLiked) {
      await unlikeCase(caseId);
      likedCases.value.delete(idStr);
      // Update list counts
      const c = cases.value.find(x => x.id === caseId);
      if (c) c.like_count = Math.max(0, (c.like_count || 0) - 1);
      // Update detail count
      if (detailCase.value && detailCase.value.id === caseId) {
        detailLikeCount.value = Math.max(0, detailLikeCount.value - 1);
      }
    } else {
      await likeCase(caseId);
      likedCases.value.add(idStr);
      const c = cases.value.find(x => x.id === caseId);
      if (c) c.like_count = (c.like_count || 0) + 1;
      if (detailCase.value && detailCase.value.id === caseId) {
        detailLikeCount.value += 1;
      }
    }
    saveLikedState();
  } catch (err) {
    notify(err.message || '操作失败，请稍后重试', 'error');
  } finally {
    likeProcessing.value.delete(caseId);
  }
}

async function loadCases() {
  loading.value = true;
  error.value = '';

  try {
    let res;
    if (hasActiveFilters.value) {
      res = await searchPublicCases({
        keyword: appliedKeyword.value || undefined,
        type: filterType.value || undefined,
        theme: filterTheme.value || undefined,
      });
    } else {
      res = await listPublicCases();
    }

    if (res?.success) {
      cases.value = res.data || [];
      total.value = res.total ?? res.data?.length ?? 0;
    } else {
      throw new Error(res?.message || '加载失败');
    }
  } catch (err) {
    error.value = err.message || '加载案例失败，请稍后重试';
    cases.value = [];
    total.value = 0;
  } finally {
    loading.value = false;
  }
}

function applySearch() {
  appliedKeyword.value = searchInput.value.trim();
  loadCases();
}

function applyFilters() {
  loadCases();
}

function clearSearch() {
  searchInput.value = '';
  appliedKeyword.value = '';
  loadCases();
}

function clearType() {
  filterType.value = '';
  loadCases();
}

function clearTheme() {
  filterTheme.value = '';
  loadCases();
}

function clearAllFilters() {
  searchInput.value = '';
  appliedKeyword.value = '';
  filterType.value = '';
  filterTheme.value = '';
  loadCases();
}

async function openDetail(caseId) {
  try {
    const res = await fetchPublicCaseDetail(caseId);
    if (res?.success && res.data) {
      detailCase.value = res.data;
      detailLikeCount.value = res.data.like_count || 0;
      // Also update the view count in the list
      const c = cases.value.find(x => x.id === caseId);
      if (c) c.view_count = res.data.view_count || 0;
    } else {
      throw new Error(res?.message || '加载详情失败');
    }
  } catch (err) {
    notify(err.message || '加载案例详情失败', 'error');
  }
}

function closeDetail() {
  detailCase.value = null;
}

onMounted(async () => {
  loadLikedState();
  const wasHandled = applyExternalSearch();
  if (!wasHandled) {
    await loadCases();
  }
  try {
    const data = await fetchCaseConstants();
    if (data) {
      if (data.case_types) caseTypes.value = data.case_types;
      if (Array.isArray(data.themes)) themes.value = data.themes;
    }
  } catch {
    // Safe fallbacks already set
  }
});
</script>

<style scoped>
.case-library {
  max-width: var(--max-content-width);
  margin: 0 auto;
  padding: 32px 24px 48px;
}

.library-header {
  margin-bottom: 24px;
}

.page-title {
  margin: 0 0 8px;
  font-size: 24px;
  font-weight: 700;
  color: var(--color-text);
}

.page-desc {
  margin: 0;
  font-size: 14px;
  color: var(--color-text-secondary);
}

/* Filter bar */
.filter-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 16px;
  align-items: center;
}

.search-box {
  display: flex;
  flex: 1 1 320px;
  min-width: 240px;
  max-width: 520px;
  align-items: stretch;
}

.search-box :deep(.base-input) {
  flex: 1;
}

.search-box :deep(.input-wrap) {
  border-radius: 6px 0 0 6px;
}

.search-box :deep(.input-suffix) {
  padding: 0;
  border: 0;
}

.search-box :deep(.base-button) {
  height: 100%;
  border-radius: 0 6px 6px 0;
  border: 1px solid var(--color-brand);
}

.filter-selects {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

.filter-selects :deep(.base-select) {
  flex: 1;
  min-width: 140px;
}

/* Filter chips */
.filter-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 12px;
  align-items: center;
}

.chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  background: var(--color-brand-light);
  color: var(--color-brand);
  font-size: 13px;
  font-weight: 500;
  border-radius: 4px;
}

.chip-remove {
  background: transparent;
  border: 0;
  color: var(--color-brand);
  font-size: 16px;
  line-height: 1;
  cursor: pointer;
  padding: 0 2px;
}

/* Results count */
.results-count {
  margin-bottom: 12px;
  font-size: 13px;
  color: var(--color-text-muted);
}

/* Case grid */
.case-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 16px;
}

.case-card-main {
  padding: 18px 20px;
  cursor: pointer;
  flex: 1;
}

.case-card-top {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
  flex-wrap: wrap;
}

.case-title {
  margin: 0 0 10px;
  font-size: 17px;
  font-weight: 700;
  color: var(--color-text);
  line-height: 1.4;
}

.case-meta-row {
  display: flex;
  flex-wrap: wrap;
  gap: 10px 16px;
  margin-bottom: 10px;
}

.meta-item {
  font-size: 13px;
  color: var(--color-text-secondary);
}

.case-preview {
  margin: 0 0 10px;
  font-size: 14px;
  color: var(--color-text-secondary);
  line-height: 1.6;
  word-break: break-word;
}

.case-stats-row {
  display: flex;
  gap: 14px;
  font-size: 13px;
  color: var(--color-text-muted);
}

/* Card actions */
.case-card-actions {
  display: flex;
  gap: 0;
  border-top: 1px solid var(--color-border);
}

.case-card .case-card-actions :deep(.base-button) {
  flex: 1;
  border-radius: 0;
  border: 0;
  border-right: 1px solid var(--color-border);
  background: transparent;
  color: var(--color-text-secondary);
}

.case-card .case-card-actions :deep(.base-button):last-child {
  border-right: 0;
}

.case-card .case-card-actions :deep(.base-button):hover {
  background: var(--color-brand-light);
  color: var(--color-brand);
}

.case-card .case-card-actions :deep(.base-button).liked {
  background: var(--color-brand-light);
  color: var(--color-brand);
}

/* Detail modal content */
.detail-badges {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 14px;
}

.detail-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 10px 16px;
  margin-bottom: 18px;
  font-size: 13px;
  color: var(--color-text-secondary);
}

.detail-content {
  margin-bottom: 16px;
}

.detail-content-body {
  font-size: 15px;
  line-height: 1.8;
  color: var(--color-text);
  white-space: pre-wrap;
  word-break: break-word;
}

.detail-source {
  margin: 0 0 16px;
  padding: 12px 14px;
  border: 1px solid rgba(141, 27, 53, 0.16);
  border-radius: 8px;
  background: rgba(141, 27, 53, 0.04);
  font-size: 13px;
  color: var(--color-text-secondary);
}

.detail-source strong {
  display: block;
  margin-bottom: 6px;
  color: var(--color-text);
}

.detail-source-body {
  white-space: pre-wrap;
  word-break: break-word;
  line-height: 1.7;
}

.detail-keywords {
  font-size: 13px;
  margin-bottom: 8px;
}

.detail-keywords strong {
  color: var(--color-text);
}

.keyword-tag {
  display: inline-block;
  margin: 2px 4px 2px 0;
}

.btn-like-lg {
  padding-left: 18px;
  padding-right: 18px;
}

.btn-like-lg:hover {
  background: var(--color-brand-light);
  border-color: var(--color-brand);
  color: var(--color-brand);
}

.btn-like-lg.liked {
  background: var(--color-brand-light);
  border-color: var(--color-brand);
  color: var(--color-brand);
}

/* Responsive */
@media (min-width: 640px) {
  .page-title {
    font-size: 28px;
  }

  .case-grid {
    grid-template-columns: repeat(2, 1fr);
    gap: 20px;
  }
}

@media (min-width: 1024px) {
  .case-grid {
    grid-template-columns: repeat(3, 1fr);
    gap: 20px;
  }
}

@media (max-width: 720px) {
  .case-library {
    padding: 20px 12px 32px;
  }

  .filter-bar {
    flex-direction: column;
    align-items: stretch;
  }

  .search-box {
    flex: none;
    max-width: none;
    width: 100%;
  }

  .filter-selects {
    width: 100%;
  }

  .filter-selects :deep(.base-select) {
    min-width: 0;
  }

  .case-card-main {
    padding: 14px 14px;
  }

  .case-title {
    font-size: 15px;
  }

  .case-meta-row {
    gap: 6px 10px;
  }

  .meta-item {
    font-size: 12px;
  }
}

@media (max-width: 390px) {
  .case-card-top {
    flex-direction: column;
    align-items: flex-start;
  }

  .case-card .case-card-actions :deep(.base-button) {
    padding: 8px 10px;
    font-size: 12px;
  }
}
</style>
