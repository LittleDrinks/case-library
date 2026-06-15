import { reactive, ref, computed } from "vue";
import { listPrompts, runParagraphReview } from "../api/ai.js";
import { createCase, updateCase } from "../api/cases.js";
import { notify } from "../utils/toast.js";

const DEFAULT_AI_REVIEW_ITEMS = [
  {
    id: "alpha/paragraph-review",
    name: "段落批注自查",
    description: "生成只读版本，并按段落给出作者侧修改建议。",
    variables: ["title", "content", "source_material", "type", "theme"],
  },
];

function createEmptyReviewState() {
  return {
    status: "idle",
    answer: "",
    parsed: null,
    parse_error: null,
    error: "",
    comments: [],
    summary: null,
    version: null,
  };
}

/**
 * AI 自查状态与调用逻辑
 *
 * 管理提示词列表、各条自查的运行状态、结果解析，以及提交前把 AI 结果
 * 附加到 payload 的收集逻辑。
 */
export function useAiReview({
  form,
  isAuthenticated,
  caseId,
  latestReviewVersionId,
  persistDraft,
  displayAuthor,
}) {
  const aiReviewItems = ref([...DEFAULT_AI_REVIEW_ITEMS]);
  const aiReviewState = reactive(
    Object.fromEntries(
      DEFAULT_AI_REVIEW_ITEMS.map((item) => [item.id, createEmptyReviewState()])
    )
  );

  const aiPromptLoadError = ref("");
  const aiRunningAll = ref(false);

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
    const done = aiReviewItems.value.filter(
      (item) => aiReviewState[item.id].status === "success"
    ).length;
    return Math.round((done / total) * 100);
  });

  function ensureAiReviewState(promptId) {
    if (!aiReviewState[promptId]) {
      aiReviewState[promptId] = createEmptyReviewState();
    }
    return aiReviewState[promptId];
  }

  function resetAiReviewItem(promptId) {
    const state = ensureAiReviewState(promptId);
    Object.assign(state, createEmptyReviewState());
  }

  function resetAllAiReviews() {
    for (const item of aiReviewItems.value) {
      resetAiReviewItem(item.id);
    }
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
    const variables = buildAiVariables();
    const payload = {
      title: variables.title,
      content: variables.content,
      source_material: variables.source_material,
      department: form.department.trim(),
      type: variables.type,
      theme: variables.theme,
      status: "draft",
    };

    if (caseId.value) {
      try {
        await updateCase(caseId.value, {
          ...payload,
          author: displayAuthor.value,
          change_reason: "AI 审核前更新",
        });
      } catch (err) {
        const detail = err.data?.detail || err.message || "";
        if (detail !== "案例没有实际变更") {
          throw err;
        }
      }
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
          version_id: state.version?.id || null,
          version_number: state.version?.version_number || null,
          version: state.version || null,
          comments: state.comments || [],
          summary: state.summary || null,
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
      const prompts = await listPrompts("alpha");
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
    Object.assign(state, createEmptyReviewState(), { status: "loading" });

    try {
      const activeCaseId = await ensureDraftCase();
      const data = await runParagraphReview(activeCaseId);
      const result = data?.data || {};
      const version = result.version || {};

      latestReviewVersionId.value = version.id || null;
      state.status = "success";
      state.comments = result.comments || [];
      state.summary = result.summary || null;
      state.version = version || null;
      state.answer =
        state.comments.map((comment) => comment.message).join("\n") || "AI 未返回段落批注。";

      const summarySuggestions = Array.from(new Set(result.summary?.suggested_next_steps || []));
      state.parsed = {
        detail: `已生成 v${version.version_number || ""} 只读审核版本，包含 ${state.comments.length} 条段落批注。`,
        suggestions: hasAnnotationPreview(state)
          ? summarySuggestions
          : summarySuggestions.concat(
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

  return {
    aiReviewItems,
    aiReviewState,
    aiPromptLoadError,
    aiRunningAll,
    canRunAiReview,
    aiReviewProgress,
    ensureAiReviewState,
    resetAiReviewItem,
    resetAllAiReviews,
    commentsForParagraph,
    hasAnnotationPreview,
    aiStatusLabel,
    collectAiReviews,
    hasAiReviewWarning,
    confirmAiReviewWarning,
    loadAiPrompts,
    runAiReview,
    runAllAiReviews,
  };
}
