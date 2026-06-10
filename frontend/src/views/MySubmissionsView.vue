<template>
  <div class="my-submissions">
    <div class="submissions-header">
      <h1 class="page-title">我的提交</h1>
      <p class="page-desc">查看和管理您提交的案例，包括待审核、已通过、需修改和草稿状态。</p>
    </div>

    <!-- Login required -->
    <div v-if="!isAuthenticated" class="login-required-card">
      <div class="login-required-icon" aria-hidden="true">锁</div>
      <h3>请先登录</h3>
      <p>查看和管理您的案例需要先登录账号。</p>
    </div>

    <template v-else>
      <!-- Tabs -->
      <div class="tabs-bar" role="tablist" aria-label="案例状态">
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
        <div class="error-icon" aria-hidden="true">警</div>
        <p>{{ error }}</p>
        <button type="button" class="btn-secondary" @click="loadCases">重试</button>
      </div>

      <!-- Empty -->
      <div v-else-if="cases.length === 0" class="state-empty">
        <div class="empty-icon" aria-hidden="true">空</div>
        <h3>暂无{{ currentTabLabel }}</h3>
        <p>当前分类下没有案例</p>
        <button type="button" class="btn-primary" @click="goToCreate">创建新案例</button>
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
              <span :class="['status-pill', statusPillClass(c.status)]">{{ statusLabel(c.status) }}</span>
            </div>
            <h3 class="case-title">{{ c.title }}</h3>
            <div class="case-meta-row">
              <span class="meta-item" v-if="c.department">学院 {{ c.department }}</span>
              <span class="meta-item" v-if="c.theme">主题 {{ c.theme }}</span>
              <span class="meta-item">创建 {{ formatDate(c.created_at) }}</span>
              <span class="meta-item" v-if="c.updated_at && c.updated_at !== c.created_at">更新 {{ formatDate(c.updated_at) }}</span>
            </div>
            <p class="case-preview">{{ preview(c.content) }}</p>
            <div class="case-stats-row">
              <span>浏览 {{ c.view_count || 0 }}</span>
              <span>点赞 {{ c.like_count || 0 }}</span>
            </div>
          </div>

          <!-- Inline detail -->
          <div v-if="expandedId === c.id" class="case-detail">
            <div class="detail-grid">
              <div class="detail-item"><strong>作者：</strong>{{ c.author || '未知' }}</div>
              <div class="detail-item"><strong>部门：</strong>{{ c.department || '未知' }}</div>
              <div class="detail-item"><strong>类型：</strong>{{ typeLabel(c.type) }}</div>
              <div class="detail-item"><strong>主题：</strong>{{ c.theme || '未设置' }}</div>
            </div>
            <div class="detail-content-full">
              <strong>内容：</strong>
              <div class="detail-content-body">{{ c.content || '暂无内容' }}</div>
            </div>
            <div class="detail-content-full" v-if="c.source_material">
              <strong>来源材料：</strong>
              <div class="detail-content-body">{{ c.source_material }}</div>
            </div>
            <div v-if="c.keywords && c.keywords.length" class="detail-keywords">
              <strong>关键词：</strong>
              <span v-for="k in c.keywords" :key="k" class="keyword-tag">{{ k }}</span>
            </div>

            <div class="version-history">
              <div class="section-head">
                <strong>历史版本</strong>
                <span v-if="versionMap[c.id]?.length" class="section-count">{{ versionMap[c.id].length }} 个版本</span>
              </div>
              <div v-if="versionLoading[c.id]" class="review-placeholder">加载中…</div>
              <div v-else-if="versionError[c.id]" class="review-placeholder">{{ versionError[c.id] }}</div>
              <div v-else-if="versionMap[c.id]?.length" class="version-list">
                <article v-for="version in versionMap[c.id]" :key="version.id" class="version-item">
                  <div class="version-head">
                    <div>
                      <strong>v{{ version.version_number }}</strong>
                      <span v-if="version.change_reason" class="version-reason">{{ version.change_reason }}</span>
                    </div>
                    <button type="button" class="btn-secondary btn-sm" @click="copyVersion(version)">复制版本</button>
                  </div>
                  <div class="version-meta">
                    <span>创建 {{ formatDate(version.created_at) }}</span>
                    <span v-if="version.created_by">创建人 {{ version.created_by }}</span>
                  </div>
                  <div class="version-body">
                    <div class="version-field">
                      <span>正文</span>
                      <p>{{ version.content || '暂无内容' }}</p>
                    </div>
                    <div class="version-field">
                      <span>来源材料</span>
                      <p>{{ version.source_material || '暂无来源材料' }}</p>
                    </div>
                  </div>
                </article>
              </div>
              <div v-else class="review-placeholder">暂无历史版本</div>
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
            <template v-if="isEditable(c.status)">
              <button type="button" class="btn-primary btn-sm" @click.stop="openEdit(c)">修改</button>
            </template>
            <template v-if="c.status === 'draft'">
              <button type="button" class="btn-primary btn-sm" @click.stop="openEdit(c, 'submit')">提交审核</button>
            </template>
            <template v-if="c.status === 'needs_revision'">
              <button type="button" class="btn-primary btn-sm" @click.stop="openEdit(c, 'resubmit')">重新提交</button>
            </template>
            <button type="button" class="btn-danger btn-sm" @click.stop="confirmDelete(c)">删除</button>
          </div>
        </div>
      </div>
    </template>

    <!-- Edit Modal -->
    <div v-if="editingCase" class="modal-overlay" @click.self="closeEdit">
      <div class="modal-panel" role="dialog" aria-modal="true" aria-labelledby="edit-title">
        <div class="modal-header">
          <h3 id="edit-title">{{ modalTitle }}</h3>
          <button type="button" class="modal-close" aria-label="关闭" @click="closeEdit">×</button>
        </div>
        <div class="modal-body">
          <div class="field">
            <label for="ms-edit-title">案例标题 <span class="required">*</span></label>
            <input id="ms-edit-title" v-model="editForm.title" type="text" placeholder="请输入案例标题" />
          </div>
          <div class="field">
            <label for="ms-edit-dept">所属部门/学院 <span class="required">*</span></label>
            <input id="ms-edit-dept" v-model="editForm.department" type="text" placeholder="请输入所属部门或学院" />
          </div>
          <div class="field">
            <label for="ms-edit-content">案例正文 <span class="required">*</span></label>
            <textarea id="ms-edit-content" v-model="editForm.content" rows="10" placeholder="请输入案例正文"></textarea>
          </div>
          <div class="field">
            <label for="ms-edit-source">来源材料</label>
            <textarea id="ms-edit-source" v-model="editForm.source_material" rows="5" placeholder="粘贴新闻、课堂记录、调研材料等来源文本"></textarea>
          </div>
          <div class="field">
            <label for="ms-edit-type">案例类型 <span class="required">*</span></label>
            <select id="ms-edit-type" v-model="editForm.type">
              <option disabled value="">请选择案例类型</option>
              <option v-for="(label, key) in caseTypes" :key="key" :value="key">{{ label }}</option>
            </select>
          </div>
          <div class="field">
            <label for="ms-edit-theme">案例主题 <span class="required">*</span></label>
            <select id="ms-edit-theme" v-model="editForm.theme">
              <option disabled value="">请选择案例主题</option>
              <option v-for="t in themes" :key="t" :value="t">{{ t }}</option>
            </select>
          </div>
        </div>
        <div class="modal-footer">
          <button type="button" class="btn-secondary" @click="closeEdit">取消</button>
          <button type="button" class="btn-primary" :disabled="saving" @click="handleSave">
            {{ saving ? '保存中…' : '保存' }}
          </button>
          <button v-if="editAction" type="button" class="btn-primary" :disabled="saving || submitting" @click="handleResubmit">
            {{ submitting ? '提交中…' : submitButtonLabel }}
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
import { isLoggedIn, currentUser } from '../api/auth.js';
import {
  fetchCaseConstants,
  listMyCases,
  fetchCaseDetail,
  fetchCaseReviews,
  fetchCaseVersions,
  updateCase,
  submitCaseById,
  deleteCaseById,
} from '../api/cases.js';
import { notify } from '../utils/toast.js';

const tabs = [
  { key: 'pending_review', label: '待审核' },
  { key: 'approved', label: '已通过' },
  { key: 'needs_revision', label: '需修改' },
  { key: 'draft', label: '草稿' },
  { key: 'all', label: '全部' },
];

const currentTab = ref('pending_review');
const cases = ref([]);
const loading = ref(false);
const error = ref('');
const expandedId = ref(null);
const reviewMap = ref({});
const reviewLoading = ref({});
const versionMap = ref({});
const versionLoading = ref({});
const versionError = ref({});

const caseTypes = ref({
  TYPE_A: '思政课教学案例',
  TYPE_B: '课程思政共享资源案例',
  TYPE_C: '实践育人案例',
});
const themes = ref(['强国建设', '实践育人', '数字赋能', '铸魂育人']);

const editingCase = ref(null);
const editAction = ref(''); // '', 'submit', 'resubmit'
const editForm = ref({ title: '', department: '', content: '', source_material: '', type: '', theme: '' });
const saving = ref(false);
const submitting = ref(false);

const modalTitle = computed(() => {
  if (editAction.value === 'resubmit') return '重新提交案例';
  if (editAction.value === 'submit') return '提交审核';
  return '修改案例';
});

const submitButtonLabel = computed(() => {
  if (editAction.value === 'resubmit') return '重新提交';
  if (editAction.value === 'submit') return '提交审核';
  return '提交';
});

const deletingCase = ref(null);
const deleting = ref(false);

const isAuthenticated = computed(() => isLoggedIn());
const currentTabLabel = computed(() => tabs.find(t => t.key === currentTab.value)?.label || '');

function switchTab(tab) {
  currentTab.value = tab;
  expandedId.value = null;
  loadCases();
}

function goToCreate() {
  window.location.hash = 'create';
}

function isEditable(status) {
  return status === 'draft' || status === 'needs_revision';
}

function showReviewFor(status) {
  return status === 'approved' || status === 'needs_revision';
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

function sortCasesNewestFirst(list) {
  return list.sort((a, b) => {
    const ta = new Date(b.updated_at || b.submitted_at || b.created_at || 0).getTime();
    const tb = new Date(a.updated_at || a.submitted_at || a.created_at || 0).getTime();
    return ta - tb;
  });
}

async function loadCases() {
  if (!isAuthenticated.value) return;
  const user = currentUser();
  if (!user?.username) return;

  loading.value = true;
  error.value = '';
  try {
    if (currentTab.value === 'all') {
      const statuses = ['pending_review', 'approved', 'needs_revision', 'draft'];
      const results = await Promise.all(
        statuses.map(s => listMyCases(user.username, s))
      );
      const map = new Map();
      for (const res of results) {
        if (res?.success && Array.isArray(res.data)) {
          for (const c of res.data) {
            map.set(c.id, c);
          }
        }
      }
      cases.value = sortCasesNewestFirst(Array.from(map.values()));
    } else {
      const res = await listMyCases(user.username, currentTab.value);
      if (res?.success) {
        cases.value = res.data || [];
      } else {
        throw new Error(res?.message || '加载失败');
      }
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
  loadVersions(caseId);
  if (c && showReviewFor(c.status)) {
    loadReview(caseId);
  }
}

async function loadVersions(caseId) {
  if (versionMap.value[caseId] !== undefined || versionLoading.value[caseId]) return;
  versionLoading.value[caseId] = true;
  versionError.value[caseId] = '';
  try {
    const res = await fetchCaseVersions(caseId);
    if (res?.success && Array.isArray(res.data)) {
      versionMap.value[caseId] = res.data;
    } else {
      throw new Error(res?.message || '版本加载失败');
    }
  } catch (err) {
    versionMap.value[caseId] = [];
    versionError.value[caseId] = err.message || '版本加载失败';
  } finally {
    versionLoading.value[caseId] = false;
  }
}

function versionSnapshotText(version) {
  return [
    `版本：v${version.version_number || ''}`,
    `标题：${version.title || ''}`,
    `类型：${typeLabel(version.type) || ''}`,
    `主题：${version.theme || ''}`,
    `创建时间：${formatDate(version.created_at)}`,
    '',
    '正文：',
    version.content || '',
    '',
    '来源材料：',
    version.source_material || '',
  ].join('\n');
}

async function copyVersion(version) {
  const text = versionSnapshotText(version);
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
    } else {
      const textarea = document.createElement('textarea');
      textarea.value = text;
      textarea.setAttribute('readonly', '');
      textarea.style.position = 'fixed';
      textarea.style.opacity = '0';
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand('copy');
      document.body.removeChild(textarea);
    }
    notify(`v${version.version_number} 已复制`, 'success');
  } catch {
    notify('复制失败，请手动选中文本复制', 'error');
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

function openEdit(c, action = '') {
  editingCase.value = c;
  editAction.value = action;
  editForm.value = {
    title: c.title || '',
    department: c.department || '',
    content: c.content || '',
    source_material: c.source_material || '',
    type: c.type || '',
    theme: c.theme || '',
  };
}

function closeEdit() {
  editingCase.value = null;
  editAction.value = '';
  saving.value = false;
  submitting.value = false;
}

async function handleSave() {
  if (!editingCase.value) return;
  if (!editForm.value.title.trim() || !editForm.value.department.trim() || !editForm.value.content.trim()) {
    notify('请填写所有必填项', 'error');
    return;
  }
  saving.value = true;
  try {
    const actionLabel = editAction.value === 'resubmit' ? '重新提交前更新' : editAction.value === 'submit' ? '提交审核前更新' : '修改案例';
    await updateCase(editingCase.value.id, {
      title: editForm.value.title.trim(),
      content: editForm.value.content.trim(),
      source_material: editForm.value.source_material.trim(),
      author: editingCase.value.author || currentUser()?.nickname || currentUser()?.username || '',
      department: editForm.value.department.trim(),
      type: editForm.value.type,
      theme: editForm.value.theme,
      change_reason: actionLabel,
    });
    notify('保存成功', 'success');
    closeEdit();
    await loadCases();
  } catch (err) {
    notify(err.message || '保存失败', 'error');
  } finally {
    saving.value = false;
  }
}

async function handleResubmit() {
  if (!editingCase.value) return;
  if (!editForm.value.title.trim() || !editForm.value.department.trim() || !editForm.value.content.trim()) {
    notify('请填写所有必填项', 'error');
    return;
  }
  submitting.value = true;
  try {
    const actionLabel = editAction.value === 'resubmit' ? '重新提交前更新' : '提交审核前更新';
    await updateCase(editingCase.value.id, {
      title: editForm.value.title.trim(),
      content: editForm.value.content.trim(),
      source_material: editForm.value.source_material.trim(),
      author: editingCase.value.author || currentUser()?.nickname || currentUser()?.username || '',
      department: editForm.value.department.trim(),
      type: editForm.value.type,
      theme: editForm.value.theme,
      change_reason: actionLabel,
    });
    await submitCaseById(editingCase.value.id);
    const successMsg = editAction.value === 'resubmit'
      ? '案例已重新提交，请等待专家审核'
      : '案例已提交审核，请等待专家审核';
    notify(successMsg, 'success');
    closeEdit();
    await loadCases();
  } catch (err) {
    const errorMsg = editAction.value === 'resubmit' ? '重新提交失败' : '提交审核失败';
    notify(err.message || errorMsg, 'error');
  } finally {
    submitting.value = false;
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
    notify('案例删除成功', 'success');
    deletingCase.value = null;
    await loadCases();
  } catch (err) {
    notify(err.message || '删除失败', 'error');
  } finally {
    deleting.value = false;
  }
}

onMounted(async () => {
  if (isAuthenticated.value) {
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

watch(currentTab, () => {
  reviewMap.value = {};
  reviewLoading.value = {};
  versionMap.value = {};
  versionLoading.value = {};
  versionError.value = {};
});
</script>

<style scoped>
.my-submissions {
  max-width: var(--max-content-width);
  margin: 0 auto;
  padding: 32px 24px 48px;
}

.submissions-header {
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
.login-required-card {
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

.error-icon,
.empty-icon,
.login-required-icon {
  font-size: 40px;
  line-height: 1;
}

.state-empty h3,
.login-required-card h3 {
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

.detail-review {
  font-size: 13px;
  margin-bottom: 10px;
  padding: 12px;
  background: var(--color-error-bg);
  border-radius: 6px;
}

.version-history {
  margin: 14px 0;
  padding-top: 12px;
  border-top: 1px solid var(--color-border);
  font-size: 13px;
}

.section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 8px;
}

.section-head strong {
  color: var(--color-text);
}

.section-count,
.version-meta {
  color: var(--color-text-muted);
  font-size: 12px;
}

.version-list {
  display: grid;
  gap: 10px;
}

.version-item {
  padding: 12px;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 6px;
}

.version-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 10px;
  margin-bottom: 6px;
}

.version-head strong {
  color: var(--color-brand);
}

.version-reason {
  margin-left: 8px;
  color: var(--color-text-secondary);
}

.version-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 14px;
  margin-bottom: 8px;
}

.version-body {
  display: grid;
  gap: 8px;
}

.version-field span {
  display: block;
  margin-bottom: 4px;
  font-weight: 700;
  color: var(--color-text);
}

.version-field p {
  margin: 0;
  color: var(--color-text-secondary);
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
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
.btn-danger {
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

.btn-primary:disabled,
.btn-secondary:disabled,
.btn-danger:disabled {
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
  min-height: 180px;
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
  .my-submissions {
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

  .case-actions {
    gap: 6px;
  }

  .btn-primary,
  .btn-secondary,
  .btn-danger {
    padding: 6px 10px;
    font-size: 12px;
  }
}
</style>
