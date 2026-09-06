import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, expect, it, vi } from "vitest";
import CommentPanel from "./CommentPanel.vue";
import { api } from "../api.js";

vi.mock("../api.js", () => ({
  api: {
    listAnnotations: vi.fn(), createAnnotation: vi.fn(), updateAnnotation: vi.fn(),
    deleteAnnotation: vi.fn(), replyAnnotation: vi.fn(), setAnnotationStatus: vi.fn(),
  },
}));

const caseRecord = {
  id: "case-1", ownerId: "user-1", workflowStatus: "draft", revision: 4,
};
const user = { id: "user-1", role: "user", csrfToken: "csrf" };
const selection = {
  from: 9, to: 16, quote: "选中的正文", section: "一、教学说明",
  quoteHash: "hash", revision: 4,
};
const annotation = {
  id: "annotation-1", caseId: "case-1", quote: selection.quote,
  section: selection.section, content: "原始批注", source: "manual",
  from: selection.from, to: selection.to, quoteHash: selection.quoteHash,
  revision: selection.revision, status: "pending", replies: [], createdBy: user.id,
  createdAt: "2026-08-26T00:00:00Z",
};

beforeEach(() => {
  vi.clearAllMocks();
  api.listAnnotations.mockResolvedValue([]);
  api.createAnnotation.mockResolvedValue(annotation);
  api.updateAnnotation.mockResolvedValue({ ...annotation, content: "已编辑批注" });
  api.deleteAnnotation.mockResolvedValue(null);
});

async function mountPanel(overrides = {}) {
  const wrapper = mount(CommentPanel, {
    props: { caseRecord, user, selection, ...overrides },
  });
  await flushPromises();
  return wrapper;
}

it("没有有效选区时禁用手动批注输入并给出提示", async () => {
  const wrapper = await mountPanel({ selection: null });
  expect(wrapper.get('[aria-label="批注内容"]').attributes("disabled")).toBeDefined();
  expect(wrapper.text()).toContain("请先在正文中选择一段文字");
});

it("作者创建批注时发送完整锚点并立即更新列表", async () => {
  const wrapper = await mountPanel();
  await wrapper.get('[aria-label="批注内容"]').setValue("请补充依据");
  const addButton = wrapper.findAll("button").find((button) => button.text() === "添加批注");
  await addButton.trigger("click");
  await flushPromises();
  expect(api.createAnnotation).toHaveBeenCalledWith(
    caseRecord.id,
    expect.objectContaining({ ...selection, content: "请补充依据", source: "manual" }),
    user.csrfToken,
  );
  expect(wrapper.text()).toContain("原始批注");
});

it("作者可以编辑并删除自己的未解决批注", async () => {
  api.listAnnotations.mockResolvedValue([annotation]);
  const wrapper = await mountPanel();
  await wrapper.get('[aria-label="编辑批注"]').trigger("click");
  await wrapper.get('[aria-label="编辑批注"]').setValue("已编辑批注");
  const saveButton = wrapper.findAll("button").find((button) => button.text() === "保存批注");
  await saveButton.trigger("click");
  await flushPromises();
  expect(api.updateAnnotation).toHaveBeenCalledWith(
    caseRecord.id, annotation.id, { content: "已编辑批注" }, user.csrfToken,
  );
  await wrapper.get('[aria-label="删除批注"]').trigger("click");
  await flushPromises();
  expect(api.deleteAnnotation).toHaveBeenCalledWith(caseRecord.id, annotation.id, user.csrfToken);
  expect(wrapper.find(".comment-card").exists()).toBe(false);
});
