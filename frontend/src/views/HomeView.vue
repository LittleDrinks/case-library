<template>
  <div class="view-home">
    <!-- Hero -->
    <div class="hero">
      <h1>欢迎来到强国有我思政案例库</h1>
      <p class="hero-desc">
        上海大学思政案例库是汇集优质思政教学案例的学术资源平台。
      </p>
    </div>

    <!-- Stats -->
    <section class="stats-section" aria-label="统计数据">
      <div v-if="statsLoading" class="state-loading compact">
        <div class="spinner" aria-hidden="true"></div>
        <p>加载统计数据…</p>
      </div>
      <div v-else-if="statsError" class="state-error compact">
        <p>{{ statsError }}</p>
        <button type="button" class="btn-text" @click="loadStats">重试</button>
      </div>
      <div v-else class="stats-grid">
        <div class="stat-card">
          <div class="stat-eyebrow">案例</div>
          <div class="stat-value">{{ formatNumber(stats.total_cases) }}</div>
          <div class="stat-label">已发布案例</div>
        </div>
        <div class="stat-card">
          <div class="stat-eyebrow">浏览</div>
          <div class="stat-value">{{ formatNumber(stats.total_views) }}</div>
          <div class="stat-label">总浏览量</div>
        </div>
        <div class="stat-card">
          <div class="stat-eyebrow">互动</div>
          <div class="stat-value">{{ formatNumber(stats.total_likes) }}</div>
          <div class="stat-label">总点赞数</div>
        </div>
        <div class="stat-card">
          <div class="stat-eyebrow">分类</div>
          <div class="stat-value">{{ typeCount }}</div>
          <div class="stat-label">案例类型</div>
        </div>
      </div>
    </section>

    <!-- Trending -->
    <section class="cases-section" aria-label="热门案例">
      <div class="section-header">
        <h2>热门案例</h2>
        <button type="button" class="btn-text-link" @click="goToLibrary">
          浏览全部 →
        </button>
      </div>
      <div v-if="trendingLoading" class="state-loading compact">
        <div class="spinner" aria-hidden="true"></div>
        <p>加载中…</p>
      </div>
      <div v-else-if="trendingError" class="state-error compact">
        <p>{{ trendingError }}</p>
        <button type="button" class="btn-text" @click="loadTrending">重试</button>
      </div>
      <div v-else-if="trendingCases.length === 0" class="state-empty compact">
        <p>暂无热门案例</p>
      </div>
      <div v-else class="case-cards">
        <div
          v-for="c in trendingCases"
          :key="c.id"
          class="case-card"
          @click="openDetail(c.id)"
        >
          <div class="case-card-top">
            <span class="case-type">{{ typeLabel(c.type) }}</span>
            <span v-if="c.theme" class="case-theme">{{ c.theme }}</span>
          </div>
          <h3 class="case-title">{{ c.title }}</h3>
          <p class="case-preview">{{ preview(c.content) }}</p>
          <div class="case-card-footer">
            <span class="meta-stat">浏览 {{ c.view_count || 0 }}</span>
            <span class="meta-stat">点赞 {{ c.like_count || 0 }}</span>
            <span class="meta-date">{{ formatDate(c.created_at) }}</span>
          </div>
        </div>
      </div>
    </section>

    <!-- Latest -->
    <section class="cases-section" aria-label="最新案例">
      <div class="section-header">
        <h2>最新案例</h2>
        <button type="button" class="btn-text-link" @click="goToLibrary">
          浏览全部 →
        </button>
      </div>
      <div v-if="latestLoading" class="state-loading compact">
        <div class="spinner" aria-hidden="true"></div>
        <p>加载中…</p>
      </div>
      <div v-else-if="latestError" class="state-error compact">
        <p>{{ latestError }}</p>
        <button type="button" class="btn-text" @click="loadLatest">重试</button>
      </div>
      <div v-else-if="latestCases.length === 0" class="state-empty compact">
        <p>暂无最新案例</p>
      </div>
      <div v-else class="case-cards">
        <div
          v-for="c in latestCases"
          :key="c.id"
          class="case-card"
          @click="openDetail(c.id)"
        >
          <div class="case-card-top">
            <span class="case-type">{{ typeLabel(c.type) }}</span>
            <span v-if="c.theme" class="case-theme">{{ c.theme }}</span>
          </div>
          <h3 class="case-title">{{ c.title }}</h3>
          <p class="case-preview">{{ preview(c.content) }}</p>
          <div class="case-card-footer">
            <span class="meta-stat">浏览 {{ c.view_count || 0 }}</span>
            <span class="meta-stat">点赞 {{ c.like_count || 0 }}</span>
            <span class="meta-date">{{ formatDate(c.created_at) }}</span>
          </div>
        </div>
      </div>
    </section>

  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue';
import {
  fetchStatistics,
  fetchTrendingCases,
  fetchLatestCases,
} from '../api/cases.js';

const stats = ref({ total_cases: 0, total_views: 0, total_likes: 0, by_type: {}, by_theme: {} });
const statsLoading = ref(false);
const statsError = ref('');

const trendingCases = ref([]);
const trendingLoading = ref(false);
const trendingError = ref('');

const latestCases = ref([]);
const latestLoading = ref(false);
const latestError = ref('');

const typeCount = computed(() => Object.keys(stats.value.by_type || {}).length);

function formatNumber(n) {
  if (n == null) return '0';
  return n.toLocaleString('zh-CN');
}

function formatDate(value) {
  if (!value) return '';
  const d = new Date(value);
  if (isNaN(d.getTime())) return String(value);
  return d.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  });
}

function preview(content) {
  const text = (content || '').replace(/\s+/g, ' ').trim();
  if (text.length <= 100) return text;
  return text.slice(0, 100) + '…';
}

function typeLabel(type) {
  const map = {
    TYPE_A: '思政课教学案例',
    TYPE_B: '课程思政共享资源案例',
    TYPE_C: '实践育人案例',
  };
  return map[type] || type || '未知类型';
}

function goToLibrary() {
  window.location.hash = 'library';
}

async function loadStats() {
  statsLoading.value = true;
  statsError.value = '';
  try {
    const res = await fetchStatistics();
    if (res?.success && res.data) {
      stats.value = res.data;
    } else {
      throw new Error(res?.message || '加载统计失败');
    }
  } catch (err) {
    statsError.value = err.message || '加载统计数据失败';
  } finally {
    statsLoading.value = false;
  }
}

async function loadTrending() {
  trendingLoading.value = true;
  trendingError.value = '';
  try {
    const res = await fetchTrendingCases(6);
    if (res?.success) {
      trendingCases.value = res.data || [];
    } else {
      throw new Error(res?.message || '加载热门案例失败');
    }
  } catch (err) {
    trendingError.value = err.message || '加载热门案例失败';
    trendingCases.value = [];
  } finally {
    trendingLoading.value = false;
  }
}

async function loadLatest() {
  latestLoading.value = true;
  latestError.value = '';
  try {
    const res = await fetchLatestCases(6);
    if (res?.success) {
      latestCases.value = res.data || [];
    } else {
      throw new Error(res?.message || '加载最新案例失败');
    }
  } catch (err) {
    latestError.value = err.message || '加载最新案例失败';
    latestCases.value = [];
  } finally {
    latestLoading.value = false;
  }
}

function openDetail(caseId) {
  window.location.hash = `library?case=${encodeURIComponent(caseId)}`;
}

onMounted(() => {
  loadStats();
  loadTrending();
  loadLatest();
});
</script>

<style scoped>
.view-home {
  max-width: var(--max-content-width);
  margin: 0 auto;
  padding: 32px 24px 48px;
}

/* Hero */
.hero {
  margin-bottom: 28px;
}

.hero h1 {
  margin: 0 0 10px;
  font-size: 28px;
  line-height: 1.3;
  color: var(--color-text);
  font-weight: 700;
}

.hero-desc {
  margin: 0;
  font-size: 15px;
  color: var(--color-text-secondary);
  line-height: 1.7;
}

/* Sections */
.stats-section {
  margin-bottom: 32px;
}

.cases-section {
  margin-bottom: 32px;
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
  flex-wrap: wrap;
  gap: 8px;
}

.section-header h2 {
  margin: 0;
  font-size: 20px;
  font-weight: 700;
  color: var(--color-text);
}

.btn-text-link {
  background: transparent;
  border: 0;
  color: var(--color-brand);
  font: inherit;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  padding: 4px 0;
  transition: color 0.15s;
}

.btn-text-link:hover {
  color: var(--color-brand-dark);
}

/* Stats grid */
.stats-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
}

.stat-card {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 8px;
  padding: 20px 16px;
  text-align: center;
  transition: box-shadow 0.15s;
  border-top: 2px solid var(--color-brand);
}

.stat-card:hover {
  box-shadow: 0 4px 16px rgba(29, 35, 47, 0.06);
}

.stat-eyebrow {
  font-size: 11px;
  font-weight: 600;
  color: var(--color-text-muted);
  letter-spacing: 0.8px;
  text-transform: uppercase;
  margin-bottom: 8px;
}

.stat-value {
  font-size: 24px;
  font-weight: 700;
  color: var(--color-brand);
  line-height: 1.3;
  margin-bottom: 4px;
}

.stat-label {
  font-size: 13px;
  color: var(--color-text-secondary);
}

/* Case cards */
.case-cards {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
}

.case-card {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 8px;
  padding: 16px;
  cursor: pointer;
  transition: box-shadow 0.15s, border-color 0.15s;
  display: flex;
  flex-direction: column;
}

.case-card:hover {
  box-shadow: 0 4px 16px rgba(29, 35, 47, 0.08);
  border-color: rgba(141, 27, 53, 0.25);
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
  margin: 0 0 8px;
  font-size: 16px;
  font-weight: 700;
  color: var(--color-text);
  line-height: 1.4;
}

.case-preview {
  margin: 0 0 12px;
  font-size: 13px;
  color: var(--color-text-secondary);
  line-height: 1.6;
  word-break: break-word;
  flex: 1;
}

.case-card-footer {
  display: flex;
  flex-wrap: wrap;
  gap: 10px 14px;
  font-size: 12px;
  color: var(--color-text-muted);
  margin-top: auto;
}

.meta-stat {
  white-space: nowrap;
}

.meta-date {
  margin-left: auto;
  white-space: nowrap;
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

.state-loading.compact,
.state-error.compact,
.state-empty.compact {
  padding: 32px 24px;
}

.state-loading p,
.state-error p,
.state-empty p {
  margin: 0;
  font-size: 14px;
  color: var(--color-text-secondary);
}

.spinner {
  width: 28px;
  height: 28px;
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

.btn-text {
  background: transparent;
  border: 0;
  color: var(--color-brand);
  font: inherit;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  text-decoration: underline;
  padding: 4px 8px;
}

.btn-text:hover {
  color: var(--color-brand-dark);
}

/* Responsive */
@media (max-width: 1024px) {
  .case-cards {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 768px) {
  .view-home {
    padding: 20px 12px 32px;
  }

  .hero h1 {
    font-size: 22px;
  }

  .stats-grid {
    grid-template-columns: repeat(2, 1fr);
    gap: 12px;
  }

  .stat-card {
    padding: 16px 12px;
  }

  .stat-value {
    font-size: 20px;
  }

  .case-cards {
    grid-template-columns: 1fr;
    gap: 12px;
  }

}

@media (max-width: 390px) {
  .stats-grid {
    grid-template-columns: 1fr 1fr;
    gap: 8px;
  }

  .stat-card {
    padding: 12px 8px;
  }

  .stat-value {
    font-size: 18px;
  }

  .case-card-top {
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>
