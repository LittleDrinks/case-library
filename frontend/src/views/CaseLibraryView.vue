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
        <input
          v-model="searchInput"
          type="text"
          placeholder="搜索案例标题、内容..."
          @keydown.enter="applySearch"
        />
        <button type="button" class="btn-search" @click="applySearch">
          搜索
        </button>
      </div>
      <div class="filter-selects">
        <select v-model="filterType" @change="applyFilters">
          <option value="">全部类型</option>
          <option v-for="(label, key) in caseTypes" :key="key" :value="key">
            {{ label }}
          </option>
        </select>
        <select v-model="filterTheme" @change="applyFilters">
          <option value="">全部主题</option>
          <option v-for="t in themes" :key="t" :value="t">
            {{ t }}
          </option>
        </select>
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
      <button type="button" class="chip-clear" @click="clearAllFilters">
        清除全部
      </button>
    </div>

    <!-- Results count -->
    <div v-if="!loading && cases.length > 0" class="results-count">
      共 {{ total }} 条结果
    </div>

    <!-- Loading -->
    <div v-if="loading" class="state-loading">
      <div class="spinner" aria-hidden="true"></div>
      <p>加载中…</p>
    </div>

    <!-- Error -->
    <div v-else-if="error" class="state-error">
      <p>{{ error }}</p>
      <button type="button" class="btn-secondary" @click="loadCases">重试</button>
    </div>

    <!-- Empty -->
    <div v-else-if="cases.length === 0" class="state-empty">
      <h3>暂无案例</h3>
      <p>当前条件下没有找到公开案例</p>
    </div>

    <!-- Case grid -->
    <div v-else class="case-grid">
      <div
        v-for="c in cases"
        :key="c.id"
        class="case-card"
        :data-case-id="c.id"
      >
        <div class="case-card-main" @click="openDetail(c.id)">
          <div class="case-card-top">
            <div class="case-type">{{ typeLabel(c.type) }}</div>
            <div v-if="c.theme" class="case-theme">{{ c.theme }}</div>
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
          <button
            type="button"
            :class="['btn-like', { liked: isLiked(c.id) }]"
            @click.stop="toggleLike(c.id)"
          >
            {{ isLiked(c.id) ? '已点赞' : '点赞' }}
          </button>
          <button type="button" class="btn-view" @click.stop="openDetail(c.id)">
            查看详情
          </button>
        </div>
      </div>
    </div>

    <!-- Detail Modal -->
    <div v-if="detailCase" class="modal-overlay" @click.self="closeDetail">
      <div class="modal-panel" role="dialog" aria-modal="true" aria-labelledby="detail-title">
        <div class="modal-header">
          <h3 id="detail-title">{{ detailCase.title }}</h3>
          <button type="button" class="modal-close" aria-label="关闭" @click="closeDetail">
            ×
          </button>
        </div>
        <div class="modal-body">
          <div class="detail-badges">
            <span class="badge-type">{{ typeLabel(detailCase.type) }}</span>
            <span v-if="detailCase.theme" class="badge-theme">{{ detailCase.theme }}</span>
            <span class="badge-status">已通过</span>
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
          <div v-if="detailCase.keywords && detailCase.keywords.length" class="detail-keywords">
            <strong>关键词：</strong>
            <span v-for="k in detailCase.keywords" :key="k" class="keyword-tag">{{ k }}</span>
          </div>
        </div>
        <div class="modal-footer">
          <button
            type="button"
            :class="['btn-like-lg', { liked: isLiked(detailCase.id) }]"
            @click="toggleLike(detailCase.id)"
          >
            {{ isLiked(detailCase.id) ? '已点赞' : '点赞' }}
          </button>
          <button type="button" class="btn-secondary" @click="closeDetail">关闭</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue';
import {
  fetchCaseConstants,
  listPublicCases,
  searchPublicCases,
  fetchPublicCaseDetail,
  likeCase,
  unlikeCase,
} from '../api/cases.js';

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
    window.alert(err.message || '操作失败，请稍后重试');
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
    window.alert(err.message || '加载案例详情失败');
  }
}

function closeDetail() {
  detailCase.value = null;
}

onMounted(async () => {
  loadLikedState();
  await loadCases();
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
}

.search-box input {
  flex: 1;
  padding: 10px 14px;
  border: 1px solid var(--color-border-strong);
  border-right: 0;
  border-radius: 6px 0 0 6px;
  font-family: inherit;
  font-size: 14px;
  color: var(--color-text);
  background: var(--color-surface);
  outline: none;
  transition: border-color 0.15s, box-shadow 0.15s;
}

.search-box input:focus {
  border-color: var(--color-brand);
  box-shadow: 0 0 0 3px var(--color-brand-light);
}

.btn-search {
  padding: 0 16px;
  border: 1px solid var(--color-brand);
  border-radius: 0 6px 6px 0;
  background: var(--color-brand);
  color: #fff;
  font-size: 14px;
  cursor: pointer;
  transition: background 0.15s;
}

.btn-search:hover {
  background: var(--color-brand-dark);
}

.filter-selects {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

.filter-selects select {
  padding: 10px 28px 10px 12px;
  border: 1px solid var(--color-border-strong);
  border-radius: 6px;
  font-family: inherit;
  font-size: 14px;
  color: var(--color-text);
  background: var(--color-surface);
  outline: none;
  appearance: none;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'%3E%3Cpath fill='%234b5565' d='M6 8L1 3h10z'/%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: right 10px center;
  transition: border-color 0.15s, box-shadow 0.15s;
  min-width: 140px;
}

.filter-selects select:focus {
  border-color: var(--color-brand);
  box-shadow: 0 0 0 3px var(--color-brand-light);
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

.chip-clear {
  background: transparent;
  border: 0;
  color: var(--color-text-secondary);
  font-size: 13px;
  cursor: pointer;
  text-decoration: underline;
  padding: 4px 6px;
}

.chip-clear:hover {
  color: var(--color-text);
}

/* Results count */
.results-count {
  margin-bottom: 12px;
  font-size: 13px;
  color: var(--color-text-muted);
}

/* States */
.state-loading,
.state-error,
.state-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 56px 24px;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 8px;
  text-align: center;
}

.state-loading p,
.state-error p,
.state-empty p {
  margin: 0;
  font-size: 14px;
  color: var(--color-text-secondary);
}

.spinner {
  width: 32px;
  height: 32px;
  border: 3px solid var(--color-border);
  border-top-color: var(--color-brand);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.state-empty h3 {
  margin: 0;
  font-size: 18px;
  font-weight: 700;
  color: var(--color-text);
}

/* Case grid */
.case-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 16px;
}

.case-card {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 8px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  transition: box-shadow 0.15s;
}

.case-card:hover {
  box-shadow: 0 4px 16px rgba(29, 35, 47, 0.08);
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

.case-type {
  font-size: 12px;
  font-weight: 600;
  color: var(--color-brand);
  background: var(--color-brand-light);
  padding: 3px 10px;
  border-radius: 4px;
}

.case-theme {
  font-size: 12px;
  font-weight: 500;
  color: var(--color-text-secondary);
  background: #f3f4f6;
  padding: 3px 10px;
  border-radius: 4px;
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

.btn-like,
.btn-view {
  flex: 1;
  padding: 10px 14px;
  border: 0;
  background: var(--color-surface);
  font-family: inherit;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
  text-align: center;
}

.btn-like {
  color: var(--color-text-secondary);
  border-right: 1px solid var(--color-border);
}

.btn-like:hover {
  background: var(--color-brand-light);
  color: var(--color-brand);
}

.btn-like.liked {
  color: var(--color-brand);
  background: var(--color-brand-light);
}

.btn-view {
  color: var(--color-brand);
}

.btn-view:hover {
  background: var(--color-brand-light);
}

/* Modal */
.modal-overlay {
  position: fixed;
  inset: 0;
  z-index: 200;
  background: rgba(0, 0, 0, 0.35);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 16px;
}

.modal-panel {
  width: 100%;
  max-width: 720px;
  max-height: calc(100vh - 32px);
  background: var(--color-surface);
  border-radius: 10px;
  box-shadow: 0 20px 50px rgba(0, 0, 0, 0.12);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid var(--color-border);
  flex-shrink: 0;
}

.modal-header h3 {
  margin: 0;
  font-size: 18px;
  font-weight: 700;
  color: var(--color-text);
  line-height: 1.4;
  padding-right: 16px;
}

.modal-close {
  background: transparent;
  border: 0;
  font-size: 22px;
  line-height: 1;
  color: var(--color-text-muted);
  cursor: pointer;
  flex-shrink: 0;
}

.modal-body {
  padding: 20px;
  overflow-y: auto;
  flex: 1;
}

.detail-badges {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 14px;
}

.badge-type {
  font-size: 12px;
  font-weight: 600;
  color: var(--color-brand);
  background: var(--color-brand-light);
  padding: 3px 10px;
  border-radius: 4px;
}

.badge-theme {
  font-size: 12px;
  font-weight: 500;
  color: var(--color-text-secondary);
  background: #f3f4f6;
  padding: 3px 10px;
  border-radius: 4px;
}

.badge-status {
  font-size: 12px;
  font-weight: 700;
  color: #166534;
  background: #dcfce7;
  padding: 3px 10px;
  border-radius: 999px;
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

.detail-keywords {
  font-size: 13px;
  margin-bottom: 8px;
}

.detail-keywords strong {
  color: var(--color-text);
}

.keyword-tag {
  display: inline-block;
  padding: 2px 8px;
  margin: 2px 4px 2px 0;
  background: var(--color-brand-light);
  color: var(--color-brand);
  font-size: 12px;
  border-radius: 4px;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  padding: 14px 20px;
  border-top: 1px solid var(--color-border);
  flex-shrink: 0;
  flex-wrap: wrap;
}

.btn-like-lg {
  padding: 8px 18px;
  border-radius: 6px;
  border: 1px solid var(--color-border-strong);
  background: var(--color-surface);
  color: var(--color-text-secondary);
  font-family: inherit;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.15s, color 0.15s, border-color 0.15s;
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

.btn-secondary {
  padding: 8px 18px;
  border-radius: 6px;
  border: 1px solid var(--color-border-strong);
  background: var(--color-surface);
  color: var(--color-text-secondary);
  font-family: inherit;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.15s;
}

.btn-secondary:hover {
  background: rgba(29, 35, 47, 0.04);
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

  .filter-selects select {
    flex: 1;
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

  .modal-body {
    padding: 14px;
  }

  .modal-footer {
    padding: 10px 14px;
  }

  .modal-header h3 {
    font-size: 16px;
  }
}

@media (max-width: 390px) {
  .case-card-top {
    flex-direction: column;
    align-items: flex-start;
  }

  .btn-like,
  .btn-view {
    padding: 8px 10px;
    font-size: 12px;
  }
}
</style>
