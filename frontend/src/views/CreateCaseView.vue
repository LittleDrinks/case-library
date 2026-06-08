<template>
  <div class="create-case-wizard">
    <!-- Mobile step summary -->
    <div class="wizard-rail-mobile">
      <div class="mobile-progress-header">
        <span class="mobile-progress-title">进度</span>
        <span class="mobile-progress-percent">{{ progressPercent }}% 完成</span>
      </div>
      <div class="mobile-progress-bar-track">
        <div class="mobile-progress-bar" :style="{ width: progressPercent + '%' }"></div>
      </div>
      <div class="mobile-steps">
        <div
          v-for="(step, idx) in steps"
          :key="step.id"
          :class="[
            'mobile-step',
            { active: idx === currentStep, completed: idx < currentStep },
          ]"
        >
          <span class="mobile-step-dot">{{ idx < currentStep ? '✓' : idx + 1 }}</span>
          <span class="mobile-step-label">{{ step.label }}</span>
        </div>
      </div>
    </div>

    <!-- Desktop progress rail -->
    <aside class="wizard-rail">
      <div class="rail-header">
        <div class="rail-header-top">
          <div class="rail-title">进度</div>
          <div class="rail-percent">{{ progressPercent }}% 完成</div>
        </div>
        <div class="rail-progress-track">
          <div class="rail-progress-bar" :style="{ width: progressPercent + '%' }"></div>
        </div>
      </div>
      <nav class="rail-steps" aria-label="创建步骤">
        <div
          v-for="(step, idx) in steps"
          :key="step.id"
          :class="[
            'rail-step',
            { active: idx === currentStep, completed: idx < currentStep, future: idx > currentStep },
          ]"
        >
          <div class="rail-step-left">
            <div class="step-icon" aria-hidden="true">
              <svg v-if="step.id === 'basic'" viewBox="0 0 24 24" width="18" height="18">
                <path fill="currentColor" d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
                <polyline points="14 2 14 8 20 8" fill="none" stroke="currentColor" stroke-width="2"></polyline>
              </svg>
              <svg v-else-if="step.id === 'content'" viewBox="0 0 24 24" width="18" height="18">
                <path fill="currentColor" d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"></path>
                <path fill="currentColor" d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"></path>
              </svg>
              <svg v-else-if="step.id === 'classify'" viewBox="0 0 24 24" width="18" height="18">
                <path fill="currentColor" d="M12 2l-9 4.5v6L3 13l9 4.5L21 13l-0-0.5v-6L12 2z"></path>
                <path fill="currentColor" d="M12 22l-9-4.5v-3l9 4.5 9-4.5v3L12 22z"></path>
              </svg>
              <svg v-else-if="step.id === 'review'" viewBox="0 0 24 24" width="18" height="18">
                <path fill="currentColor" d="M12 22c5.523 0 10-4.477 10-10S17.523 2 12 2 2 6.477 2 12s4.477 10 10 10z"></path>
                <path fill="none" stroke="#fff" stroke-width="2" d="M9 12l2 2 4-4"></path>
              </svg>
              <svg v-else viewBox="0 0 24 24" width="18" height="18">
                <path fill="currentColor" d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path>
                <polyline points="22 4 12 14.01 9 11.01" fill="none" stroke="currentColor" stroke-width="2"></polyline>
              </svg>
            </div>
            <div class="step-marker" aria-hidden="true">
              {{ idx < currentStep ? '✓' : idx + 1 }}
            </div>
          </div>
          <div class="step-label">{{ step.label }}</div>
        </div>
      </nav>
    </aside>

    <main class="wizard-main">
      <div class="wizard-breadcrumb">
        <span class="bc-parent">创建案例</span>
        <span class="bc-chevron" aria-hidden="true">›</span>
        <span class="bc-current">{{ steps[currentStep].label }}</span>
      </div>

      <h1 class="wizard-title">{{ stepMeta.title }}</h1>
      <p class="wizard-desc">{{ stepMeta.desc }}</p>

      <!-- Unauthenticated notice -->
      <div v-if="!isAuthenticated" class="login-required-card">
        <div class="login-required-icon" aria-hidden="true">
          <svg viewBox="0 0 24 24" width="34" height="34">
            <rect x="5" y="10" width="14" height="10" rx="2" fill="none" stroke="currentColor" stroke-width="2"></rect>
            <path d="M8 10V7a4 4 0 0 1 8 0v3" fill="none" stroke="currentColor" stroke-width="2"></path>
          </svg>
        </div>
        <h3>请先登录</h3>
        <p>创建案例需要登录账号。请先登录后再继续。</p>
      </div>

      <div v-else class="wizard-form">
        <!-- Step 1: 基本信息 -->
        <template v-if="currentStep === 0">
          <div class="field">
            <label for="ccf-title">案例标题 <span class="required" aria-hidden="true">*</span></label>
            <input
              id="ccf-title"
              v-model="form.title"
              type="text"
              placeholder="请输入案例标题"
              :aria-invalid="!!errors.title"
              @blur="touch('title')"
            />
            <div v-if="errors.title" class="field-error" role="alert">{{ errors.title }}</div>
          </div>

          <div class="row two-col">
            <div class="field">
              <label for="ccf-author">作者姓名</label>
              <input
                id="ccf-author"
                :value="displayAuthor"
                type="text"
                readonly
                class="readonly"
                aria-describedby="ccf-author-tip"
              />
              <div id="ccf-author-tip" class="field-help">取自当前登录账号信息</div>
            </div>
            <div class="field">
              <label for="ccf-department">
                所属部门/学院 <span class="required" aria-hidden="true">*</span>
              </label>
              <input
                id="ccf-department"
                v-model="form.department"
                type="text"
                placeholder="请输入所属部门或学院"
                :aria-invalid="!!errors.department"
                @blur="touch('department')"
              />
              <div v-if="errors.department" class="field-error" role="alert">{{ errors.department }}</div>
            </div>
          </div>

          <div class="tip-card">
            <div class="tip-icon" aria-hidden="true">
              <svg viewBox="0 0 24 24" width="28" height="28">
                <path d="M9 18h6" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"></path>
                <path d="M10 22h4" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"></path>
                <path d="M8 14c-1.4-1.1-2-2.7-2-4.2A6 6 0 0 1 18 9.8c0 1.5-.6 3.1-2 4.2-.8.7-1 1.4-1 2H9c0-.6-.2-1.3-1-2Z" fill="none" stroke="currentColor" stroke-width="2"></path>
              </svg>
            </div>
            <div class="tip-body">
              <div class="tip-title">编写小贴士</div>
              <ul>
                <li>标题应简洁明了，突出案例的核心问题与教学价值。</li>
                <li>作者姓名取自登录账号，如需修改请联系管理员。</li>
                <li>部门/学院信息将用于案例归属、统计与检索。</li>
              </ul>
            </div>
          </div>
        </template>

        <!-- Step 2: 案例内容 -->
        <template v-if="currentStep === 1">
          <div class="field">
            <label for="ccf-content">案例正文 <span class="required" aria-hidden="true">*</span></label>
            <textarea
              id="ccf-content"
              v-model="form.content"
              rows="14"
              placeholder="请使用 Markdown 格式编写案例正文，建议包含背景、问题、分析、反思等部分。"
              :aria-invalid="!!errors.content"
              @blur="touch('content')"
            ></textarea>
            <div class="textarea-meta">
              <span>字数 {{ wordCount }}</span>
              <span>预计阅读 {{ readingTime }} 分钟</span>
            </div>
            <div v-if="errors.content" class="field-error" role="alert">{{ errors.content }}</div>
          </div>
        </template>

        <!-- Step 3: 分类选择 -->
        <template v-if="currentStep === 2">
          <div class="hint-banner">
            <span class="hint-icon" aria-hidden="true">
              <svg viewBox="0 0 24 24" width="22" height="22">
                <path d="M12 3v3" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"></path>
                <rect x="5" y="7" width="14" height="11" rx="2" fill="none" stroke="currentColor" stroke-width="2"></rect>
                <circle cx="9" cy="12" r="1" fill="currentColor"></circle>
                <circle cx="15" cy="12" r="1" fill="currentColor"></circle>
                <path d="M9 16h6" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"></path>
              </svg>
            </span>
            <span>不确定分类？可点击右下角 AI 助手，根据已填写内容获取一次本地建议。</span>
          </div>

          <div class="field">
            <label for="ccf-type">案例类型 <span class="required" aria-hidden="true">*</span></label>
            <select
              id="ccf-type"
              v-model="form.type"
              :aria-invalid="!!errors.type"
              @change="touch('type')"
            >
              <option disabled value="">请选择案例类型</option>
              <option v-for="(label, key) in constants.case_types" :key="key" :value="key">
                {{ label }}
              </option>
            </select>
            <div class="field-help">类型决定案例在库中的展示分类与主要使用场景。</div>
            <div v-if="errors.type" class="field-error" role="alert">{{ errors.type }}</div>
          </div>

          <div class="field">
            <label for="ccf-theme">案例主题 <span class="required" aria-hidden="true">*</span></label>
            <select
              id="ccf-theme"
              v-model="form.theme"
              :aria-invalid="!!errors.theme"
              @change="touch('theme')"
            >
              <option disabled value="">请选择案例主题</option>
              <option v-for="t in constants.themes" :key="t" :value="t">{{ t }}</option>
            </select>
            <div class="field-help">主题用于跨类型的关键词聚合与检索。</div>
            <div v-if="errors.theme" class="field-error" role="alert">{{ errors.theme }}</div>
          </div>

          <!-- Transient local helper panel -->
          <div v-if="showHelper" class="helper-panel" role="dialog" aria-modal="true" aria-labelledby="helper-title">
            <div class="helper-header">
              <span id="helper-title">AI 分类助手（本地建议）</span>
              <button type="button" class="helper-close-btn" aria-label="关闭" @click="showHelper = false">×</button>
            </div>
            <div class="helper-body">
              <p class="helper-desc">请输入您想咨询的问题，例如：“帮我推荐案例类型和主题”。</p>
              <input
                v-model="helperInput"
                type="text"
                placeholder="输入问题…"
                @keyup.enter="runHelper"
              />
              <button type="button" class="btn-helper" :disabled="!helperInput.trim()" @click="runHelper">
                获取建议
              </button>
              <div v-if="helperResponse" class="helper-response" role="status" aria-live="polite">
                {{ helperResponse }}
              </div>
            </div>
          </div>

          <button
            type="button"
            class="fab-helper"
            aria-label="打开 AI 分类助手"
            @click="showHelper = true"
          >
            <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true">
              <path d="M12 3v3" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"></path>
              <rect x="5" y="7" width="14" height="11" rx="2" fill="none" stroke="currentColor" stroke-width="2"></rect>
              <path d="M9 12h.01M15 12h.01M9 16h6" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"></path>
            </svg>
          </button>
        </template>

        <!-- Step 4: AI 审核 -->
        <template v-if="currentStep === 3">
          <div class="review-header">
            <span class="review-badge">整体审核进度</span>
            <span class="review-percent">{{ aiReviewProgress }}% 已完成</span>
          </div>
          <div class="review-progress-track">
            <div class="review-progress-bar" :style="{ width: aiReviewProgress + '%' }"></div>
          </div>
          <p class="review-note">
            以下结果来自后端 AI 自查接口，仅作为作者提交前参考，不代表专家审核结论。
          </p>

          <div v-if="aiPromptLoadError" class="ai-unavailable-banner" role="status">
            {{ aiPromptLoadError }}
          </div>

          <div class="ai-review-toolbar">
            <button
              type="button"
              class="btn-primary"
              :disabled="aiRunningAll || !canRunAiReview"
              @click="runAllAiReviews"
            >
              {{ aiRunningAll ? '自查中…' : '运行全部自查' }}
            </button>
            <span class="ai-toolbar-note">
              需要先填写标题、正文、类型和主题。AI 不可用时可继续提交人工审核。
            </span>
          </div>

          <div class="review-grid" data-testid="ai-review-grid">
            <div
              v-for="item in aiReviewItems"
              :key="item.id"
              class="review-card ai-review-card"
              :class="{ 'score-summary-card': item.id === 'workflow/score' }"
            >
              <div class="review-card-top">
                <div class="review-card-icon" aria-hidden="true">
                  <svg v-if="item.id === 'workflow/completeness'" viewBox="0 0 24 24" width="32" height="32">
                    <path d="M4 5h7v7H4zM13 5h7v7h-7zM4 14h7v5H4z" fill="none" stroke="currentColor" stroke-width="2"></path>
                    <path d="M14 17l2 2 4-5" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"></path>
                  </svg>
                  <svg v-else-if="item.id === 'workflow/categorization'" viewBox="0 0 24 24" width="32" height="32">
                    <path d="M5 4h14v16H5z" fill="none" stroke="currentColor" stroke-width="2"></path>
                    <path d="M8 8h5M8 12h4M8 16h3M15 15l2 2 3-5" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"></path>
                  </svg>
                  <svg v-else-if="item.id === 'workflow/expression'" viewBox="0 0 24 24" width="32" height="32">
                    <path d="M5 19 12 5l7 14M8 14h8" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"></path>
                    <path d="m16 6 2 2 3-4" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"></path>
                  </svg>
                </div>
                <div class="review-card-copy">
                  <div class="review-card-title">{{ item.name }}</div>
                  <div class="review-card-desc">{{ item.description }}</div>
                </div>
                <span class="ai-status-pill" :class="aiResultClass(item.id)">
                  {{ aiResultLabel(item.id) }}
                </span>
              </div>

              <div v-if="item.id === 'workflow/score'" class="score-summary">
                <div class="score-ring" :style="{ '--score-deg': scoreRingDegrees(item.id) }">
                  <strong>{{ scoreValue(item.id) }}</strong>
                  <span>SCORE</span>
                </div>
                <div class="score-summary-text">{{ scoreRating(item.id) }}</div>
              </div>

              <div v-if="aiReviewState[item.id].status === 'idle'" class="ai-placeholder">
                尚未运行。点击下方按钮获取作者侧自查建议。
              </div>

              <div v-else-if="aiReviewState[item.id].status === 'loading'" class="ai-placeholder">
                正在请求后端 AI 自查…
              </div>

              <div v-else-if="aiReviewState[item.id].status === 'error'" class="ai-error">
                {{ aiReviewState[item.id].error }}
              </div>

              <div v-else class="ai-result">
                <div v-if="aiReviewState[item.id].parsed" class="ai-result-body">
                  <div v-if="aiReviewState[item.id].parsed.detail" class="ai-detail">
                    {{ aiReviewState[item.id].parsed.detail }}
                  </div>
                  <div v-if="aiReviewState[item.id].parsed.score != null" class="ai-score">
                    评分 {{ aiReviewState[item.id].parsed.score }}
                  </div>
                  <ul
                    v-if="Array.isArray(aiReviewState[item.id].parsed.suggestions) && aiReviewState[item.id].parsed.suggestions.length"
                    class="ai-suggestions"
                  >
                    <li v-for="suggestion in aiReviewState[item.id].parsed.suggestions" :key="suggestion">
                      {{ suggestion }}
                    </li>
                  </ul>
                </div>
                <pre v-else class="ai-answer">{{ aiReviewState[item.id].answer }}</pre>
                <div v-if="aiReviewState[item.id].parse_error" class="ai-parse-warning">
                  {{ aiReviewState[item.id].parse_error }}
                </div>
              </div>

              <button
                type="button"
                class="btn-secondary ai-run-btn"
                :disabled="aiReviewState[item.id].status === 'loading' || !canRunAiReview"
                @click="runAiReview(item.id)"
              >
                {{ aiReviewState[item.id].status === 'loading' ? '运行中…' : '运行此项' }}
              </button>
            </div>
          </div>
        </template>

        <!-- Step 5: 提交确认 -->
        <template v-if="currentStep === 4">
          <div class="pass-notice">
            <span class="pass-icon" aria-hidden="true">
              <svg viewBox="0 0 24 24" width="22" height="22">
                <circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" stroke-width="2"></circle>
                <path d="m8 12 3 3 5-6" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"></path>
              </svg>
            </span>
            <span>专家人工审核流程：提交后将进入待审核队列，AI 自查结果仅作为专家参考。</span>
          </div>

          <div class="submit-card">
            <div class="submit-card-header">
              <div class="submit-title-wrap">
                <span class="submit-title-icon" aria-hidden="true">
                  <svg viewBox="0 0 24 24" width="26" height="26">
                    <path d="M5 12h14M13 6l6 6-6 6" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"></path>
                  </svg>
                </span>
                <h3>提交至专家审核</h3>
              </div>
              <span class="status-pill">待审核</span>
            </div>
            <ul class="submit-checklist">
              <li :class="{ ok: form.title }">
                <span class="check" aria-hidden="true">{{ form.title ? '✓' : '○' }}</span>
                案例标题：{{ form.title || '未填写' }}
              </li>
              <li :class="{ ok: form.department }">
                <span class="check" aria-hidden="true">{{ form.department ? '✓' : '○' }}</span>
                所属部门/学院：{{ form.department || '未填写' }}
              </li>
              <li :class="{ ok: form.content }">
                <span class="check" aria-hidden="true">{{ form.content ? '✓' : '○' }}</span>
                案例正文：{{ contentSummary }}
              </li>
              <li :class="{ ok: form.type }">
                <span class="check" aria-hidden="true">{{ form.type ? '✓' : '○' }}</span>
                案例类型：{{ form.type ? constants.case_types[form.type] : '未选择' }}
              </li>
              <li :class="{ ok: form.theme }">
                <span class="check" aria-hidden="true">{{ form.theme ? '✓' : '○' }}</span>
                案例主题：{{ form.theme || '未选择' }}
              </li>
            </ul>
            <button
              type="button"
              class="btn-submit-final"
              :disabled="submitting || !canSubmit"
              @click="handleFormalSubmit"
            >
              <span>{{ submitting ? '提交中…' : '正式提交案例' }}</span>
              <svg class="icon" viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
                <path fill="currentColor" d="M2 21l21-9L2 3v7l15 2-15 2v7z"></path>
              </svg>
            </button>
          </div>
        </template>

        <!-- Bottom actions -->
        <div class="wizard-actions">
          <template v-if="currentStep > 0 && currentStep < 4">
            <button type="button" class="btn-secondary" @click="prevStep">上一步</button>
          </template>
          <template v-if="currentStep < 4">
            <button type="button" class="btn-secondary" :disabled="saving" @click="handleSaveDraft">
              {{ saving ? '保存中…' : '保存草稿' }}
            </button>
            <button type="button" class="btn-primary" @click="nextStep">
              继续 <span class="arrow" aria-hidden="true">→</span>
            </button>
          </template>
          <template v-if="currentStep === 4">
            <button type="button" class="btn-secondary" @click="currentStep = 1">返回修改</button>
          </template>
        </div>
      </div>
    </main>
  </div>
</template>

<script setup>
import { ref, reactive, computed, watch, onMounted, nextTick } from "vue";
import { currentUser, isLoggedIn } from "../api/auth.js";
import {
  fetchCaseConstants,
  createCase,
  updateCase,
  submitCaseById,
} from "../api/cases.js";
import { listPrompts, runPrompt } from "../api/ai.js";

const DRAFT_KEY = "case_library_create_case_draft";

const steps = [
  { id: "basic", label: "基本信息" },
  { id: "content", label: "案例内容" },
  { id: "classify", label: "分类选择" },
  { id: "review", label: "提交前自查" },
  { id: "confirm", label: "提交确认" },
];

const currentStep = ref(0);
const saving = ref(false);
const submitting = ref(false);
const caseId = ref(null);

const form = reactive({
  title: "",
  author: "",
  department: "",
  content: "",
  type: "",
  theme: "",
});

const touched = reactive({
  title: false,
  department: false,
  content: false,
  type: false,
  theme: false,
});

const constants = reactive({
  case_types: {
    TYPE_A: "思政课教学案例",
    TYPE_B: "课程思政共享资源案例",
    TYPE_C: "实践育人案例",
  },
  themes: ["强国建设", "实践育人", "数字赋能", "铸魂育人"],
  statuses: {
    draft: "草稿",
    pending_review: "待审核",
    approved: "已通过",
    needs_revision: "已驳回",
  },
});

const showHelper = ref(false);
const helperInput = ref("");
const helperResponse = ref("");
const aiPromptLoadError = ref("");
const aiRunningAll = ref(false);

const DEFAULT_AI_REVIEW_ITEMS = [
  {
    id: "workflow/completeness",
    name: "完整性检查",
    description: "检查案例是否包含背景、做法、成效与反思等关键板块。",
    variables: ["title", "content"],
  },
  {
    id: "workflow/categorization",
    name: "分类检查",
    description: "检查案例类型和主题是否与正文内容匹配。",
    variables: ["title", "content", "type", "theme"],
  },
  {
    id: "workflow/expression",
    name: "表达检查",
    description: "检查案例表达是否清晰、正式、适合专家审核。",
    variables: ["title", "content"],
  },
  {
    id: "workflow/score",
    name: "综合评分",
    description: "给出提交前综合自查评分和主要风险。",
    variables: ["title", "content"],
  },
];

const aiReviewItems = ref([...DEFAULT_AI_REVIEW_ITEMS]);
const aiReviewState = reactive(
  Object.fromEntries(
    DEFAULT_AI_REVIEW_ITEMS.map((item) => [
      item.id,
      {
        status: "idle",
        answer: "",
        parsed: null,
        parse_error: null,
        error: "",
      },
    ])
  )
);

const displayAuthor = computed(() => {
  const user = currentUser();
  return form.author || user?.nickname || user?.username || "";
});

const wordCount = computed(() => {
  const text = form.content || "";
  // Simple CJK + word token count
  const cjk = (text.match(/[一-龥]/g) || []).length;
  const words = (text.replace(/[一-龥]/g, "").match(/\b[a-zA-Z0-9_]+\b/g) || []).length;
  return cjk + words;
});

const readingTime = computed(() => {
  const wpm = 300;
  return Math.max(1, Math.ceil(wordCount.value / wpm));
});

const contentSummary = computed(() => {
  const text = form.content || "";
  if (!text) return "未填写";
  const snippet = text.replace(/\s+/g, " ").slice(0, 60);
  return text.length > 60 ? snippet + "…" : snippet;
});

const isAuthenticated = computed(() => isLoggedIn());

const progressPercent = computed(() => {
  return Math.round(((currentStep.value + 1) / steps.length) * 100);
});

const stepMeta = computed(() => {
  const metas = [
    { title: "填写基本信息", desc: "完善案例标题、作者与所属部门，为后续编写打好基础。" },
    { title: "编写案例内容", desc: "在下方编辑器中撰写案例正文，支持 Markdown 格式。" },
    { title: "选择案例分类", desc: "选择案例类型与主题，便于检索与推荐。" },
    { title: "提交前自查", desc: "根据已填写内容进行自查，确认必填项完整后再提交。" },
    { title: "确认并提交", desc: "核对填写内容，确认后提交至专家审核。" },
  ];
  return metas[currentStep.value];
});

const errors = computed(() => {
  const e = {};
  if (touched.title && !form.title.trim()) e.title = "请输入案例标题";
  if (touched.department && !form.department.trim()) e.department = "请输入所属部门/学院";
  if (touched.content && !form.content.trim()) e.content = "请输入案例正文";
  if (touched.type && !form.type) e.type = "请选择案例类型";
  if (touched.theme && !form.theme) e.theme = "请选择案例主题";
  return e;
});

const checklist = computed(() => {
  return {
    structure: !!(form.title.trim() && form.department.trim() && form.content.trim()),
    classification: !!(form.type && form.theme),
    expression: form.content.trim().length >= 50 && form.title.trim().length >= 4,
  };
});

const reviewScore = computed(() => {
  let score = 0;
  if (form.title.trim()) score += 20;
  if (form.department.trim()) score += 15;
  if (form.content.trim()) score += 25;
  if (form.type) score += 20;
  if (form.theme) score += 20;
  return score;
});

const canSubmit = computed(() => {
  return (
    !!form.title.trim() &&
    !!form.department.trim() &&
    !!form.content.trim() &&
    !!form.type &&
    !!form.theme
  );
});

const canRunAiReview = computed(() => {
  return !!(
    form.title.trim() &&
    form.content.trim() &&
    form.type &&
    form.theme &&
    isAuthenticated.value
  );
});

const aiReviewProgress = computed(() => {
  const total = aiReviewItems.value.length || 1;
  const done = aiReviewItems.value.filter((item) => aiReviewState[item.id].status === "success").length;
  return Math.round((done / total) * 100);
});

function touch(field) {
  touched[field] = true;
}

function validateStep(step) {
  if (step === 0) {
    touched.title = true;
    touched.department = true;
    return !errors.value.title && !errors.value.department;
  }
  if (step === 1) {
    touched.content = true;
    return !errors.value.content;
  }
  if (step === 2) {
    touched.type = true;
    touched.theme = true;
    return !errors.value.type && !errors.value.theme;
  }
  return true;
}

function nextStep() {
  if (!validateStep(currentStep.value)) return;
  if (currentStep.value === 3 && hasAiReviewWarning() && !confirmAiReviewWarning()) {
    return;
  }
  if (currentStep.value < steps.length - 1) {
    currentStep.value += 1;
  }
}

function prevStep() {
  if (currentStep.value > 0) {
    currentStep.value -= 1;
  }
}

function buildPayload(status) {
  const payload = {
    title: form.title.trim(),
    content: form.content.trim(),
    department: form.department.trim(),
    type: form.type,
    theme: form.theme,
    status,
  };
  appendAiReviewsPayload(payload);
  return payload;
}

function appendAiReviewsPayload(payload) {
  const reviews = collectAiReviews();
  if (reviews.length) {
    payload.ai_reviews = JSON.stringify(reviews);
  }
  return payload;
}

async function handleSaveDraft() {
  if (!isAuthenticated.value) {
    window.alert("请先登录后再保存草稿");
    return;
  }
  saving.value = true;
  try {
    if (caseId.value) {
      const payload = {
        title: form.title.trim(),
        content: form.content.trim(),
        author: displayAuthor.value,
        department: form.department.trim(),
        type: form.type,
        theme: form.theme,
        change_reason: "保存草稿",
      };
      appendAiReviewsPayload(payload);
      await updateCase(caseId.value, payload);
    } else {
      const res = await createCase(buildPayload("draft"));
      if (res && res.case_id) {
        caseId.value = res.case_id;
      }
    }
    persistDraft();
    window.alert("草稿已保存");
  } catch (err) {
    window.alert(err.message || "保存草稿失败，请稍后重试");
  } finally {
    saving.value = false;
  }
}

async function handleFormalSubmit() {
  if (!canSubmit.value) {
    window.alert("请完善所有必填项后再提交");
    return;
  }
  if (!isAuthenticated.value) {
    window.alert("请先登录后再提交案例");
    return;
  }
  submitting.value = true;
  try {
    if (caseId.value) {
      // Update existing draft with latest form data before submitting
      const payload = {
        title: form.title.trim(),
        content: form.content.trim(),
        author: displayAuthor.value,
        department: form.department.trim(),
        type: form.type,
        theme: form.theme,
        change_reason: "提交前更新",
      };
      appendAiReviewsPayload(payload);
      await updateCase(caseId.value, payload);
      await submitCaseById(caseId.value);
    } else {
      await createCase(buildPayload("pending_review"));
    }
    clearDraft();
    window.alert("案例提交成功，请等待专家审核");
    resetForm();
    currentStep.value = 0;
  } catch (err) {
    window.alert(err.message || "提交失败，请稍后重试");
  } finally {
    submitting.value = false;
  }
}

function persistDraft() {
  try {
    const payload = {
      form: {
        title: form.title,
        author: form.author,
        department: form.department,
        content: form.content,
        type: form.type,
        theme: form.theme,
      },
      caseId: caseId.value,
      savedAt: Date.now(),
    };
    localStorage.setItem(DRAFT_KEY, JSON.stringify(payload));
  } catch {
    // Ignore storage errors
  }
}

function loadDraft() {
  try {
    const raw = localStorage.getItem(DRAFT_KEY);
    if (!raw) return;
    const saved = JSON.parse(raw);
    if (saved && saved.form) {
      Object.assign(form, saved.form);
    }
    if (saved && saved.caseId) {
      caseId.value = saved.caseId;
    }
  } catch {
    // Ignore malformed storage
  }
}

function clearDraft() {
  try {
    localStorage.removeItem(DRAFT_KEY);
  } catch {
    // Ignore
  }
}

function resetForm() {
  form.title = "";
  form.author = "";
  form.department = "";
  form.content = "";
  form.type = "";
  form.theme = "";
  caseId.value = null;
  currentStep.value = 0;
  touched.title = false;
  touched.department = false;
  touched.content = false;
  touched.type = false;
  touched.theme = false;
  for (const item of aiReviewItems.value) {
    resetAiReviewItem(item.id);
  }
}

function ensureAiReviewState(promptId) {
  if (!aiReviewState[promptId]) {
    aiReviewState[promptId] = {
      status: "idle",
      answer: "",
      parsed: null,
      parse_error: null,
      error: "",
    };
  }
  return aiReviewState[promptId];
}

function resetAiReviewItem(promptId) {
  const state = ensureAiReviewState(promptId);
  state.status = "idle";
  state.answer = "";
  state.parsed = null;
  state.parse_error = null;
  state.error = "";
}

function aiStatusLabel(status) {
  if (status === "loading") return "运行中";
  if (status === "success") return "已完成";
  if (status === "error") return "不可用";
  return "待运行";
}

function aiResultClass(promptId) {
  const state = aiReviewState[promptId];
  if (!state) return "idle";
  if (state.status !== "success") return state.status;
  const parsed = state.parsed;
  if (parsed && typeof parsed === "object") {
    if (parsed.pass === false) return "warning";
    const score = Number(parsed.score);
    if (Number.isFinite(score) && score < 70) return "warning";
  }
  return "success";
}

function aiResultLabel(promptId) {
  const className = aiResultClass(promptId);
  if (className === "loading") return "运行中";
  if (className === "error") return "不可用";
  if (className === "warning") return promptId === "workflow/score" ? "需关注" : "待优化";
  if (className === "success") {
    if (promptId === "workflow/categorization") return "准确";
    if (promptId === "workflow/expression") return "规范";
    return "合格";
  }
  return "待运行";
}

function scoreValue(promptId) {
  const parsed = aiReviewState[promptId]?.parsed;
  const score = Number(parsed?.score);
  if (Number.isFinite(score)) return Math.max(0, Math.min(100, Math.round(score)));
  return aiReviewState[promptId]?.status === "success" ? 80 : "--";
}

function scoreRingDegrees(promptId) {
  const value = scoreValue(promptId);
  if (typeof value !== "number") return "0deg";
  return `${Math.round((value / 100) * 360)}deg`;
}

function scoreRating(promptId) {
  const value = scoreValue(promptId);
  if (typeof value !== "number") return "等待综合评估";
  if (value >= 85) return "综合评估优秀";
  if (value >= 70) return "综合评估良好";
  return "综合评估需修改";
}

function buildAiVariables() {
  return {
    title: form.title.trim(),
    content: form.content.trim(),
    type: form.type,
    theme: form.theme,
  };
}

function collectAiReviews() {
  return aiReviewItems.value
    .map((item) => {
      const state = aiReviewState[item.id];
      if (!state || state.status !== "success") return null;
      return {
        prompt_id: item.id,
        name: item.name,
        answer: state.answer,
        parsed: state.parsed,
        parse_error: state.parse_error,
        reviewed_at: new Date().toISOString(),
      };
    })
    .filter(Boolean)
    .slice(-3);
}

function hasAiReviewWarning() {
  return aiReviewItems.value.some((item) => {
    const parsed = aiReviewState[item.id]?.parsed;
    if (!parsed || typeof parsed !== "object") return false;
    if (parsed.pass === false) return true;
    if (parsed.score != null) {
      const score = Number(parsed.score);
      return Number.isFinite(score) && score < 70;
    }
    return false;
  });
}

function confirmAiReviewWarning() {
  return window.confirm(
    "AI 自查提示当前案例可能还需要修改。AI 结果可能误判，不会阻止提交；你可以继续提交专家审核，也可以取消后返回修改。"
  );
}

async function loadAiPrompts() {
  aiPromptLoadError.value = "";
  try {
    const prompts = await listPrompts("workflow");
    const mapped = DEFAULT_AI_REVIEW_ITEMS.map((fallback) => {
      const prompt = prompts.find((item) => item.id === fallback.id);
      return prompt
        ? {
            id: prompt.id,
            name: prompt.name || fallback.name,
            description: prompt.description || fallback.description,
            variables: prompt.variables || fallback.variables,
          }
        : fallback;
    });
    aiReviewItems.value = mapped;
    for (const item of mapped) ensureAiReviewState(item.id);
  } catch (err) {
    aiPromptLoadError.value = err.message || "AI 自查提示词暂不可用";
  }
}

async function runAiReview(promptId) {
  if (!canRunAiReview.value) {
    aiPromptLoadError.value = "请先登录并填写标题、正文、类型和主题后再运行 AI 自查。";
    return;
  }
  const state = ensureAiReviewState(promptId);
  state.status = "loading";
  state.answer = "";
  state.parsed = null;
  state.parse_error = null;
  state.error = "";
  try {
    const data = await runPrompt(promptId, buildAiVariables());
    state.status = "success";
    state.answer = data.answer || "";
    state.parsed = data.parsed || null;
    state.parse_error = data.parse_error || null;
  } catch (err) {
    state.status = "error";
    state.error = err.message || "AI 自查暂不可用";
  }
}

async function runAllAiReviews() {
  if (!canRunAiReview.value || aiRunningAll.value) return;
  aiRunningAll.value = true;
  try {
    for (const item of aiReviewItems.value) {
      await runAiReview(item.id);
    }
  } finally {
    aiRunningAll.value = false;
  }
}

function runHelper() {
  const q = helperInput.value.trim();
  if (!q) return;
  const text = (form.title + " " + form.content).toLowerCase();
  let type = "TYPE_A";
  let theme = "铸魂育人";
  if (text.includes("课程") || text.includes("教学")) type = "TYPE_A";
  if (text.includes("共享") || text.includes("资源")) type = "TYPE_B";
  if (text.includes("实践") || text.includes("活动") || text.includes("社会")) type = "TYPE_C";
  if (text.includes("强国")) theme = "强国建设";
  else if (text.includes("实践") || text.includes("育人")) theme = "实践育人";
  else if (text.includes("数字") || text.includes("技术") || text.includes("网络")) theme = "数字赋能";
  const typeLabel = constants.case_types[type] || type;
  helperResponse.value = `根据当前内容，建议类型为「${typeLabel}」，主题选择「${theme}」。您也可以结合自身判断手动调整。`;
}

onMounted(async () => {
  const user = currentUser();
  form.author = user?.nickname || user?.username || "";
  loadDraft();
  try {
    const data = await fetchCaseConstants();
    if (data) {
      if (data.case_types) constants.case_types = data.case_types;
      if (Array.isArray(data.themes)) constants.themes = data.themes;
      if (data.statuses) constants.statuses = data.statuses;
    }
  } catch {
    // Safe fallbacks already set
  }
  if (isAuthenticated.value) {
    await loadAiPrompts();
  }
});

// Persist form changes locally as the user types
watch(
  () => ({
    title: form.title,
    author: form.author,
    department: form.department,
    content: form.content,
    type: form.type,
    theme: form.theme,
  }),
  () => persistDraft(),
  { deep: true }
);

watch(currentStep, (step) => {
  if (step === 3 && isAuthenticated.value) {
    loadAiPrompts();
  }
});

// Reset scroll to the top of the page whenever the wizard step changes
watch(currentStep, () => {
  nextTick(() => {
    window.scrollTo({ top: 0, behavior: "auto" });
  });
});
</script>

<style scoped>
.create-case-wizard {
  display: flex;
  flex-direction: column;
  min-height: calc(100vh - var(--header-height));
  background: #fff;
}

/* Desktop rail */
.wizard-rail {
  display: none;
  width: 288px;
  flex-shrink: 0;
  background: #fff;
  border-right: 1px solid #eceff3;
}

.rail-header {
  padding: 56px 32px 48px;
  border-bottom: 0;
}

.rail-header-top {
  display: block;
  margin-bottom: 14px;
}

.rail-title {
  font-size: 16px;
  font-weight: 700;
  color: #111827;
  margin-bottom: 18px;
}

.rail-percent {
  font-size: 17px;
  font-weight: 700;
  color: #17c964;
}

.rail-progress-track {
  height: 6px;
  background: #f0f2f4;
  border-radius: 3px;
  overflow: hidden;
  max-width: 212px;
}

.rail-progress-bar {
  height: 100%;
  background: #17c964;
  border-radius: 3px;
  transition: width 0.3s ease;
}

.rail-steps {
  padding: 28px 0 24px;
}

.rail-step {
  display: flex;
  align-items: center;
  gap: 24px;
  min-height: 58px;
  padding: 0 32px;
  position: relative;
  color: #9aa0aa;
}

.rail-step.active {
  background: #fff5f6;
  color: var(--color-brand);
}

.rail-step.active::before {
  content: "";
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 4px;
  background: var(--color-brand);
}

.rail-step.completed {
  color: #6b7280;
}

.rail-step.future {
  color: var(--color-text-muted);
}

.rail-step-left {
  display: flex;
  align-items: center;
  gap: 14px;
}

.step-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  color: currentColor;
}

.step-marker {
  width: 22px;
  height: 22px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  font-size: 12px;
  font-weight: 700;
  border: 2px solid #e0e5ec;
  color: #c8cfd8;
  background: #fff;
}

.rail-step.completed .step-marker {
  background: #fff;
  color: var(--color-brand);
  border-color: var(--color-brand);
}

.rail-step.active .step-marker {
  border-color: #dbe3ec;
  color: #b8c2cf;
}

.rail-step.future .step-marker {
  border-color: #e0e5ec;
  color: #c8cfd8;
}

.step-label {
  font-size: 15px;
  font-weight: 600;
}

.rail-step.active .step-label {
  font-weight: 600;
}

/* Mobile rail */
.wizard-rail-mobile {
  display: block;
  background: var(--color-surface);
  border-bottom: 1px solid var(--color-border);
  padding: 16px;
}

.mobile-progress-header {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  margin-bottom: 8px;
}

.mobile-progress-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text-secondary);
}

.mobile-progress-percent {
  font-size: 15px;
  font-weight: 700;
  color: #16a34a;
}

.mobile-progress-bar-track {
  height: 6px;
  background: #e5e7eb;
  border-radius: 3px;
  overflow: hidden;
  margin-bottom: 10px;
}

.mobile-progress-bar {
  height: 100%;
  background: #16a34a;
  border-radius: 3px;
  transition: width 0.3s ease;
}

.mobile-steps {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 4px;
}

.mobile-step {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  color: var(--color-text-muted);
  flex: 1;
  min-width: 0;
}

.mobile-step.active {
  color: var(--color-brand);
}

.mobile-step.completed {
  color: var(--color-brand);
}

.mobile-step-dot {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  border: 2px solid currentColor;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  font-weight: 700;
  flex-shrink: 0;
}

.mobile-step.completed .mobile-step-dot {
  background: var(--color-brand);
  color: #fff;
  border-color: var(--color-brand);
}

.mobile-step-label {
  font-size: 11px;
  text-align: center;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 100%;
}

/* Main workspace */
.wizard-main {
  flex: 1;
  width: 100%;
  min-width: 0;
  padding: 34px 16px 40px;
  max-width: none;
}

.wizard-breadcrumb {
  font-size: 15px;
  color: #5d6470;
  margin-bottom: 26px;
}

.bc-current {
  color: var(--color-brand);
  font-weight: 600;
}

.bc-chevron {
  margin: 0 6px;
}

.wizard-title {
  margin: 0 0 14px;
  font-size: 32px;
  font-weight: 500;
  color: #111111;
  letter-spacing: 0;
}

.wizard-desc {
  margin: 0 0 42px;
  font-size: 16px;
  color: #606773;
  line-height: 1.8;
}

.wizard-form {
  background: transparent;
  border: 0;
  border-radius: 0;
  padding: 0;
  max-width: 920px;
}

.field {
  margin-bottom: 30px;
}

.field label {
  display: block;
  font-size: 15px;
  font-weight: 600;
  color: #191919;
  margin-bottom: 10px;
}

.required {
  color: var(--color-brand);
  margin-left: 2px;
}

input[type="text"],
select,
textarea {
  width: 100%;
  padding: 14px 16px;
  border: 1px solid #d9dee7;
  border-radius: 0;
  font-family: inherit;
  font-size: 16px;
  color: var(--color-text);
  background: var(--color-surface);
  outline: none;
  transition: border-color 0.15s, box-shadow 0.15s;
}

input[type="text"]:focus,
select:focus,
textarea:focus {
  border-color: var(--color-brand);
  box-shadow: 0 0 0 2px rgba(191, 0, 36, 0.08);
}

input.readonly {
  background: #f3f4f6;
  color: var(--color-text-secondary);
}

textarea {
  min-height: 430px;
  resize: vertical;
  line-height: 1.6;
}

.field-help {
  margin-top: 8px;
  font-size: 13px;
  color: #777e89;
}

.field-error {
  margin-top: 6px;
  font-size: 12px;
  color: var(--color-error-text);
  background: var(--color-error-bg);
  padding: 6px 8px;
  border-radius: 4px;
}

.textarea-meta {
  display: flex;
  justify-content: space-between;
  margin-top: 6px;
  font-size: 12px;
  color: var(--color-text-muted);
}

.row.two-col {
  display: grid;
  grid-template-columns: 1fr;
  gap: 0;
}

.tip-card {
  display: flex;
  flex-direction: column;
  gap: 18px;
  padding: 26px 30px;
  border: 1px solid #edf0f4;
  border-radius: 8px;
  background: #fff;
  box-shadow: 0 2px 8px rgba(17, 24, 39, 0.02);
}

.tip-icon {
  color: var(--color-brand);
  flex-shrink: 0;
}

.tip-title {
  font-size: 17px;
  font-weight: 700;
  color: var(--color-text);
  margin-bottom: 8px;
}

.tip-body {
  min-width: 0;
}

.tip-body ul {
  margin: 0;
  padding-left: 16px;
  font-size: 14px;
  color: var(--color-text-secondary);
  line-height: 1.8;
}

.hint-banner {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 18px 22px;
  background: #fffdf3;
  border: 1px solid #efe6bd;
  border-radius: 0;
  margin-bottom: 34px;
  font-size: 15px;
  color: #3f3530;
}

.hint-icon {
  color: #d4aa20;
  flex-shrink: 0;
}

/* Helper panel */
.helper-panel {
  position: fixed;
  right: 32px;
  bottom: 92px;
  width: min(92vw, 360px);
  background: var(--color-surface);
  border: 1px solid var(--color-border-strong);
  border-radius: 10px;
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.08);
  z-index: 110;
}

.helper-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 14px;
  border-bottom: 1px solid var(--color-border);
  font-size: 13px;
  font-weight: 700;
  color: var(--color-text);
}

.helper-close-btn {
  background: transparent;
  border: 0;
  font-size: 20px;
  line-height: 1;
  color: var(--color-text-muted);
  cursor: pointer;
}

.helper-body {
  padding: 14px;
}

.helper-desc {
  margin: 0 0 10px;
  font-size: 12px;
  color: var(--color-text-secondary);
}

.helper-body input[type="text"] {
  margin-bottom: 10px;
}

.btn-helper {
  width: 100%;
  padding: 10px;
  border: 1px solid var(--color-brand);
  border-radius: 6px;
  background: var(--color-brand);
  color: #fff;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
}

.btn-helper:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.helper-response {
  margin-top: 10px;
  padding: 10px;
  background: #f6f7f9;
  border-radius: 6px;
  font-size: 13px;
  color: var(--color-text);
  line-height: 1.5;
}

.fab-helper {
  position: fixed;
  right: 32px;
  bottom: 32px;
  width: 52px;
  height: 52px;
  border-radius: 8px;
  background: var(--color-brand);
  color: #fff;
  border: 0;
  font-size: 20px;
  cursor: pointer;
  box-shadow: 0 6px 16px rgba(141, 27, 53, 0.25);
  z-index: 105;
}

/* Review step */
.review-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.review-badge {
  display: inline-flex;
  align-items: center;
  padding: 0;
  border-radius: 0;
  background: transparent;
  color: var(--color-brand);
  font-size: 17px;
  font-weight: 700;
}

.review-percent {
  font-size: 16px;
  font-weight: 500;
  color: #4f5662;
}

.review-progress-track {
  height: 6px;
  background: #f4d4d9;
  border-radius: 3px;
  overflow: hidden;
  margin-bottom: 14px;
}

.review-progress-bar {
  height: 100%;
  background: var(--color-brand);
  border-radius: 3px;
}

.review-note {
  font-size: 14px;
  color: #6a7280;
  margin: 0 0 24px;
  line-height: 1.7;
}

.ai-unavailable-banner {
  padding: 12px 14px;
  border: 1px solid #f59e0b;
  border-radius: 6px;
  background: #fffbeb;
  color: #92400e;
  font-size: 13px;
  margin-bottom: 14px;
}

.ai-review-toolbar {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 28px;
}

.ai-toolbar-note {
  font-size: 12px;
  color: var(--color-text-secondary);
  line-height: 1.5;
}

.review-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 28px;
  margin-bottom: 18px;
}

.review-card {
  padding: 34px;
  border: 1px solid #e8ebf0;
  border-radius: 8px;
  background: var(--color-surface);
  box-shadow: 0 3px 12px rgba(17, 24, 39, 0.025);
}

.ai-review-card {
  display: flex;
  flex-direction: column;
  min-height: 238px;
  position: relative;
}

.review-card-top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 18px;
  margin-bottom: 26px;
}

.review-card-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 38px;
  height: 38px;
  color: var(--color-brand);
  flex-shrink: 0;
}

.review-card-copy {
  min-width: 0;
  flex: 1;
}

.ai-status-pill {
  flex-shrink: 0;
  padding: 4px 12px;
  border-radius: 999px;
  background: #f3f4f6;
  color: var(--color-text-secondary);
  font-size: 12px;
  font-weight: 700;
}

.ai-status-pill.loading {
  background: #eff6ff;
  color: #1d4ed8;
}

.ai-status-pill.success {
  background: #dcfce7;
  color: #15803d;
}

.ai-status-pill.warning {
  background: #fff7ed;
  color: #c2410c;
}

.ai-status-pill.error {
  background: #fee2e2;
  color: #b91c1c;
}

.ai-placeholder,
.ai-error,
.ai-result {
  flex: 1;
  margin: 4px 0 14px;
  font-size: 15px;
  line-height: 1.6;
}

.ai-placeholder {
  color: var(--color-text-muted);
}

.ai-error {
  color: #b91c1c;
}

.ai-detail {
  color: var(--color-text);
  margin-bottom: 10px;
}

.ai-score {
  display: inline-flex;
  align-items: center;
  min-height: 26px;
  padding: 3px 8px;
  border-radius: 999px;
  background: var(--color-brand-light);
  color: var(--color-brand);
  font-size: 12px;
  font-weight: 700;
  margin-bottom: 8px;
}

.ai-suggestions {
  margin: 0;
  padding-left: 18px;
  color: var(--color-text-secondary);
}

.ai-answer {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  margin: 0;
  font: inherit;
  color: var(--color-text-secondary);
}

.ai-parse-warning {
  margin-top: 8px;
  color: #92400e;
  font-size: 12px;
}

.ai-run-btn {
  align-self: flex-start;
}

.score-summary-card {
  align-items: center;
  justify-content: center;
  border: 2px solid var(--color-brand);
  text-align: center;
}

.review-card-title {
  font-size: 22px;
  font-weight: 700;
  color: var(--color-text);
  margin-bottom: 14px;
}

.review-card-status {
  font-size: 18px;
  font-weight: 700;
  color: var(--color-text-muted);
  margin-bottom: 6px;
}

.review-card-status.pass {
  color: #16a34a;
}

.review-card-desc {
  font-size: 15px;
  color: var(--color-text-secondary);
  line-height: 1.8;
}

.score-summary {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 14px;
  flex: 1;
  width: 100%;
}

.score-ring {
  --score-deg: 0deg;
  width: 112px;
  height: 112px;
  border-radius: 50%;
  background: conic-gradient(var(--color-brand) var(--score-deg), #f1f3f6 0);
  color: var(--color-brand);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-direction: column;
  position: relative;
  margin: 0 auto;
}

.score-ring::before {
  content: "";
  position: absolute;
  inset: 12px;
  border-radius: 50%;
  background: #fff;
}

.score-ring strong,
.score-ring span {
  position: relative;
}

.score-ring strong {
  font-size: 28px;
  font-weight: 800;
  line-height: 1;
}

.score-ring span {
  margin-top: 5px;
  color: #6b7280;
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 2px;
}

.score-summary-text {
  color: var(--color-brand);
  font-size: 21px;
  font-weight: 700;
}

/* Submit confirmation */
.pass-notice {
  display: flex;
  align-items: center;
  gap: 18px;
  padding: 26px 34px;
  border: 1px solid #efc7ce;
  border-radius: 4px;
  color: #3f3530;
  font-size: 16px;
  font-weight: 600;
  margin-bottom: 32px;
  line-height: 1.7;
}

.pass-icon {
  width: 34px;
  height: 34px;
  border-radius: 50%;
  color: #334155;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.submit-card {
  padding: 32px 42px;
  border: 1px solid #efc7ce;
  border-radius: 0;
  background: var(--color-surface);
}

.submit-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  margin-bottom: 22px;
}

.submit-title-wrap {
  display: flex;
  align-items: center;
  gap: 16px;
  min-width: 0;
}

.submit-title-icon {
  color: var(--color-brand);
  flex-shrink: 0;
}

.submit-card-header h3 {
  margin: 0;
  font-size: 24px;
  font-weight: 700;
  color: var(--color-text);
}

.status-pill {
  padding: 6px 14px;
  border-radius: 999px;
  background: #fff1f2;
  color: var(--color-brand);
  font-size: 13px;
  font-weight: 700;
}

.submit-checklist {
  list-style: none;
  margin: 0 0 26px;
  padding: 0;
}

.submit-checklist li {
  display: flex;
  align-items: flex-start;
  gap: 14px;
  padding: 8px 0;
  font-size: 15px;
  color: #4b5565;
  border-bottom: 0;
  line-height: 1.6;
}

.submit-checklist li:last-child {
  border-bottom: 0;
}

.submit-checklist li.ok {
  color: var(--color-text);
}

.submit-checklist .check {
  width: 20px;
  height: 20px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  flex-shrink: 0;
  border: 2px solid var(--color-border-strong);
  color: var(--color-text-muted);
}

.submit-checklist li.ok .check {
  background: var(--color-brand);
  border-color: var(--color-brand);
  color: #fff;
}

.btn-submit-final {
  width: auto;
  min-width: 228px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 16px 28px;
  border: 0;
  border-radius: 4px;
  background: var(--color-brand);
  color: #fff;
  font-size: 16px;
  font-weight: 700;
  cursor: pointer;
}

.btn-submit-final:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

/* Actions */
.wizard-actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 24px;
  margin-top: 54px;
  padding-top: 0;
  border-top: 0;
}

.btn-primary,
.btn-secondary {
  min-width: 150px;
  padding: 14px 26px;
  border-radius: 4px;
  font-size: 16px;
  font-weight: 600;
  cursor: pointer;
  transition: opacity 0.15s, transform 0.05s;
}

.btn-primary {
  border: 0;
  background: var(--color-brand);
  color: #fff;
}

.btn-secondary {
  border: 1px solid #9da3ad;
  background: var(--color-surface);
  color: #4b5565;
}

.btn-primary:disabled,
.btn-secondary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.arrow {
  margin-left: 2px;
}

.login-required-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 48px 24px;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 8px;
  text-align: center;
}

.login-required-card h3 {
  margin: 0;
  font-size: 18px;
  font-weight: 700;
  color: var(--color-text);
}

.login-required-card p {
  margin: 0;
  font-size: 14px;
  color: var(--color-text-secondary);
  max-width: 360px;
}

.login-required-icon {
  font-size: 40px;
  line-height: 1;
}

/* Responsive desktop */
@media (min-width: 860px) {
  .create-case-wizard {
    flex-direction: row;
  }

  .wizard-rail {
    display: block;
  }

  .wizard-rail-mobile {
    display: none;
  }

  .wizard-main {
    padding: 72px 72px 72px;
  }

  .wizard-title {
    font-size: 42px;
  }

  .wizard-form {
    padding: 0;
    max-width: min(980px, calc(100vw - 430px));
  }

  .tip-card {
    flex-direction: row;
  }

  .row.two-col {
    grid-template-columns: 1fr 1fr;
    gap: 56px;
  }

  .review-grid {
    grid-template-columns: 1fr 1fr;
  }
}

@media (min-width: 1180px) {
  .wizard-rail {
    width: 336px;
  }

  .rail-step {
    min-height: 64px;
    padding: 0 38px;
  }

  .wizard-main {
    padding-left: 84px;
    padding-right: 84px;
  }

  .wizard-form {
    max-width: 1040px;
  }

  .review-grid {
    max-width: 1020px;
  }
}

@media (max-width: 859px) {
  .wizard-main {
    padding: 24px 16px 40px;
  }

  .wizard-title {
    font-size: 28px;
  }

  .wizard-desc {
    font-size: 14px;
    margin-bottom: 26px;
  }

  .wizard-form {
    max-width: none;
  }

  textarea {
    min-height: 260px;
  }

  .review-card {
    padding: 22px;
  }

  .review-card-top,
  .submit-card-header {
    flex-wrap: wrap;
  }

  .score-summary-card {
    min-height: 260px;
  }

  .pass-notice,
  .submit-card {
    padding: 22px;
  }

  .btn-submit-final,
  .btn-primary,
  .btn-secondary {
    width: 100%;
  }

  .wizard-actions {
    gap: 12px;
    margin-top: 32px;
  }
}
</style>
