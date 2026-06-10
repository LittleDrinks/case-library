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
        <div class="login-required-icon" aria-hidden="true"></div>
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
            <div class="tip-icon" aria-hidden="true"></div>
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

          <div class="field">
            <label for="ccf-source">来源材料</label>
            <textarea
              id="ccf-source"
              v-model="form.source_material"
              rows="8"
              placeholder="可粘贴新闻链接、公众号正文、活动记录、访谈纪要或其他支撑材料。"
            ></textarea>
            <div class="field-help">来源材料会随版本快照保存，公开案例仅展示正文和来源材料，不展示审核批注。</div>
          </div>
        </template>

        <!-- Step 3: 分类选择 -->
        <template v-if="currentStep === 2">
          <div class="hint-banner">
            <span class="hint-icon" aria-hidden="true"></span>
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
            AI
          </button>
        </template>

        <!-- Step 4: AI 审核 -->
        <template v-if="currentStep === 3">
          <div class="review-header">
            <span class="review-badge">AI 自查</span>
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

          <div class="review-grid">
            <div v-for="item in aiReviewItems" :key="item.id" class="review-card ai-review-card">
              <div class="review-card-top">
                <div>
                  <div class="review-card-title">{{ item.name }}</div>
                  <div class="review-card-desc">{{ item.description }}</div>
                </div>
                <span class="ai-status-pill" :class="aiReviewState[item.id].status">
                  {{ aiStatusLabel(aiReviewState[item.id].status) }}
                </span>
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
                  <ul
                    v-if="Array.isArray(aiReviewState[item.id].comments) && aiReviewState[item.id].comments.length && !hasAnnotationPreview(aiReviewState[item.id])"
                    class="ai-suggestions"
                  >
                    <li v-for="comment in aiReviewState[item.id].comments" :key="comment.id || comment.message">
                      {{ comment.paragraph_id }}：{{ comment.message }}
                    </li>
                  </ul>
                  <div
                    v-if="hasAnnotationPreview(aiReviewState[item.id])"
                    class="ai-annotation-preview"
                  >
                    <div class="annotation-copy">
                      <strong>版本正文</strong>
                      <p
                        v-for="paragraph in aiReviewState[item.id].version.paragraphs"
                        :key="paragraph.paragraph_id"
                        :class="{ highlighted: commentsForParagraph(aiReviewState[item.id], paragraph.paragraph_id).length }"
                      >
                        <span>{{ paragraph.paragraph_id }}</span>
                        {{ paragraph.text }}
                      </p>
                    </div>
                    <aside class="annotation-comments" aria-label="AI 段落批注">
                      <strong>AI 批注</strong>
                      <div
                        v-for="comment in aiReviewState[item.id].comments"
                        :key="comment.id || `${comment.paragraph_id}-${comment.message}`"
                        class="annotation-comment"
                      >
                        <strong>{{ comment.paragraph_id }}</strong>
                        <p>{{ comment.message }}</p>
                        <small v-if="comment.suggestion">{{ comment.suggestion }}</small>
                      </div>
                    </aside>
                  </div>
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
            <span class="pass-icon" aria-hidden="true"></span>
            <span>提交后案例将进入专家人工审核流程，请耐心等待。</span>
          </div>

          <div class="submit-card">
            <div class="submit-card-header">
              <h3>提交至专家审核</h3>
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
import { listPrompts, runParagraphReview } from "../api/ai.js";
import { notify } from "../utils/toast.js";

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
  source_material: "",
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
    needs_revision: "退回修改",
  },
});

const showHelper = ref(false);
const helperInput = ref("");
const helperResponse = ref("");
const aiPromptLoadError = ref("");
const aiRunningAll = ref(false);
const latestReviewVersionId = ref(null);

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
        comments: [],
        version: null,
      },
    ])
  )
);

const displayAuthor = computed(() => {
  const user = currentUser();
  return user?.nickname || user?.username || form.author || "";
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
    source_material: form.source_material.trim(),
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
    notify("请先登录后再保存草稿", "error");
    return;
  }
  saving.value = true;
  try {
    if (caseId.value) {
      const payload = {
        title: form.title.trim(),
        content: form.content.trim(),
        source_material: form.source_material.trim(),
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
    notify("草稿已保存", "success");
  } catch (err) {
    notify(err.message || "保存草稿失败，请稍后重试", "error");
  } finally {
    saving.value = false;
  }
}

async function handleFormalSubmit() {
  if (!canSubmit.value) {
    notify("请完善所有必填项后再提交", "error");
    return;
  }
  if (!isAuthenticated.value) {
    notify("请先登录后再提交案例", "error");
    return;
  }
  submitting.value = true;
  try {
    if (caseId.value) {
      // Update existing draft with latest form data before submitting
      const payload = {
        title: form.title.trim(),
        content: form.content.trim(),
        source_material: form.source_material.trim(),
        author: displayAuthor.value,
        department: form.department.trim(),
        type: form.type,
        theme: form.theme,
        change_reason: "提交前更新",
      };
      appendAiReviewsPayload(payload);
      await updateCase(caseId.value, payload);
      await submitCaseById(caseId.value, latestReviewVersionId.value);
    } else {
      const res = await createCase(buildPayload("draft"));
      if (res && res.case_id) {
        caseId.value = res.case_id;
        await submitCaseById(caseId.value, latestReviewVersionId.value);
      }
    }
    clearDraft();
    notify("案例提交成功，请等待专家审核", "success");
    resetForm();
    currentStep.value = 0;
  } catch (err) {
    notify(err.message || "提交失败，请稍后重试", "error");
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
        source_material: form.source_material,
        type: form.type,
        theme: form.theme,
      },
      caseId: caseId.value,
      latestReviewVersionId: latestReviewVersionId.value,
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
    if (saved && saved.latestReviewVersionId) {
      latestReviewVersionId.value = saved.latestReviewVersionId;
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
  form.source_material = "";
  form.type = "";
  form.theme = "";
  caseId.value = null;
  latestReviewVersionId.value = null;
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
      comments: [],
      version: null,
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
  state.comments = [];
  state.version = null;
}

function commentsForParagraph(state, paragraphId) {
  return (state.comments || []).filter((comment) => comment.paragraph_id === paragraphId);
}

function hasAnnotationPreview(state) {
  return Boolean(state?.version?.paragraphs?.length && state?.comments?.length);
}

function aiStatusLabel(status) {
  if (status === "loading") return "运行中";
  if (status === "success") return "已完成";
  if (status === "error") return "不可用";
  return "待运行";
}

function buildAiVariables() {
  return {
    title: form.title.trim(),
    content: form.content.trim(),
    source_material: form.source_material.trim(),
    type: form.type,
    theme: form.theme,
  };
}

async function ensureDraftCase() {
  const payload = buildPayload("draft");
  if (caseId.value) {
    await updateCase(caseId.value, {
      ...payload,
      author: displayAuthor.value,
      change_reason: "AI 审核前更新",
    });
    return caseId.value;
  }
  const res = await createCase(payload);
  if (!res || !res.case_id) {
    throw new Error("保存草稿失败，无法创建 AI 审核版本");
  }
  caseId.value = res.case_id;
  persistDraft();
  return caseId.value;
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
  notify(
    "AI 自查提示当前案例可能还需要修改；结果仅供参考，不会阻止提交专家审核。",
    "info"
  );
  return true;
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
  state.comments = [];
  state.version = null;
  try {
    const activeCaseId = await ensureDraftCase();
    const data = await runParagraphReview(activeCaseId);
    const result = data?.data || {};
    const version = result.version || {};
    latestReviewVersionId.value = version.id || null;
    state.status = "success";
    state.comments = result.comments || [];
    state.version = version || null;
    state.answer = state.comments.map((comment) => comment.message).join("\n") || "AI 未返回段落批注。";
    const summarySuggestions = Array.from(new Set(result.summary?.suggested_next_steps || []));
    state.parsed = {
      detail: `已生成 v${version.version_number || ""} 只读审核版本，包含 ${state.comments.length} 条段落批注。`,
      suggestions: hasAnnotationPreview(state) ? summarySuggestions : summarySuggestions.concat(
        state.comments.map((comment) => comment.suggestion).filter(Boolean)
      ),
    };
    state.parse_error = null;
    persistDraft();
  } catch (err) {
    state.status = "error";
    state.error = err.data?.detail || err.message || "AI 自查暂不可用";
  }
}

async function runAllAiReviews() {
  if (!canRunAiReview.value || aiRunningAll.value) return;
  aiRunningAll.value = true;
  try {
    await runAiReview(aiReviewItems.value[0]?.id || DEFAULT_AI_REVIEW_ITEMS[0].id);
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
    source_material: form.source_material,
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
    const wizardTop = document.querySelector(".create-case-wizard")?.getBoundingClientRect().top || 0;
    const headerHeight = parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--header-height")) || 0;
    window.scrollTo({
      top: Math.max(0, window.scrollY + wizardTop - headerHeight),
      behavior: "auto",
    });
  });
});
</script>

<style scoped>
.create-case-wizard {
  display: flex;
  flex-direction: column;
  min-height: calc(100vh - var(--header-height));
  background: var(--color-bg);
}

/* Desktop rail */
.wizard-rail {
  display: none;
  width: 280px;
  flex-shrink: 0;
  background: var(--color-surface);
  border-right: 1px solid var(--color-border);
}

.rail-header {
  padding: 24px;
  border-bottom: 1px solid var(--color-border);
}

.rail-header-top {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  margin-bottom: 12px;
}

.rail-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text-secondary);
}

.rail-percent {
  font-size: 20px;
  font-weight: 700;
  color: #16a34a;
}

.rail-progress-track {
  height: 6px;
  background: #e5e7eb;
  border-radius: 3px;
  overflow: hidden;
}

.rail-progress-bar {
  height: 100%;
  background: #16a34a;
  border-radius: 3px;
  transition: width 0.3s ease;
}

.rail-steps {
  padding: 8px 0 24px;
}

.rail-step {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 20px;
  position: relative;
  color: var(--color-text-secondary);
}

.rail-step.active {
  background: var(--color-brand-light);
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
  border-radius: 0 2px 2px 0;
}

.rail-step.completed {
  color: var(--color-text);
}

.rail-step.future {
  color: var(--color-text-muted);
}

.rail-step-left {
  display: flex;
  align-items: center;
  gap: 10px;
}

.step-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
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
  border: 2px solid currentColor;
}

.rail-step.completed .step-marker {
  background: var(--color-brand);
  color: #fff;
  border-color: var(--color-brand);
}

.rail-step.future .step-marker {
  border-color: var(--color-text-muted);
  color: var(--color-text-muted);
}

.step-label {
  font-size: 14px;
  font-weight: 500;
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
  padding: 24px 16px 40px;
  max-width: 960px;
}

.wizard-breadcrumb {
  font-size: 13px;
  color: var(--color-text-muted);
  margin-bottom: 12px;
}

.bc-current {
  color: var(--color-brand);
  font-weight: 600;
}

.bc-chevron {
  margin: 0 6px;
}

.wizard-title {
  margin: 0 0 8px;
  font-size: 24px;
  font-weight: 700;
  color: var(--color-text);
}

.wizard-desc {
  margin: 0 0 24px;
  font-size: 14px;
  color: var(--color-text-secondary);
  line-height: 1.6;
}

.wizard-form {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 8px;
  padding: 20px;
}

.field {
  margin-bottom: 18px;
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

input.readonly {
  background: #f3f4f6;
  color: var(--color-text-secondary);
}

textarea {
  min-height: 240px;
  resize: vertical;
  line-height: 1.6;
}

.field-help {
  margin-top: 4px;
  font-size: 12px;
  color: var(--color-text-muted);
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
  gap: 12px;
  padding: 14px;
  border: 1px dashed var(--color-border-strong);
  border-radius: 6px;
  background: #fafafa;
}

.tip-icon {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: var(--color-brand-light);
  color: var(--color-brand);
  position: relative;
  flex-shrink: 0;
}

.tip-icon::before {
  content: '';
  position: absolute;
  left: 10px;
  top: 5px;
  width: 2px;
  height: 12px;
  background: currentColor;
  border-radius: 1px;
}

.tip-icon::after {
  content: '';
  position: absolute;
  left: 5px;
  top: 10px;
  width: 12px;
  height: 2px;
  background: currentColor;
  border-radius: 1px;
}

.tip-title {
  font-size: 13px;
  font-weight: 700;
  color: var(--color-text);
  margin-bottom: 6px;
}

.tip-body {
  min-width: 0;
}

.tip-body ul {
  margin: 0;
  padding-left: 16px;
  font-size: 13px;
  color: var(--color-text-secondary);
  line-height: 1.7;
}

.hint-banner {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 14px;
  background: #fefce8;
  border: 1px solid #fde047;
  border-radius: 6px;
  margin-bottom: 18px;
  font-size: 13px;
  color: #713f12;
}

.hint-icon {
  width: 18px;
  height: 18px;
  border-radius: 50%;
  border: 2px solid currentColor;
  position: relative;
  flex-shrink: 0;
}

.hint-icon::before,
.hint-icon::after {
  content: '';
  position: absolute;
  background: currentColor;
  border-radius: 1px;
}

.hint-icon::before {
  left: 7px;
  top: 3px;
  width: 2px;
  height: 8px;
}

.hint-icon::after {
  left: 7px;
  top: 12px;
  width: 2px;
  height: 2px;
}

/* Helper panel */
.helper-panel {
  position: fixed;
  right: 16px;
  bottom: 80px;
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
  right: 16px;
  bottom: 24px;
  width: 48px;
  height: 48px;
  border-radius: 8px;
  background: var(--color-brand);
  color: #fff;
  border: 0;
  font-size: 20px;
  cursor: pointer;
  box-shadow: 0 6px 16px rgba(141, 27, 53, 0.25);
  z-index: 105;
}

@media (max-width: 859px) {
  .fab-helper {
    position: static;
    display: flex;
    align-items: center;
    justify-content: center;
    margin: 12px 0 0 auto;
    width: 72px;
    height: 44px;
    font-size: 16px;
    border-radius: 7px;
  }
}

/* Review step */
.review-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}

.review-badge {
  display: inline-flex;
  align-items: center;
  padding: 4px 10px;
  border-radius: 4px;
  background: var(--color-error-bg);
  color: var(--color-brand);
  font-size: 12px;
  font-weight: 700;
}

.review-percent {
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text-secondary);
}

.review-progress-track {
  height: 8px;
  background: #fee2e2;
  border-radius: 4px;
  overflow: hidden;
  margin-bottom: 10px;
}

.review-progress-bar {
  height: 100%;
  background: var(--color-brand);
  border-radius: 4px;
}

.review-note {
  font-size: 13px;
  color: var(--color-text-secondary);
  margin: 0 0 18px;
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
  gap: 10px;
  margin-bottom: 16px;
}

.ai-toolbar-note {
  font-size: 12px;
  color: var(--color-text-secondary);
  line-height: 1.5;
}

.review-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 12px;
  margin-bottom: 8px;
}

.review-card {
  padding: 16px;
  border: 1px solid var(--color-border);
  border-radius: 6px;
  background: var(--color-surface);
}

.ai-review-card {
  display: flex;
  flex-direction: column;
  min-height: 210px;
}

.review-card-top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}

.ai-status-pill {
  flex-shrink: 0;
  padding: 4px 8px;
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

.ai-status-pill.error {
  background: #fee2e2;
  color: #b91c1c;
}

.ai-placeholder,
.ai-error,
.ai-result {
  flex: 1;
  margin: 4px 0 14px;
  font-size: 13px;
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
  margin-bottom: 8px;
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

.ai-annotation-preview {
  display: grid;
  grid-template-columns: 1fr;
  gap: 10px;
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid var(--color-border);
}

.annotation-copy,
.annotation-comments {
  display: grid;
  gap: 8px;
  min-width: 0;
  align-content: start;
}

.annotation-copy > strong,
.annotation-comments > strong {
  font-size: 12px;
  color: var(--color-text-muted);
  letter-spacing: 0;
}

.annotation-copy p {
  margin: 0;
  padding: 9px 10px;
  border: 1px solid var(--color-border);
  border-radius: 6px;
  color: var(--color-text-secondary);
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
}

.annotation-copy p.highlighted {
  border-color: rgba(141, 27, 53, 0.35);
  background: var(--color-brand-light);
  color: var(--color-text);
}

.annotation-copy span {
  display: inline-flex;
  margin-right: 6px;
  font-weight: 700;
  color: var(--color-brand);
}

.annotation-comment {
  padding: 9px 10px;
  border: 1px solid rgba(141, 27, 53, 0.22);
  border-left: 3px solid var(--color-brand);
  border-radius: 6px;
  background: #fff;
  box-shadow: 0 8px 20px rgba(141, 27, 53, 0.06);
}

.annotation-comment > strong {
  display: block;
  margin-bottom: 4px;
  color: var(--color-brand);
}

.annotation-comment p,
.annotation-comment small {
  display: block;
  margin: 0;
  color: var(--color-text-secondary);
  line-height: 1.6;
  word-break: break-word;
}

.annotation-comment small {
  margin-top: 4px;
  color: var(--color-text-muted);
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

.score-card {
  border-color: var(--color-brand);
  background: var(--color-brand-light);
}

.review-card-title {
  font-size: 13px;
  font-weight: 700;
  color: var(--color-text);
  margin-bottom: 8px;
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
  font-size: 12px;
  color: var(--color-text-secondary);
  line-height: 1.5;
}

.score-circle {
  width: 56px;
  height: 56px;
  border-radius: 50%;
  background: var(--color-brand);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
  font-weight: 800;
  margin-bottom: 8px;
}

/* Submit confirmation */
.pass-notice {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 14px;
  border: 1px solid var(--color-brand);
  border-radius: 6px;
  color: var(--color-brand);
  font-size: 14px;
  font-weight: 600;
  margin-bottom: 18px;
}

.pass-icon {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: var(--color-brand);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  flex-shrink: 0;
}

.pass-icon::before {
  content: '';
  width: 10px;
  height: 6px;
  border-left: 2px solid #fff;
  border-bottom: 2px solid #fff;
  transform: rotate(-45deg) translateY(-1px);
}

.submit-card {
  padding: 20px;
  border: 1px solid var(--color-border);
  border-radius: 8px;
  background: var(--color-surface);
}

.submit-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 14px;
}

.submit-card-header h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 700;
  color: var(--color-text);
}

.status-pill {
  padding: 4px 10px;
  border-radius: 999px;
  background: #fef3c7;
  color: #92400e;
  font-size: 12px;
  font-weight: 700;
}

.submit-checklist {
  list-style: none;
  margin: 0 0 20px;
  padding: 0;
}

.submit-checklist li {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 8px 0;
  font-size: 13px;
  color: var(--color-text-secondary);
  border-bottom: 1px solid var(--color-border);
}

.submit-checklist li:last-child {
  border-bottom: 0;
}

.submit-checklist li.ok {
  color: var(--color-text);
}

.submit-checklist .check {
  width: 18px;
  height: 18px;
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
  width: 100%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 12px 20px;
  border: 0;
  border-radius: 6px;
  background: var(--color-brand);
  color: #fff;
  font-size: 15px;
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
  gap: 10px;
  margin-top: 24px;
  padding-top: 16px;
  border-top: 1px solid var(--color-border);
}

.btn-primary,
.btn-secondary {
  padding: 10px 18px;
  border-radius: 6px;
  font-size: 14px;
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
  border: 1px solid var(--color-border-strong);
  background: var(--color-surface);
  color: var(--color-text-secondary);
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
    padding: 32px 40px 48px;
  }

  .wizard-title {
    font-size: 28px;
  }

  .wizard-form {
    padding: 28px;
  }

  .tip-card {
    flex-direction: row;
  }

  .row.two-col {
    grid-template-columns: 1fr 1fr;
    gap: 16px;
  }

  .review-grid {
    grid-template-columns: 1fr 1fr;
  }

  .ai-annotation-preview {
    grid-template-columns: minmax(0, 1fr) minmax(220px, 0.65fr);
  }
}
</style>
