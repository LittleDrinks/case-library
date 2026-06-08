<template>
  <div class="admin-review">
    <div class="review-header">
      <h1 class="page-title">审核管理</h1>
      <p class="page-desc">管理员专用：审核待处理的案例提交，管理案例公开状态。</p>
    </div>

    <!-- Login required -->
    <div v-if="!isAuthenticated" class="login-required-card">
      <div class="login-required-icon" aria-hidden="true">🔒</div>
      <h3>请先登录</h3>
      <p>审核管理功能需要管理员身份，请先登录。</p>
    </div>

    <!-- Permission denied -->
    <div v-else-if="!isAdminUser" class="permission-denied-card">
      <div class="permission-icon" aria-hidden="true">🚫</div>
      <h3>权限不足</h3>
      <p>审核管理功能仅限管理员使用。</p>
    </div>

    <template v-else>
      <!-- Tabs -->
      <div class="tabs-bar" role="tablist" aria-label="审核状态">
        <button
          v-for="tab in tabs"
          :key="tab.key"
          :class="['tab-btn', { active: currentTab === tab.key }]"
          role="tab"
          :aria-selected="currentTab === tab.key"
          @click="switchTab(tab.key)"
        >
          {{ tab.label }}
        </button>
      </div>

      <!-- Loading -->
      <div v-if="loading" class="state-loading">
        <div class="spinner" aria-hidden="true"></div>
        <p>加载中…</p>
      </div>

      <!-- Error -->
      <div v-else-if="error" class="state-error">
        <div class="error-icon" aria-hidden="true">⚠️</div>
        <p>{{ error }}</p>
        <button type="button" class="btn-secondary" @click="loadCases">重试</button>
      </div>

      <!-- Empty -->
      <div v-else-if="cases.length === 0" class="state-empty">
        <div class="empty-icon" aria-hidden="true">📋</div>
        <h3>暂无{{ currentTabLabel }}</h3>
        <p>当前分类下没有案例</p>
      </div>

      <!-- Case list -->
      <div v-else class="case-list">
        <div
          v-for="c in cases"
          :key="c.id"
          class="case-card"
          :data-case-id="c.id"
        >
          <div class="case-card-main" @click="toggleDetail(c.id)">
            <div class="case-card-top">
              <div class="case-type">{{ typeLabel(c.type) }}</div>
              <div class="case-badges">
                <span :class="['status-pill', statusPillClass(c.status)]">{{ statusLabel(c.status) }}</span>
                <span v-if="c.status === 'approved'" :class="['status-pill', c.is_hidden ? 'pill-hidden' : 'pill-visible']">
                  {{ c.is_hidden ? '已隐藏' : '未隐藏' }}
                </span>
              </div>
            </div>
            <h3 class="case-title">{{ c.title }}</h3>
            <div class="case-meta-row">
              <span class="meta-item" v-if="c.author">👤 {{ c.author }}</span>
              <span class="meta-item" v-if="c.owner_username">🏛 {{ c.owner_username }}</span>
              <span class="meta-item" v-if="c.department">🏢 {{ c.department }}</span>
              <span class="meta-item" v-if="c.theme">🏷 {{ c.theme }}</span>
              <span class="meta-item">📅 {{ formatDate(c.created_at) }}</span>
              <span class="meta-item" v-if="c.updated_at && c.updated_at !== c.created_at">🔄 {{ formatDate(c.updated_at) }}</span>
            </div>
            <p class="case-preview">{{ preview(c.content) }}</p>
            <div class="case-stats-row">
              <span>👁 {{ c.view_count || 0 }}</span>
              <span>❤️ {{ c.like_count || 0 }}</span>
            </div>
          </div>

          <!-- Inline detail -->
          <div v-if="expandedId === c.id" class="case-detail">
            <div class="detail-grid">
              <div class="detail-item"><strong>提交账号：</strong>{{ c.owner_username || '未知' }}</div>
              <div class="detail-item"><strong>作者：</strong>{{ c.author || '未知' }}</div>
              <div class="detail-item"><strong>部门：</strong>{{ c.department || '未知' }}</div>
              <div class="detail-item"><strong>类型：</strong>{{ typeLabel(c.type) }}</div>
              <div class="detail-item"><strong>主题：</strong>{{ c.theme || '未设置' }}</div>
            </div>
            <div class="detail-content-full">
              <strong>内容：</strong>
              <div class="detail-content-body">{{ c.content || '暂无内容' }}</div>
            </div>
            <div v-if="c.keywords && c.keywords.length" class="detail-keywords">
              <strong>关键词：</strong>
              <span v-for="k in c.keywords" :key="k" class="keyword-tag">{{ k }}</span>
            </div>

            <div v-if="c.ai_reviews && c.ai_reviews.length" class="detail-ai-reviews">
              <strong>作者 AI 自查意见：</strong>
              <div class="ai-review-list">
                <div v-for="item in c.ai_reviews" :key="item.prompt_id" class="ai-review-item">
                  <div class="ai-review-head">
                    <span class="ai-review-name">{{ item.name || item.prompt_id }}</span>
                    <span v-if="item.reviewed_at" class="ai-review-time">{{ formatDate(item.reviewed_at) }}</span>
                  </div>
                  <div v-if="item.parsed && item.parsed.detail" class="ai-review-detail">
                    {{ item.parsed.detail }}
                  </div>
                  <div v-if="item.parsed && item.parsed.score != null" class="ai-review-score">
                    评分 {{ item.parsed.score }}
                  </div>
                  <ul
                    v-if="item.parsed && Array.isArray(item.parsed.suggestions) && item.parsed.suggestions.length"
                    class="ai-review-suggestions"
                  >
                    <li v-for="suggestion in item.parsed.suggestions" :key="suggestion">
                      {{ suggestion }}
                    </li>
                  </ul>
                  <pre v-if="!item.parsed" class="ai-review-answer">{{ item.answer }}</pre>
                  <div v-if="item.parse_error" class="ai-review-warning">
                    {{ item.parse_error }}
                  </div>
                </div>
              </div>
            </div>

            <!-- Review info -->
            <div v-if="showReviewFor(c.status)" class="detail-review">
              <strong>审核信息：</strong>
              <div v-if="reviewLoading[c.id]" class="review-placeholder">加载中…</div>
              <div v-else-if="reviewMap[c.id]" class="review-body">
                <div><strong>审核人：</strong>{{ reviewMap[c.id].reviewer }}</div>
                <div><strong>审核结果：</strong>{{ reviewMap[c.id].result }}</div>
                <div><strong>审核意见：</strong>{{ reviewMap[c.id].comment }}</div>
                <div v-if="reviewMap[c.id].reviewAt"><strong>审核时间：</strong>{{ reviewMap[c.id].reviewAt }}</div>
              </div>
              <div v-else class="review-placeholder">暂无审核信息</div>
            </div>

            <div class="detail-actions">
              <button type="button" class="btn-secondary btn-sm" @click="toggleDetail(c.id)">收起详情</button>
            </div>
          </div>

          <!-- Card actions -->
          <div class="case-actions">
            <button type="button" class="btn-secondary btn-sm" @click.stop="toggleDetail(c.id)">
              {{ expandedId === c.id ? '收起' : '查看详情' }}
            </button>
            <template v-if="c.status === 'pending_review'">
              <button type="button" class="btn-primary btn-sm" @click.stop="openReviewModal(c)">审核</button>
            </template>
            <template v-if="c.status === 'approved'">
              <button
                type="button"
                :class="['btn-sm', c.is_hidden ? 'btn-primary' : 'btn-warning']"
                @click.stop="toggleVisibility(c)"
              >
                {{ c.is_hidden ? '展示' : '隐藏' }}
              </button>
            </template>
            <button type="button" class="btn-danger btn-sm" @click.stop="confirmDelete(c)">删除</button>
          </div>
        </div>
      </div>
    </template>

    <!-- Review Modal -->
    <div v-if="reviewingCase" class="modal-overlay" @click.self="closeReviewModal">
      <div class="modal-panel" role="dialog" aria-modal="true" aria-labelledby="review-title">
        <div class="modal-header">
          <h3 id="review-title">审核案例：{{ reviewingCase.title }}</h3>
          <button type="button" class="modal-close" aria-label="关闭" @click="closeReviewModal">×</button>
        </div>
        <div class="modal-body">
          <div class="field">
            <label for="review-comment">审核意见 <span class="required">*</span></label>
            <textarea
              id="review-comment"
              v-model="reviewForm.comment"
              rows="5"
              placeholder="请输入审核意见"
            ></textarea>
          </div>
          <div class="field">
            <label>审核结果 <span class="required">*</span></label>
            <div class="radio-group">
              <label class="radio-label">
                <input type="radio" v-model="reviewForm.status" value="approve" />
                <span>通过</span>
              </label>
              <label class="radio-label">
                <input type="radio" v-model="reviewForm.status" value="reject" />
                <span>需修改</span>
              </label>
            </div>
          </div>
        </div>
        <div class="modal-footer">
          <button type="button" class="btn-secondary" @click="closeReviewModal">取消</button>
          <button type="button" class="btn-primary" :disabled="reviewing" @click="submitReview">
            {{ reviewing ? '提交中…' : '提交审核' }}
          </button>
        </div>
      </div>
    </div>

    <!-- Delete confirmation modal -->
    <div v-if="deletingCase" class="modal-overlay" @click.self="deletingCase = null">
      <div class="modal-panel confirm-panel" role="dialog" aria-modal="true">
        <div class="modal-header">
          <h3>确认删除</h3>
          <button type="button" class="modal-close" aria-label="关闭" @click="deletingCase = null">×</button>
        </div>
        <div class="modal-body">
          <p>确定要删除案例「{{ deletingCase.title }}」吗？此操作不可撤销。</p>
        </div>
        <div class="modal-footer">
          <button type="button" class="btn-secondary" @click="deletingCase = null">取消</button>
          <button type="button" class="btn-danger" :disabled="deleting" @click="doDelete">
            {{ deleting ? '删除中…' : '删除' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue';
import { isLoggedIn, isAdmin, currentUser } from '../api/auth.js';
import {
  fetchCaseConstants,
  listReviewCases,
  fetchCaseReviews,
  reviewCase,
  setCaseVisibility,
  deleteCaseById,
} from '../api/cases.js';

const tabs = [
  { key: 'pending', label: '待审核', apiStatus: 'pending_review' },
  { key: 'approved', label: '已通过', apiStatus: 'approved_all' },
  { key: 'rejected', label: '需修改', apiStatus: 'rejected' },
  { key: 'all', label: '全部案例', apiStatus: 'all' },
];

const currentTab = ref('pending');
const cases = ref([]);
const loading = ref(false);
const error = ref('');
const expandedId = ref(null);
const reviewMap = ref({});
const reviewLoading = ref({});

const caseTypes = ref({
  TYPE_A: '思政课教学案例',
  TYPE_B: '课程思政共享资源案例',
  TYPE_C: '实践育人案例',
});

const reviewingCase = ref(null);
const reviewForm = ref({ comment: '', status: 'approve' });
const reviewing = ref(false);

const deletingCase = ref(null);
const deleting = ref(false);

const isAuthenticated = computed(() => isLoggedIn());
const isAdminUser = computed(() => isAdmin());
const currentTabLabel = computed(() => tabs.find(t => t.key === currentTab.value)?.label || '');
const currentTabApiStatus = computed(() => tabs.find(t => t.key === currentTab.value)?.apiStatus || 'pending_review');

function switchTab(tab) {
  currentTab.value = tab;
  expandedId.value = null;
  loadCases();
}

function statusLabel(status) {
  const map = {
    draft: '草稿',
    pending_review: '待审核',
    approved: '已通过',
    needs_revision: '需修改',
  };
  return map[status] || status;
}

function typeLabel(type) {
  return caseTypes.value[type] || type;
}

function statusPillClass(status) {
  const map = {
    draft: 'pill-draft',
    pending_review: 'pill-pending',
    approved: 'pill-approved',
    needs_revision: 'pill-revision',
  };
  return map[status] || '';
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
  if (text.length <= 120) return text;
  return text.slice(0, 120) + '…';
}

function showReviewFor(status) {
  return status === 'approved' || status === 'needs_revision';
}

async function loadCases() {
  if (!isAuthenticated.value || !isAdminUser.value) return;

  loading.value = true;
  error.value = '';
  try {
    const res = await listReviewCases(currentTabApiStatus.value);
    if (res?.success) {
      cases.value = res.data || [];
    } else {
      throw new Error(res?.message || '加载失败');
    }
  } catch (err) {
    error.value = err.message || '加载案例失败，请稍后重试';
    cases.value = [];
  } finally {
    loading.value = false;
  }
}

function toggleDetail(caseId) {
  if (expandedId.value === caseId) {
    expandedId.value = null;
    return;
  }
  expandedId.value = caseId;
  const c = cases.value.find(x => x.id === caseId);
  if (c && showReviewFor(c.status)) {
    loadReview(caseId);
  }
}

async function loadReview(caseId) {
  if (reviewMap.value[caseId] !== undefined) return;
  reviewLoading.value[caseId] = true;
  try {
    const res = await fetchCaseReviews(caseId);
    if (res?.success && Array.isArray(res.data)) {
      const decisive = res.data.find(r => r.status === 'approved' || r.status === 'rejected');
      if (decisive) {
        reviewMap.value[caseId] = {
          reviewer: decisive.reviewer || '未知',
          result: decisive.status === 'approved' ? '通过' : '驳回',
          comment: decisive.comment || '（无意见）',
          reviewAt: formatDate(decisive.review_at),
        };
      } else {
        reviewMap.value[caseId] = null;
      }
    } else {
      reviewMap.value[caseId] = null;
    }
  } catch {
    reviewMap.value[caseId] = null;
  } finally {
    reviewLoading.value[caseId] = false;
  }
}

function openReviewModal(c) {
  reviewingCase.value = c;
  reviewForm.value = { comment: '', status: 'approve' };
}

function closeReviewModal() {
  reviewingCase.value = null;
  reviewing.value = false;
}

async function submitReview() {
  if (!reviewingCase.value) return;
  if (!reviewForm.value.comment.trim()) {
    window.alert('请填写审核意见');
    return;
  }
  reviewing.value = true;
  try {
    await reviewCase(reviewingCase.value.id, {
      comment: reviewForm.value.comment.trim(),
      status: reviewForm.value.status,
    });
    window.alert('审核完成');
    closeReviewModal();
    await loadCases();
  } catch (err) {
    window.alert(err.message || '审核提交失败');
  } finally {
    reviewing.value = false;
  }
}

async function toggleVisibility(c) {
  try {
    await setCaseVisibility(c.id, !c.is_hidden);
    window.alert(c.is_hidden ? '案例已展示' : '案例已隐藏');
    await loadCases();
  } catch (err) {
    window.alert(err.message || '操作失败');
  }
}

function confirmDelete(c) {
  deletingCase.value = c;
}

async function doDelete() {
  if (!deletingCase.value) return;
  deleting.value = true;
  try {
    await deleteCaseById(deletingCase.value.id);
    window.alert('案例删除成功');
    deletingCase.value = null;
    await loadCases();
  } catch (err) {
    window.alert(err.message || '删除失败');
  } finally {
    deleting.value = false;
  }
}

onMounted(async () => {
  if (isAuthenticated.value && isAdminUser.value) {
    await loadCases();
  }
  try {
    const data = await fetchCaseConstants();
    if (data) {
      if (data.case_types) caseTypes.value = data.case_types;
    }
  } catch {
    // Safe fallbacks already set
  }
});

watch(currentTab, () => {
  reviewMap.value = {};
  reviewLoading.value = {};
});
</script>

<style scoped>
.admin-review {
  max-width: var(--max-content-width);
  margin: 0 auto;
  padding: 32px 24px 48px;
}

.review-header {
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

/* Tabs */
.tabs-bar {
  display: flex;
  gap: 4px;
  margin-bottom: 20px;
  border-bottom: 1px solid var(--color-border);
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
  scrollbar-width: none;
}

.tabs-bar::-webkit-scrollbar {
  display: none;
}

.tab-btn {
  position: relative;
  padding: 10px 16px;
  border: 0;
  border-radius: 6px 6px 0 0;
  background: transparent;
  color: var(--color-text-secondary);
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  white-space: nowrap;
  transition: color 0.15s, background 0.15s;
}

.tab-btn:hover {
  color: var(--color-text);
  background: rgba(29, 35, 47, 0.04);
}

.tab-btn.active {
  color: var(--color-brand);
  font-weight: 600;
  background: var(--color-brand-light);
}

.tab-btn.active::after {
  content: '';
  position: absolute;
  bottom: -1px;
  left: 8px;
  right: 8px;
  height: 2px;
  border-radius: 1px;
  background: var(--color-brand);
}

/* States */
.state-loading,
.state-error,
.state-empty,
.login-required-card,
.permission-denied-card {
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
.state-empty p,
.login-required-card p,
.permission-denied-card p {
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

.error-icon,
.empty-icon,
.login-required-icon,
.permission-icon {
  font-size: 40px;
  line-height: 1;
}

.state-empty h3,
.login-required-card h3,
.permission-denied-card h3 {
  margin: 0;
  font-size: 18px;
  font-weight: 700;
  color: var(--color-text);
}

/* Case list */
.case-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.case-card {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 8px;
  overflow: hidden;
}

.case-card-main {
  padding: 18px 20px;
  cursor: pointer;
  transition: background 0.1s;
}

.case-card-main:hover {
  background: rgba(141, 27, 53, 0.02);
}

.case-card-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
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

.case-badges {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.status-pill {
  font-size: 12px;
  font-weight: 700;
  padding: 3px 10px;
  border-radius: 999px;
}

.pill-draft {
  background: #f3f4f6;
  color: var(--color-text-secondary);
}

.pill-pending {
  background: #fef3c7;
  color: #92400e;
}

.pill-approved {
  background: #dcfce7;
  color: #166534;
}

.pill-revision {
  background: #fee2e2;
  color: #991b1b;
}

.pill-hidden {
  background: #f3f4f6;
  color: var(--color-text-secondary);
}

.pill-visible {
  background: #e0f2fe;
  color: #0c4a6e;
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

/* Detail */
.case-detail {
  padding: 0 20px 18px;
  border-top: 1px solid var(--color-border);
  background: #fafafa;
}

.detail-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 8px;
  padding: 14px 0;
}

.detail-item {
  font-size: 13px;
  color: var(--color-text-secondary);
}

.detail-item strong {
  color: var(--color-text);
}

.detail-content-full {
  font-size: 13px;
  color: var(--color-text-secondary);
  margin-bottom: 10px;
}

.detail-content-full strong {
  color: var(--color-text);
}

.detail-content-body {
  margin-top: 6px;
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
}

.detail-keywords {
  font-size: 13px;
  margin-bottom: 10px;
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

.detail-ai-reviews {
  font-size: 13px;
  margin: 12px 0;
  color: var(--color-text-secondary);
}

.detail-ai-reviews > strong {
  color: var(--color-text);
}

.ai-review-list {
  display: grid;
  grid-template-columns: 1fr;
  gap: 10px;
  margin-top: 8px;
}

.ai-review-item {
  padding: 12px;
  border: 1px solid var(--color-border);
  border-radius: 6px;
  background: var(--color-surface);
}

.ai-review-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 8px;
}

.ai-review-name {
  font-weight: 700;
  color: var(--color-text);
}

.ai-review-time {
  flex-shrink: 0;
  color: var(--color-text-muted);
  font-size: 12px;
}

.ai-review-detail {
  color: var(--color-text);
  line-height: 1.6;
  margin-bottom: 6px;
}

.ai-review-score {
  display: inline-flex;
  padding: 3px 8px;
  border-radius: 999px;
  background: var(--color-brand-light);
  color: var(--color-brand);
  font-size: 12px;
  font-weight: 700;
  margin-bottom: 6px;
}

.ai-review-suggestions {
  margin: 0;
  padding-left: 18px;
  line-height: 1.6;
}

.ai-review-answer {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  margin: 0;
  font: inherit;
  line-height: 1.6;
}

.ai-review-warning {
  margin-top: 6px;
  color: #92400e;
  font-size: 12px;
}

.detail-review {
  font-size: 13px;
  margin-bottom: 10px;
  padding: 12px;
  background: var(--color-error-bg);
  border-radius: 6px;
}

.detail-review strong {
  color: var(--color-text);
}

.review-placeholder {
  margin-top: 6px;
  color: var(--color-text-muted);
}

.review-body {
  margin-top: 6px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  color: var(--color-text-secondary);
  line-height: 1.5;
}

.detail-actions {
  display: flex;
  justify-content: flex-end;
  padding-top: 10px;
}

/* Card actions */
.case-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding: 10px 20px;
  border-top: 1px solid var(--color-border);
  background: var(--color-surface);
}

/* Buttons */
.btn-primary,
.btn-secondary,
.btn-danger,
.btn-warning {
  padding: 8px 14px;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: opacity 0.15s;
  border: 0;
  white-space: nowrap;
}

.btn-primary {
  background: var(--color-brand);
  color: #fff;
}

.btn-secondary {
  background: var(--color-surface);
  color: var(--color-text-secondary);
  border: 1px solid var(--color-border-strong);
}

.btn-danger {
  background: var(--color-error-bg);
  color: var(--color-error-text);
  border: 1px solid #fecaca;
}

.btn-warning {
  background: #fef3c7;
  color: #92400e;
  border: 1px solid #fde68a;
}

.btn-primary:disabled,
.btn-secondary:disabled,
.btn-danger:disabled,
.btn-warning:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-sm {
  padding: 6px 12px;
  font-size: 12px;
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
  max-width: 640px;
  max-height: calc(100vh - 32px);
  background: var(--color-surface);
  border-radius: 10px;
  box-shadow: 0 20px 50px rgba(0, 0, 0, 0.12);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.confirm-panel {
  max-width: 420px;
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid var(--color-border);
}

.modal-header h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 700;
  color: var(--color-text);
}

.modal-close {
  background: transparent;
  border: 0;
  font-size: 22px;
  line-height: 1;
  color: var(--color-text-muted);
  cursor: pointer;
}

.modal-body {
  padding: 20px;
  overflow-y: auto;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  padding: 14px 20px;
  border-top: 1px solid var(--color-border);
}

/* Form fields in modal */
.field {
  margin-bottom: 16px;
}

.field label {
  display: block;
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text);
  margin-bottom: 6px;
}

.required {
  color: var(--color-brand);
  margin-left: 2px;
}

.radio-group {
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
}

.radio-label {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  color: var(--color-text);
  cursor: pointer;
}

.radio-label input[type="radio"] {
  width: 18px;
  height: 18px;
  accent-color: var(--color-brand);
  cursor: pointer;
}

input[type="text"],
select,
textarea {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid var(--color-border-strong);
  border-radius: 4px;
  font-family: inherit;
  font-size: 14px;
  color: var(--color-text);
  background: var(--color-surface);
  outline: none;
  transition: border-color 0.15s, box-shadow 0.15s;
}

input[type="text"]:focus,
select:focus,
textarea:focus {
  border-color: var(--color-brand);
  box-shadow: 0 0 0 3px var(--color-brand-light);
}

textarea {
  min-height: 120px;
  resize: vertical;
  line-height: 1.6;
}

/* Responsive */
@media (min-width: 640px) {
  .page-title {
    font-size: 28px;
  }

  .detail-grid {
    grid-template-columns: 1fr 1fr;
    gap: 10px 16px;
  }

  .case-actions {
    gap: 10px;
  }
}

@media (max-width: 480px) {
  .admin-review {
    padding: 20px 12px 32px;
  }

  .tab-btn {
    padding: 8px 10px;
    font-size: 13px;
  }

  .case-card-main {
    padding: 14px 14px;
  }

  .case-detail,
  .case-actions {
    padding-left: 14px;
    padding-right: 14px;
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
    flex-wrap: wrap;
  }
}

@media (max-width: 390px) {
  .case-card-top {
    flex-direction: column;
    align-items: flex-start;
  }

  .case-badges {
    width: 100%;
  }

  .case-actions {
    gap: 6px;
  }

  .btn-primary,
  .btn-secondary,
  .btn-danger,
  .btn-warning {
    padding: 6px 10px;
    font-size: 12px;
  }
}
</style>
