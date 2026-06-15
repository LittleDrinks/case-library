import { ref } from "vue";
import { createCase, updateCase, submitCaseById } from "../api/cases.js";
import { notify } from "../utils/toast.js";

/**
 * 案例创建页的保存草稿与正式提交逻辑
 *
 * 把与后端 cases API 的交互、payload 组装和提交状态从视图层抽离，
 * 使 CreateCaseView 只保留步骤导航与渲染编排。
 */
export function useCaseSubmission({
  form,
  caseId,
  latestReviewVersionId,
  displayAuthor,
  isAuthenticated,
  collectAiReviews,
  persistDraft,
  clearDraft,
  resetCaseForm,
  resetAllAiReviews,
}) {
  const saving = ref(false);
  const submitting = ref(false);

  function appendAiReviews(payload) {
    const reviews = collectAiReviews();
    if (reviews.length) {
      payload.ai_reviews = JSON.stringify(reviews);
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
    appendAiReviews(payload);
    return payload;
  }

  async function saveDraft() {
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
        appendAiReviews(payload);
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

  async function submitCase() {
    if (!form.title.trim() || !form.department.trim() || !form.content.trim() || !form.type || !form.theme) {
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
        appendAiReviews(payload);
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
      resetCaseState();
      return true;
    } catch (err) {
      notify(err.message || "提交失败，请稍后重试", "error");
    } finally {
      submitting.value = false;
    }
  }

  function resetCaseState() {
    resetCaseForm();
    resetAllAiReviews();
    caseId.value = null;
    latestReviewVersionId.value = null;
  }

  return {
    saving,
    submitting,
    buildPayload,
    saveDraft,
    submitCase,
    resetCaseState,
  };
}
