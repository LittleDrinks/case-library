import { reactive, computed } from "vue";
import { currentUser, isLoggedIn } from "../api/auth.js";
import { fetchCaseConstants } from "../api/cases.js";

const DEFAULT_CASE_TYPES = {
  TYPE_A: "思政课教学案例",
  TYPE_B: "课程思政共享资源案例",
  TYPE_C: "实践育人案例",
};

const DEFAULT_THEMES = ["强国建设", "实践育人", "数字赋能", "铸魂育人"];

const DEFAULT_STATUSES = {
  draft: "草稿",
  pending_review: "待审核",
  approved: "已通过",
  needs_revision: "退回修改",
};

/**
 * 案例创建表单的集中状态与校验
 *
 * 提供表单字段、校验错误、派生统计和工具函数；持久化与后端草稿身份
 * 由调用方通过 useCaseDraft 管理。
 */
export function useCaseForm() {
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
    case_types: { ...DEFAULT_CASE_TYPES },
    themes: [...DEFAULT_THEMES],
    statuses: { ...DEFAULT_STATUSES },
  });

  const isAuthenticated = computed(() => isLoggedIn());

  const displayAuthor = computed(() => {
    const user = currentUser();
    return user?.nickname || user?.username || form.author || "";
  });

  const wordCount = computed(() => {
    const text = form.content || "";
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

  const errors = computed(() => {
    const e = {};
    if (touched.title && !form.title.trim()) e.title = "请输入案例标题";
    if (touched.department && !form.department.trim()) e.department = "请输入所属部门/学院";
    if (touched.content && !form.content.trim()) e.content = "请输入案例正文";
    if (touched.type && !form.type) e.type = "请选择案例类型";
    if (touched.theme && !form.theme) e.theme = "请选择案例主题";
    return e;
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

  function resetForm() {
    form.title = "";
    form.author = "";
    form.department = "";
    form.content = "";
    form.source_material = "";
    form.type = "";
    form.theme = "";

    touched.title = false;
    touched.department = false;
    touched.content = false;
    touched.type = false;
    touched.theme = false;
  }

  async function loadConstants() {
    try {
      const data = await fetchCaseConstants();
      if (data) {
        if (data.case_types) constants.case_types = data.case_types;
        if (Array.isArray(data.themes)) constants.themes = data.themes;
        if (data.statuses) constants.statuses = data.statuses;
      }
    } catch {
      // 后端不可用时使用默认 fallback
    }
  }

  return {
    form,
    touched,
    constants,
    isAuthenticated,
    displayAuthor,
    wordCount,
    readingTime,
    contentSummary,
    errors,
    canSubmit,
    touch,
    validateStep,
    resetForm,
    loadConstants,
  };
}
