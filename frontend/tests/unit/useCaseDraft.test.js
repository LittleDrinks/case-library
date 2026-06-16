import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { reactive, ref } from "vue";
import { useCaseDraft } from "../../src/composables/useCaseDraft.js";

function createDraftHarness(username = "alice") {
  const form = reactive({
    title: "标题",
    author: "作者",
    department: "学院",
    content: "正文",
    source_material: "来源",
    type: "案例类型",
    theme: "思政主题",
  });
  const caseId = ref("case-1");
  const latestReviewVersionId = ref("version-1");
  const getCurrentUser = vi.fn(() => ({ username }));
  const draft = useCaseDraft({ form, caseId, latestReviewVersionId, getCurrentUser });

  return { form, caseId, latestReviewVersionId, draft, getCurrentUser };
}

describe("useCaseDraft", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.useRealTimers();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("persists a draft snapshot to localStorage", () => {
    vi.spyOn(Date, "now").mockReturnValue(1700000000000);
    const { draft } = createDraftHarness();

    draft.persistDraft();

    const saved = JSON.parse(localStorage.getItem("case_library_create_case_draft"));
    expect(saved).toMatchObject({
      username: "alice",
      form: {
        title: "标题",
        author: "作者",
        department: "学院",
        content: "正文",
        source_material: "来源",
        type: "案例类型",
        theme: "思政主题",
      },
      caseId: "case-1",
      latestReviewVersionId: "version-1",
      savedAt: 1700000000000,
    });
  });

  it("loads a same-user draft including backend identifiers", () => {
    const source = createDraftHarness("alice");
    source.form.title = "已保存标题";
    source.draft.persistDraft();

    const target = createDraftHarness("alice");
    target.form.title = "";
    target.caseId.value = null;
    target.latestReviewVersionId.value = null;

    target.draft.loadDraft();

    expect(target.form.title).toBe("已保存标题");
    expect(target.caseId.value).toBe("case-1");
    expect(target.latestReviewVersionId.value).toBe("version-1");
  });

  it("keeps form fields but clears backend identifiers across users", () => {
    const source = createDraftHarness("alice");
    source.form.title = "跨用户草稿";
    source.draft.persistDraft();

    const target = createDraftHarness("bob");
    target.caseId.value = "stale-case";
    target.latestReviewVersionId.value = "stale-version";

    target.draft.loadDraft();

    expect(target.form.title).toBe("跨用户草稿");
    expect(target.caseId.value).toBeNull();
    expect(target.latestReviewVersionId.value).toBeNull();
  });
});
