import { currentUser as defaultCurrentUser } from "../api/auth.js";

const DRAFT_KEY = "case_library_create_case_draft";

/**
 * 案例创建页本地草稿管理
 *
 * 将 localStorage 中的草稿读写抽离出来，明确区分：
 * - 新建案例：caseId 为空，提交时由后端生成新案例；
 * - 继续编辑草稿：caseId 非空，保存/提交时更新已有案例。
 *
 * 草稿按用户名隔离。若登录用户与保存草稿时不一致，则丢弃旧 caseId 与
 * latestReviewVersionId，避免把 A 用户的草稿 caseId 套用到 B 用户身上。
 */
export function useCaseDraft({
  form,
  caseId,
  latestReviewVersionId,
  getCurrentUser = defaultCurrentUser,
}) {
  function buildSnapshot() {
    const user = getCurrentUser();
    return {
      username: user?.username || "",
      form: {
        title: form.title,
        author: form.author,
        department: form.department,
        content: form.content,
        source_material: form.source_material,
        type: form.type,
        theme: form.theme,
        target_stages: form.target_stages,
      },
      caseId: caseId.value,
      latestReviewVersionId: latestReviewVersionId.value,
      savedAt: Date.now(),
    };
  }

  function persistDraft() {
    try {
      localStorage.setItem(DRAFT_KEY, JSON.stringify(buildSnapshot()));
    } catch {
      // 忽略存储异常（例如隐私模式、容量超限）
    }
  }

  function loadDraft(options = {}) {
    const {
      includeBackendIds = true,
      includeExistingCaseDraft = true,
    } = options;
    try {
      const raw = localStorage.getItem(DRAFT_KEY);
      if (!raw) return;
      const saved = JSON.parse(raw);
      const user = getCurrentUser();
      const sameUser = !saved.username || saved.username === user?.username;
      const hasBackendIds = Boolean(saved?.caseId || saved?.latestReviewVersionId);

      if (sameUser && hasBackendIds && !includeExistingCaseDraft) {
        caseId.value = null;
        latestReviewVersionId.value = null;
        return;
      }

      if (saved?.form) {
        Object.assign(form, saved.form);
      }

      if (sameUser && includeBackendIds && saved?.caseId) {
        caseId.value = saved.caseId;
      }

      if (sameUser && includeBackendIds && saved?.latestReviewVersionId) {
        latestReviewVersionId.value = saved.latestReviewVersionId;
      }

      if (!sameUser || !includeBackendIds) {
        // 切换用户时只保留表单字段，重置后端标识，防止误用他人草稿
        caseId.value = null;
        latestReviewVersionId.value = null;
      }
    } catch {
      // 忽略损坏或无法解析的存储内容
    }
  }

  function clearDraft() {
    try {
      localStorage.removeItem(DRAFT_KEY);
    } catch {
      // 忽略
    }
  }

  return {
    persistDraft,
    loadDraft,
    clearDraft,
  };
}
