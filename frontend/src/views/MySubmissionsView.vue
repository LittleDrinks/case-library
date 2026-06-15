<template>
  <div class="my-submissions">
    <div class="submissions-header">
      <h1 class="page-title">我的提交</h1>
      <p class="page-desc">查看和管理您提交的案例，包括待审核、已通过、需修改和草稿状态。</p>
    </div>

    <!-- Login required -->
    <div v-if="!isAuthenticated" class="login-required-card">
      <div class="login-required-icon" aria-hidden="true"></div>
      <h3>请先登录</h3>
      <p>查看和管理您的案例需要先登录账号。</p>
    </div>

    <section v-else-if="detailCase" class="submission-detail-page">
      <div class="submission-detail-toolbar">
        <button type="button" class="btn-secondary" @click="closeSubmissionDetail">返回我的提交</button>
        <div class="submission-detail-actions">
          <button
            v-if="hasDetailReviewArtifacts"
            type="button"
            class="btn-secondary"
            @click="showDetailReviewResult = !showDetailReviewResult"
          >
            {{ showDetailReviewResult ? '隐藏审核结果' : '显示审核结果' }}
          </button>
          <button v-if="isEditable(detailCase.status)" type="button" class="btn-primary" @click="goToEdit(detailCase)">
            修改案例
          </button>
        </div>
      </div>

      <div class="submission-detail-header">
        <div>
          <div class="case-type">{{ typeLabel(detailCase.type) }}</div>
          <h2>{{ detailCase.title }}</h2>
          <div class="case-meta-row">
            <span class="meta-item" v-if="detailCase.department">学院 {{ detailCase.department }}</span>
            <span class="meta-item" v-if="detailCase.theme">主题 {{ detailCase.theme }}</span>
            <span class="meta-item">创建 {{ formatDate(detailCase.created_at) }}</span>
            <span class="meta-item" v-if="detailCase.updated_at && detailCase.updated_at !== detailCase.created_at">更新 {{ formatDate(detailCase.updated_at) }}</span>
          </div>
        </div>
        <span :class="['status-pill', statusPillClass(detailCase.status)]">{{ statusLabel(detailCase.status) }}</span>
      </div>

      <div class="submission-detail-grid">
        <main class="submission-detail-main">
          <section class="submission-detail-card">
            <div class="section-head">
              <strong>案例正文</strong>
              <span v-if="showDetailReviewResult && detailReviewVersion" class="section-count">
                审核版本 v{{ detailReviewVersion.version_number }}
              </span>
            </div>
            <div v-if="showDetailReviewResult && detailParagraphs.length" class="submission-paragraph-list">
              <article
                v-for="paragraph in detailParagraphs"
                :key="paragraph.paragraph_id"
                class="submission-paragraph"
              >
                <span>{{ paragraph.paragraph_id }}</span>
                <div class="submission-paragraph-text" v-html="renderMarkdown(paragraph.text)"></div>
                <div
                  v-for="comment in detailAiCommentsForParagraph(paragraph.paragraph_id)"
                  :key="comment.id || `ai-${comment.paragraph_id}-${comment.message}`"
                  class="submission-ai-inline"
                >
                  <strong>AI 意见</strong>
                  <p>{{ comment.message }}</p>
                  <small v-if="comment.suggestion">建议：{{ comment.suggestion }}</small>
                  <small v-if="comment.severity || comment.category">
                    {{ comment.category || '内容建议' }} · {{ comment.severity || '提示' }}
                  </small>
                </div>
                <div
                  v-for="comment in detailAdminCommentsForParagraph(paragraph.paragraph_id)"
                  :key="`admin-${comment.paragraph_id}-${comment.created_at}-${comment.message}`"
                  class="submission-admin-inline"
                >
                  <strong>人工段落批注</strong>
                  <p>{{ comment.message }}</p>
                  <small v-if="comment.suggestion">建议：{{ comment.suggestion }}</small>
                  <small>
                    {{ comment.reviewer || '审核员' }}
                    <template v-if="comment.created_at"> · {{ formatDate(comment.created_at) }}</template>
                  </small>
                </div>
              </article>
            </div>
            <div v-else class="detail-markdown" v-html="renderMarkdown(detailCase.content || '暂无内容')"></div>
          </section>
          <section v-if="detailCase.source_material" class="submission-detail-card">
            <div class="section-head">
              <strong>来源材料</strong>
            </div>
            <div class="detail-markdown" v-html="renderMarkdown(detailCase.source_material)"></div>
          </section>
        </main>

        <aside class="submission-detail-side">
          <section class="submission-detail-card">
            <div class="section-head">
              <strong>历史版本</strong>
              <span v-if="detailVersions.length" class="section-count">{{ detailVersions.length }} 个版本</span>
            </div>
            <div v-if="versionLoading[detailCase.id]" class="review-placeholder">加载中…</div>
            <div v-else-if="versionError[detailCase.id]" class="review-placeholder">{{ versionError[detailCase.id] }}</div>
            <div v-else-if="detailVersions.length" class="version-list">
              <article v-for="version in detailVersions" :key="version.id" class="version-item">
                <div class="version-head">
                  <div>
                    <strong>v{{ version.version_number }}</strong>
                    <span v-if="version.change_reason" class="version-reason">{{ version.change_reason }}</span>
                  </div>
                  <button type="button" class="btn-secondary btn-sm" @click="copyVersion(version)">复制</button>
                </div>
                <div class="version-meta">
                  <span>创建 {{ formatDate(version.created_at) }}</span>
                </div>
              </article>
            </div>
            <div v-else class="review-placeholder">暂无历史版本</div>
          </section>

          <section v-if="showReviewFor(detailCase.status)" class="submission-detail-card">
            <div class="section-head">
              <strong>审核信息</strong>
            </div>
            <div v-if="reviewLoading[detailCase.id]" class="review-placeholder">加载中…</div>
            <div v-else-if="reviewMap[detailCase.id]" class="review-body">
              <div><strong>审核人：</strong>{{ reviewMap[detailCase.id].reviewer }}</div>
              <div><strong>审核结果：</strong>{{ reviewMap[detailCase.id].result }}</div>
              <div><strong>审核意见：</strong>{{ reviewMap[detailCase.id].comment }}</div>
              <div v-if="reviewMap[detailCase.id].reviewAt"><strong>审核时间：</strong>{{ reviewMap[detailCase.id].reviewAt }}</div>
            </div>
            <div v-else class="review-placeholder">暂无审核信息</div>
          </section>
        </aside>
      </div>
    </section>

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

      <div class="submissions-toolbar">
        <div>
          <strong>{{ currentTabLabel }}</strong>
          <span>{{ tabDescription }}</span>
        </div>
        <button
          type="button"
          class="btn-primary"
          @click="goToCreate"
        >
          新建案例
        </button>
      </div>

      <!-- Loading -->
      <div v-if="loading" class="state-loading">
        <div class="spinner" aria-hidden="true"></div>
        <p>加载中…</p>
      </div>

      <!-- Error -->
      <div v-else-if="error" class="state-error">
        <div class="error-icon" aria-hidden="true"></div>
        <p>{{ error }}</p>
        <button type="button" class="btn-secondary" @click="loadCases">重试</button>
      </div>

      <!-- Empty -->
      <div v-else-if="cases.length === 0" class="state-empty">
        <div class="empty-icon" aria-hidden="true"></div>
        <h3>暂无{{ currentTabLabel }}</h3>
        <p>{{ emptyDescription }}</p>
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
                  <div v-if="version.admin_comments?.length" class="version-admin-comments">
                    <strong>人工段落批注</strong>
                    <div
                      v-for="batch in version.admin_comments"
                      :key="`${batch.created_at}-${batch.reviewer}`"
                      class="version-comment-batch"
                    >
                      <div class="version-comment-meta">
                        <span>{{ batch.reviewer || '审核员' }}</span>
                        <span>{{ formatDate(batch.created_at) }}</span>
                      </div>
                      <p v-if="batch.comment" class="version-review-comment">{{ batch.comment }}</p>
                      <ul>
                        <li
                          v-for="comment in batch.comments"
                          :key="`${comment.paragraph_id}-${comment.message}`"
                        >
                          <span>{{ comment.paragraph_id }}</span>
                          <p>
                            {{ comment.message }}
                            <em v-if="comment.suggestion">{{ comment.suggestion }}</em>
                          </p>
                        </li>
                      </ul>
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
              查看详情
            </button>
            <template v-if="isEditable(c.status)">
              <button type="button" class="btn-primary btn-sm" @click.stop="goToEdit(c)">修改</button>
            </template>
            <template v-if="c.status === 'draft'">
              <button type="button" class="btn-primary btn-sm" @click.stop="goToEdit(c)">提交审核</button>
            </template>
            <template v-if="c.status === 'needs_revision'">
              <button type="button" class="btn-primary btn-sm" @click.stop="goToEdit(c)">重新提交</button>
            </template>
            <button type="button" class="btn-danger btn-sm" @click.stop="confirmDelete(c)">删除</button>
          </div>
        </div>
      </div>
    </template>

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
import { ref, computed, onMounted, onBeforeUnmount, watch } from 'vue';
import { isLoggedIn, currentUser } from '../api/auth.js';
import {
  fetchCaseConstants,
  listMyCases,
  fetchCaseDetail,
  fetchCaseReviews,
  fetchCaseVersions,
  deleteCaseById,
} from '../api/cases.js';
import { notify } from '../utils/toast.js';

const tabs = [
  { key: 'all', label: '全部' },
  { key: 'draft', label: '草稿' },
  { key: 'pending_review', label: '待审核' },
  { key: 'needs_revision', label: '需修改' },
  { key: 'approved', label: '已通过' },
];

const currentTab = ref('all');
const cases = ref([]);
const loading = ref(false);
const error = ref('');
const expandedId = ref(null);
const reviewMap = ref({});
const reviewLoading = ref({});
const versionMap = ref({});
const versionLoading = ref({});
const versionError = ref({});
const detailCase = ref(null);
const showDetailReviewResult = ref(false);
let lastOpenedHashCaseId = '';

const caseTypes = ref({
  TYPE_A: '思政课教学案例',
  TYPE_B: '课程思政共享资源案例',
  TYPE_C: '实践育人案例',
});
const themes = ref(['强国建设', '实践育人', '数字赋能', '铸魂育人']);

const deletingCase = ref(null);
const deleting = ref(false);

const isAuthenticated = computed(() => isLoggedIn());
const currentTabLabel = computed(() => tabs.find(t => t.key === currentTab.value)?.label || '');
const tabDescription = computed(() => {
  const map = {
    all: '集中查看全部案例状态，支持继续编辑草稿、处理退回修改和查看审核进度。',
    draft: '尚未提交审核的案例，可继续编辑或提交审核。',
    pending_review: '已提交但仍在等待专家审核的案例。',
    needs_revision: '专家退回后需要修改并重新提交的案例。',
    approved: '已通过审核并可进入案例库展示的案例。',
  };
  return map[currentTab.value] || '查看和管理您的案例。';
});
const emptyDescription = computed(() => {
  const map = {
    all: '当前还没有案例，可以从新建案例开始。',
    draft: '当前没有草稿，可以从新建案例开始。',
    pending_review: '当前没有等待审核的案例。',
    needs_revision: '当前没有需要修改的案例。',
    approved: '当前没有已通过的案例。',
  };
  return map[currentTab.value] || '当前分类下没有案例。';
});
const detailVersions = computed(() => {
  if (!detailCase.value) return [];
  return versionMap.value[detailCase.value.id] || [];
});
const detailReviewVersion = computed(() => {
  if (!detailCase.value || !detailVersions.value.length) return null;
  const targetId = detailCase.value.submitted_version_id || detailCase.value.reviewed_version_id;
  const target = detailVersions.value.find(version => Number(version.id) === Number(targetId));
  if (target) return target;
  const withAdminComments = detailVersions.value.find(version => Array.isArray(version.admin_comments) && version.admin_comments.length);
  if (withAdminComments) return withAdminComments;
  const withAiComments = detailVersions.value.find(version => Array.isArray(version.ai_review?.comments) && version.ai_review.comments.length);
  if (withAiComments) return withAiComments;
  return detailVersions.value[0];
});
const detailParagraphs = computed(() => {
  if (Array.isArray(detailReviewVersion.value?.paragraphs) && detailReviewVersion.value.paragraphs.length) {
    return detailReviewVersion.value.paragraphs;
  }
  const content = detailReviewVersion.value?.content || detailCase.value?.content || '';
  return splitContentToParagraphs(content);
});
const detailAiComments = computed(() => {
  const caseComments = (detailCase.value?.ai_reviews || []).flatMap(item => {
    if (Array.isArray(item.comments)) return item.comments;
    if (Array.isArray(item.version?.ai_review?.comments)) return item.version.ai_review.comments;
    return [];
  });
  if (caseComments.length) return caseComments;
  return detailReviewVersion.value?.ai_review?.comments || [];
});
const detailAdminComments = computed(() => {
  const versions = detailReviewVersion.value ? [detailReviewVersion.value] : detailVersions.value;
  return versions.flatMap(version => {
    return (version.admin_comments || []).flatMap(batch => {
      return (batch.comments || []).map(comment => ({
        ...comment,
        reviewer: batch.reviewer,
        created_at: batch.created_at,
      }));
    });
  });
});
const hasDetailReviewArtifacts = computed(() => {
  return detailAiComments.value.length > 0 || detailAdminComments.value.length > 0;
});

function switchTab(tab) {
  currentTab.value = tab;
  expandedId.value = null;
  loadCases();
}

function goToCreate() {
  window.location.hash = 'create';
}

function goToEdit(c) {
  window.location.hash = `create?draft=${encodeURIComponent(c.id)}`;
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
  openSubmissionDetail(caseId);
}

function openSubmissionDetail(caseId) {
  const targetHash = `submissions?case=${encodeURIComponent(caseId)}`;
  const currentHash = window.location.hash.replace('#', '');
  if (currentHash !== targetHash) {
    window.location.hash = targetHash;
    return;
  }
  loadSubmissionDetail(caseId);
}

async function loadSubmissionDetail(caseId) {
  try {
    showDetailReviewResult.value = false;
    const res = await fetchCaseDetail(caseId, false);
    if (!res?.success || !res.data) {
      throw new Error(res?.message || '加载案例详情失败');
    }
    detailCase.value = res.data;
    await loadVersions(caseId);
    if (showReviewFor(res.data.status)) await loadReview(caseId);
  } catch (err) {
    notify(err.message || '加载案例详情失败', 'error');
  }
}

function closeSubmissionDetail() {
  detailCase.value = null;
  showDetailReviewResult.value = false;
  lastOpenedHashCaseId = '';
  if (window.location.hash.replace('#', '').startsWith('submissions?case=')) {
    window.location.hash = 'submissions';
  }
}

function readDetailFromHash() {
  const hash = window.location.hash.replace('#', '');
  const [viewId, query = ''] = hash.split('?');
  if (viewId !== 'submissions') return;
  const caseId = new URLSearchParams(query).get('case') || '';
  if (!caseId) {
    detailCase.value = null;
    lastOpenedHashCaseId = '';
    return;
  }
  if (caseId === lastOpenedHashCaseId && detailCase.value) return;
  lastOpenedHashCaseId = caseId;
  loadSubmissionDetail(caseId);
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
          result: decisive.status === 'approved' ? '通过' : '需修改',
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

function escapeHtml(value) {
  return String(value || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function renderInlineMarkdown(value) {
  return escapeHtml(value)
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/`([^`]+)`/g, '<code>$1</code>');
}

function renderMarkdown(value) {
  const lines = String(value || '').split(/\r?\n/);
  return lines.map((line) => {
    const trimmed = line.trim();
    if (!trimmed) return '<br>';
    const heading = trimmed.match(/^(#{1,4})\s+(.+)$/);
    if (heading) {
      const level = Math.min(4, heading[1].length + 2);
      return `<h${level}>${renderInlineMarkdown(heading[2])}</h${level}>`;
    }
    const listItem = trimmed.match(/^[-*]\s+(.+)$/);
    if (listItem) {
      return `<p class="md-list-item">${renderInlineMarkdown(listItem[1])}</p>`;
    }
    const quote = trimmed.match(/^>\s*(.+)$/);
    if (quote) {
      return `<blockquote>${renderInlineMarkdown(quote[1])}</blockquote>`;
    }
    return `<p>${renderInlineMarkdown(line)}</p>`;
  }).join('');
}

function splitContentToParagraphs(content) {
  const chunks = String(content || '')
    .split(/\n{2,}/)
    .map(text => text.trim())
    .filter(Boolean);
  if (!chunks.length) return [];
  return chunks.map((text, index) => ({
    paragraph_id: `p${index + 1}`,
    text,
  }));
}

function detailAiCommentsForParagraph(paragraphId) {
  return detailAiComments.value.filter(comment => comment.paragraph_id === paragraphId);
}

function detailAdminCommentsForParagraph(paragraphId) {
  return detailAdminComments.value.filter(comment => comment.paragraph_id === paragraphId);
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
  readDetailFromHash();
  window.addEventListener('hashchange', readDetailFromHash);
});

onBeforeUnmount(() => {
  window.removeEventListener('hashchange', readDetailFromHash);
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

.submissions-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin: -4px 0 20px;
  padding: 14px 16px;
  border: 1px solid var(--color-border);
  border-radius: 8px;
  background: #fafafa;
}

.submissions-toolbar strong,
.submissions-toolbar span {
  display: block;
}

.submissions-toolbar strong {
  margin-bottom: 2px;
  font-size: 14px;
  color: var(--color-text);
}

.submissions-toolbar span {
  font-size: 12px;
  color: var(--color-text-secondary);
}

.submission-detail-page {
  display: grid;
  gap: 18px;
}

.submission-detail-toolbar,
.submission-detail-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.submission-detail-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  flex-wrap: wrap;
}

.submission-detail-header {
  padding: 20px;
  border: 1px solid var(--color-border);
  border-radius: 8px;
  background: var(--color-surface);
}

.submission-detail-header h2 {
  margin: 10px 0;
  font-size: 22px;
  line-height: 1.35;
  color: var(--color-text);
}

.submission-detail-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(320px, 420px);
  gap: 20px;
  align-items: start;
}

.submission-detail-main,
.submission-detail-side {
  min-width: 0;
}

.submission-detail-side {
  position: sticky;
  top: calc(var(--header-height) + 20px);
  display: grid;
  gap: 14px;
}

.submission-detail-card {
  padding: 18px;
  border: 1px solid var(--color-border);
  border-radius: 8px;
  background: var(--color-surface);
}

.submission-detail-card + .submission-detail-card {
  margin-top: 14px;
}

.detail-markdown {
  color: var(--color-text);
  font-size: 15px;
  line-height: 1.85;
}

.detail-markdown :deep(p),
.detail-markdown :deep(h3),
.detail-markdown :deep(h4),
.detail-markdown :deep(h5),
.detail-markdown :deep(h6) {
  margin: 0;
  word-break: break-word;
}

.detail-markdown :deep(p + p),
.detail-markdown :deep(h3 + p),
.detail-markdown :deep(p + h3) {
  margin-top: 10px;
}

.detail-markdown :deep(h3),
.detail-markdown :deep(h4),
.detail-markdown :deep(h5),
.detail-markdown :deep(h6) {
  font-size: 16px;
  font-weight: 800;
}

.detail-markdown :deep(.md-list-item)::before {
  content: '- ';
  color: var(--color-brand);
  font-weight: 700;
}

.detail-markdown :deep(blockquote) {
  margin: 8px 0;
  padding: 8px 12px;
  border-left: 3px solid var(--color-brand);
  background: #fafafa;
  color: var(--color-text-secondary);
}

.detail-markdown :deep(code) {
  padding: 1px 4px;
  border-radius: 4px;
  background: #f3f4f6;
  font-family: inherit;
  font-size: 0.95em;
}

.submission-paragraph-list {
  display: grid;
  gap: 10px;
}

.submission-paragraph {
  display: grid;
  grid-template-columns: 44px minmax(0, 1fr);
  gap: 10px;
  padding: 14px;
  border: 1px solid var(--color-border);
  border-radius: 8px;
  background: #fff;
}

.submission-paragraph > span {
  display: inline-flex;
  align-items: flex-start;
  justify-content: center;
  color: var(--color-brand);
  font-weight: 800;
}

.submission-paragraph-text {
  min-width: 0;
}

.submission-paragraph-text :deep(p),
.submission-paragraph-text :deep(h3),
.submission-paragraph-text :deep(h4),
.submission-paragraph-text :deep(h5),
.submission-paragraph-text :deep(h6) {
  margin: 0;
  color: var(--color-text);
  line-height: 1.8;
  word-break: break-word;
}

.submission-paragraph-text :deep(p + p),
.submission-paragraph-text :deep(p + h3),
.submission-paragraph-text :deep(h3 + p),
.submission-paragraph-text :deep(h4 + p) {
  margin-top: 8px;
}

.submission-paragraph-text :deep(h3),
.submission-paragraph-text :deep(h4),
.submission-paragraph-text :deep(h5),
.submission-paragraph-text :deep(h6) {
  font-size: 15px;
  font-weight: 800;
}

.submission-paragraph-text :deep(.md-list-item)::before {
  content: '- ';
  color: var(--color-brand);
  font-weight: 700;
}

.submission-paragraph-text :deep(code) {
  padding: 1px 4px;
  border-radius: 4px;
  background: #f3f4f6;
  font-family: inherit;
  font-size: 0.95em;
}

.submission-paragraph-text :deep(blockquote) {
  margin: 8px 0;
  padding: 8px 12px;
  border-left: 3px solid var(--color-brand);
  background: #fafafa;
  color: var(--color-text-secondary);
}

.submission-ai-inline,
.submission-admin-inline {
  grid-column: 2;
  padding: 10px 12px;
  border-radius: 6px;
}

.submission-ai-inline {
  border: 1px solid rgba(141, 27, 53, 0.2);
  border-left: 3px solid var(--color-brand);
  background: #fff;
}

.submission-admin-inline {
  border: 1px solid #fecaca;
  border-left: 3px solid #b91c1c;
  background: #fff7f7;
}

.submission-ai-inline strong,
.submission-admin-inline strong,
.submission-ai-inline p,
.submission-admin-inline p,
.submission-ai-inline small,
.submission-admin-inline small {
  display: block;
  margin: 0;
}

.submission-ai-inline strong {
  margin-bottom: 4px;
  font-size: 12px;
  color: var(--color-brand);
}

.submission-admin-inline strong {
  margin-bottom: 4px;
  font-size: 12px;
  color: #b91c1c;
}

.submission-ai-inline p,
.submission-admin-inline p {
  color: var(--color-text);
  line-height: 1.6;
}

.submission-ai-inline small,
.submission-admin-inline small {
  margin-top: 4px;
  color: var(--color-text-muted);
  line-height: 1.5;
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
  width: 40px;
  height: 40px;
  border-radius: 50%;
  position: relative;
  background: var(--color-brand-light);
  color: var(--color-brand);
}

.login-required-icon::before {
  content: '';
  position: absolute;
  left: 12px;
  top: 17px;
  width: 16px;
  height: 12px;
  border: 2px solid currentColor;
  border-radius: 3px;
}

.login-required-icon::after {
  content: '';
  position: absolute;
  left: 15px;
  top: 9px;
  width: 10px;
  height: 12px;
  border: 2px solid currentColor;
  border-bottom: 0;
  border-radius: 8px 8px 0 0;
}

.error-icon {
  background: var(--color-error-bg);
  color: var(--color-error-text);
}

.error-icon::before {
  content: '!';
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  font-size: 24px;
  font-weight: 800;
}

.empty-icon::before {
  content: '';
  position: absolute;
  left: 10px;
  right: 10px;
  top: 13px;
  height: 14px;
  border: 2px solid currentColor;
  border-radius: 3px;
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

.version-admin-comments {
  margin-top: 12px;
  padding: 12px;
  border: 1px solid #fecaca;
  border-radius: 6px;
  background: #fff7f7;
}

.version-admin-comments > strong {
  display: block;
  margin-bottom: 8px;
  font-size: 13px;
  color: #991b1b;
}

.version-comment-batch + .version-comment-batch {
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px solid #fee2e2;
}

.version-comment-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 6px;
  font-size: 12px;
  color: var(--color-text-muted);
}

.version-review-comment {
  margin: 0 0 8px;
  font-size: 13px;
  color: var(--color-text-secondary);
  line-height: 1.6;
}

.version-admin-comments ul {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.version-admin-comments li {
  display: grid;
  grid-template-columns: 42px 1fr;
  gap: 8px;
  align-items: start;
  font-size: 13px;
}

.version-admin-comments li > span {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 24px;
  border-radius: 4px;
  background: #fee2e2;
  color: #991b1b;
  font-weight: 700;
}

.version-admin-comments li p {
  margin: 0;
  color: var(--color-text);
  line-height: 1.6;
}

.version-admin-comments li em {
  display: block;
  margin-top: 4px;
  font-style: normal;
  color: var(--color-text-secondary);
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

  .submission-detail-toolbar,
  .submission-detail-header {
    flex-direction: column;
    align-items: stretch;
  }

  .submission-detail-grid {
    grid-template-columns: 1fr;
  }

  .submission-detail-side {
    position: static;
  }

  .submissions-toolbar {
    flex-direction: column;
    align-items: stretch;
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
