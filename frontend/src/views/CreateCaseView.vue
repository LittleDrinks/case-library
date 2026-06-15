<template>
  <div class="create-case-wizard">
    <CreateWizardRail :steps="steps" :current-step="currentStep" :progress-percent="progressPercent" />

    <main :class="['wizard-main', { 'wizard-main-wide': currentStep === 1 || currentStep === 3 }]">
      <div class="wizard-breadcrumb">
        <span class="bc-parent">{{ isEditingExisting ? "修改案例" : "创建案例" }}</span>
        <span class="bc-chevron" aria-hidden="true">›</span>
        <span class="bc-current">{{ steps[currentStep].label }}</span>
      </div>

      <h1 class="wizard-title">{{ stepMeta.title }}</h1>
      <p class="wizard-desc">{{ stepMeta.desc }}</p>
      <div v-if="isEditingExisting" class="edit-context-bar">
        <div>
          <strong>正在修改已保存案例</strong>
          <span>保存草稿会生成新的历史版本，可在“我的提交”中查看版本记录。</span>
        </div>
        <button type="button" class="context-link" @click="goToSubmissions">返回我的提交</button>
      </div>

      <LoginRequiredCard v-if="!isAuthenticated" />

      <div v-else class="wizard-form">
        <CreateBasicStep
          v-if="currentStep === 0"
          :form="form"
          :errors="errors"
          :display-author="displayAuthor"
          @touch="touch"
        />
        <CreateContentStep
          v-if="currentStep === 1"
          :form="form"
          :errors="errors"
          :word-count="wordCount"
          :reading-time="readingTime"
          @touch="touch"
        />
        <CreateClassifyStep
          v-if="currentStep === 2"
          :form="form"
          :errors="errors"
          :constants="constants"
          @touch="touch"
        />
        <CreateReviewStep
          v-if="currentStep === 3"
          :ai-review-items="aiReviewItems"
          :ai-review-state="aiReviewState"
          :ai-prompt-load-error="aiPromptLoadError"
          :ai-running-all="aiRunningAll"
          :can-run-ai-review="canRunAiReview"
          :ai-review-progress="aiReviewProgress"
          @run-all="runAllAiReviews"
          @run-item="runAiReview"
        />
        <CreateSubmitStep
          v-if="currentStep === 4"
          :form="form"
          :constants="constants"
          :can-submit="canSubmit"
          :submitting="submitting"
          :content-summary="contentSummary"
          @submit="handleFormalSubmit"
        />

        <CreateWizardActions
          :current-step="currentStep"
          :saving="saving"
          @prev="prevStep"
          @save="saveDraft"
          @next="nextStep"
          @edit="currentStep = 1"
        />
      </div>
    </main>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, nextTick } from "vue";
import { currentUser } from "../api/auth.js";
import { fetchCaseDetail } from "../api/cases.js";
import { notify } from "../utils/toast.js";
import CreateWizardRail from "../components/create/CreateWizardRail.vue";
import CreateWizardActions from "../components/create/CreateWizardActions.vue";
import LoginRequiredCard from "../components/create/LoginRequiredCard.vue";
import CreateBasicStep from "../components/create/CreateBasicStep.vue";
import CreateContentStep from "../components/create/CreateContentStep.vue";
import CreateClassifyStep from "../components/create/CreateClassifyStep.vue";
import CreateReviewStep from "../components/create/CreateReviewStep.vue";
import CreateSubmitStep from "../components/create/CreateSubmitStep.vue";
import { useCaseDraft } from "../composables/useCaseDraft.js";
import { useCaseForm } from "../composables/useCaseForm.js";
import { useAiReview } from "../composables/useAiReview.js";
import { useCaseSubmission } from "../composables/useCaseSubmission.js";

const steps = [
  { id: "basic", label: "基本信息" },
  { id: "content", label: "案例内容" },
  { id: "classify", label: "分类选择" },
  { id: "review", label: "AI 审核" },
  { id: "confirm", label: "提交确认" },
];
const currentStep = ref(0);

const {
  form, constants, isAuthenticated, displayAuthor,
  wordCount, readingTime, contentSummary, errors, canSubmit,
  touch, validateStep, resetForm: resetCaseForm, loadConstants,
} = useCaseForm();

const caseId = ref(null);
const latestReviewVersionId = ref(null);
const { persistDraft, loadDraft, clearDraft } = useCaseDraft({
  form, caseId, latestReviewVersionId, getCurrentUser: currentUser,
});

const {
  aiReviewItems, aiReviewState, aiPromptLoadError, aiRunningAll,
  canRunAiReview, aiReviewProgress, resetAllAiReviews,
  loadAiPrompts, runAiReview, runAllAiReviews, collectAiReviews,
  hasAiReviewWarning, confirmAiReviewWarning,
} = useAiReview({
  form, isAuthenticated, caseId, latestReviewVersionId, persistDraft, displayAuthor,
});

const { saving, submitting, saveDraft, submitCase } = useCaseSubmission({
  form, caseId, latestReviewVersionId, displayAuthor, isAuthenticated,
  collectAiReviews, persistDraft, clearDraft, resetCaseForm, resetAllAiReviews,
});

const progressPercent = computed(() => Math.round(((currentStep.value + 1) / steps.length) * 100));
const isEditingExisting = computed(() => Boolean(caseId.value));
const stepMeta = computed(() => {
  const metas = [
    { title: "填写案例基本信息", desc: "请准确填写案例的标题、作者及所属单位信息。这些信息将作为案例在库中检索、引用及展示的核心标识。" },
    { title: "撰写案例内容", desc: "请围绕教学实践，系统撰写案例正文。内容应包含案例背景、教学过程、思政元素融入方式及教学反思等核心模块，确保案例具有示范性与可推广价值。" },
    { title: "选择分类", desc: "请为案例选择合适的案例类型与思政主题。准确的分类有助于案例被精准检索和推荐，提升案例在思政教学中的传播价值与实践影响力。" },
    { title: "AI 智能内容审核", desc: "通过多维学术模型评估您的案例内容，帮助您在提交前发现结构、分类和表达方面的改进点。" },
    { title: "提交确认", desc: "请仔细核对以下信息，确认无误后提交您的案例。提交后将进入人工审核流程，审核结果将通过站内信通知您。" },
  ];
  return metas[currentStep.value];
});

function nextStep() {
  if (!validateStep(currentStep.value)) return;
  if (currentStep.value === 3 && hasAiReviewWarning() && !confirmAiReviewWarning()) return;
  if (currentStep.value < steps.length - 1) currentStep.value += 1;
}

function prevStep() {
  if (currentStep.value > 0) currentStep.value -= 1;
}

async function handleFormalSubmit() {
  if (await submitCase()) {
    currentStep.value = 0;
    window.location.hash = "submissions";
  }
}

function applyCaseToForm(data) {
  form.title = data.title || "";
  form.author = data.author || currentUser()?.nickname || currentUser()?.username || "";
  form.department = data.department || "";
  form.content = data.content || "";
  form.source_material = data.source_material || "";
  form.type = data.type || "";
  form.theme = data.theme || "";
}

async function loadCaseForEdit(draftId) {
  try {
    const res = await fetchCaseDetail(draftId, false);
    if (!res?.success || !res.data) {
      throw new Error(res?.message || "案例加载失败");
    }
    applyCaseToForm(res.data);
    caseId.value = res.data.id || draftId;
    latestReviewVersionId.value = null;
    currentStep.value = 1;
    persistDraft();
  } catch (err) {
    notify(err.message || "加载待修改案例失败", "error");
  }
}

function goToSubmissions() {
  window.location.hash = "submissions";
}

onMounted(async () => {
  const user = currentUser();
  form.author = user?.nickname || user?.username || "";
  const hash = window.location.hash.replace("#", "");
  const [viewId, query = ""] = hash.split("?");
  const draftId = viewId === "create" ? new URLSearchParams(query).get("draft") : "";
  if (viewId === "create") {
    if (draftId) {
      clearDraft();
      caseId.value = draftId;
      latestReviewVersionId.value = null;
    } else {
      caseId.value = null;
      latestReviewVersionId.value = null;
      loadDraft();
    }
  } else {
    loadDraft();
  }
  await loadConstants();
  if (draftId) await loadCaseForEdit(draftId);
  if (isAuthenticated.value) await loadAiPrompts();
});

watch(
  () => ({
    title: form.title, author: form.author, department: form.department,
    content: form.content, source_material: form.source_material, type: form.type, theme: form.theme,
  }),
  () => persistDraft(),
  { deep: true }
);

watch(currentStep, (step) => {
  if (step === 3 && isAuthenticated.value) loadAiPrompts();
});

watch(currentStep, () => {
  nextTick(() => {
    const wizardTop = document.querySelector(".create-case-wizard")?.getBoundingClientRect().top || 0;
    const headerHeight = parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--header-height")) || 0;
    window.scrollTo({ top: Math.max(0, window.scrollY + wizardTop - headerHeight), behavior: "auto" });
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
.wizard-main {
  flex: 1;
  width: 100%;
  min-width: 0;
  padding: 20px 16px;
  max-width: 100%;
}
.wizard-breadcrumb {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  font-weight: 500;
  color: var(--color-text-secondary);
  margin-bottom: 24px;
}
.bc-current {
  color: var(--color-brand);
  font-weight: 500;
}
.bc-chevron {
  color: #cccccc;
}
.wizard-title {
  margin: 0 0 8px;
  font-family: var(--font-display);
  font-size: 22px;
  font-weight: 700;
  color: var(--color-text);
  letter-spacing: 1px;
}
.wizard-desc {
  max-width: 100%;
  margin: 0 0 32px;
  font-size: 13px;
  color: var(--color-text-secondary);
  line-height: 1.7;
}
.edit-context-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin: -14px 0 28px;
  padding: 14px 16px;
  border: 1px solid rgba(141, 27, 53, 0.18);
  border-radius: 8px;
  background: var(--color-brand-light);
  color: var(--color-text);
}
.edit-context-bar strong,
.edit-context-bar span {
  display: block;
}
.edit-context-bar strong {
  margin-bottom: 2px;
  font-size: 14px;
}
.edit-context-bar span {
  font-size: 12px;
  color: var(--color-text-secondary);
}
.context-link {
  border: 1px solid var(--color-brand);
  border-radius: 6px;
  background: var(--color-surface);
  color: var(--color-brand);
  padding: 8px 12px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  white-space: nowrap;
}
.wizard-form {
  background: transparent;
  border: 0;
  border-radius: 0;
  padding: 0;
}
@media (min-width: 860px) {
  .create-case-wizard {
    flex-direction: row;
  }
  .wizard-main {
    padding: 32px 48px 48px;
    max-width: none;
  }
  .wizard-main-wide {
    max-width: none;
  }
  .wizard-title {
    font-size: 28px;
    line-height: 1.25;
  }
}

@media (max-width: 640px) {
  .edit-context-bar {
    flex-direction: column;
    align-items: stretch;
  }
}

@media (min-width: 1280px) {
  .wizard-main {
    padding-left: 48px;
  }
}
</style>
