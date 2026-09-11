import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, expect, it, vi } from "vitest";
import CommentPanel from "./CommentPanel.vue";
import { api } from "../api.js";

vi.mock("../api.js", () => ({
  api: {
    listAnnotations: vi.fn(), createAnnotation: vi.fn(), updateAnnotation: vi.fn(),
    deleteAnnotation: vi.fn(), replyAnnotation: vi.fn(), setAnnotationStatus: vi.fn(),
    mergeAnnotation: vi.fn(),
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
const revisedAnnotation = {
  ...annotation,
  revisions: [
    { id: "revision-1", replacement: "第一轮", reason: "先补充依据", status: "expired" },
    { id: "revision-2", replacement: "最新轮", reason: "再收紧表述", status: "pending" },
  ],
};
const resolvedAnnotation = { ...revisedAnnotation, status: "resolved", revisions: [
  ...revisedAnnotation.revisions.slice(0, 1),
  { ...revisedAnnotation.revisions[1], status: "accepted" },
] };
const resolvedDiscussion = {
  ...resolvedAnnotation,
  id: "annotation-resolved",
  content: "已解决批注",
  replies: [{ id: "reply-1", content: "已完成处理", createdBy: user.id, createdAt: annotation.createdAt }],
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

function deferred() {
  let resolve;
  const promise = new Promise((done) => { resolve = done; });
  return { promise, resolve };
}

it("没有有效选区时禁用手动批注输入并给出提示", async () => {
  const wrapper = await mountPanel({ selection: null });
  expect(wrapper.get('[aria-label="批注内容"]').attributes("disabled")).toBeDefined();
  expect(wrapper.text()).toContain("请先在正文中选择一段文字");
});

it("作者创建批注时发送完整锚点并立即更新列表", async () => {
  api.listAnnotations.mockResolvedValueOnce([]).mockResolvedValueOnce([annotation]);
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

it("批注加载替换列表时仍显示已成功创建的批注", async () => {
  const list = deferred();
  const refreshed = deferred();
  const create = deferred();
  api.listAnnotations.mockReturnValueOnce(list.promise).mockReturnValueOnce(refreshed.promise);
  api.createAnnotation.mockReturnValueOnce(create.promise);
  const wrapper = mount(CommentPanel, { props: { caseRecord, user, selection } });
  await wrapper.get('[aria-label="批注内容"]').setValue("并发批注");
  const addButton = wrapper.findAll("button").find((button) => button.text() === "添加批注");
  await addButton.trigger("click");
  list.resolve([]);
  await flushPromises();
  create.resolve(annotation);
  await flushPromises();
  refreshed.resolve([annotation]);
  await flushPromises();
  expect(wrapper.find(".comment-card").exists()).toBe(true);
});

it("旧列表晚于创建后的刷新返回时不覆盖新批注", async () => {
  const initial = deferred();
  const refreshed = deferred();
  const create = deferred();
  api.listAnnotations.mockReturnValueOnce(initial.promise).mockReturnValueOnce(refreshed.promise);
  api.createAnnotation.mockReturnValueOnce(create.promise);
  const wrapper = mount(CommentPanel, { props: { caseRecord, user, selection } });
  await wrapper.get('[aria-label="批注内容"]').setValue("并发批注");
  const addButton = wrapper.findAll("button").find((button) => button.text() === "添加批注");
  await addButton.trigger("click");
  create.resolve(annotation);
  await flushPromises();
  refreshed.resolve([annotation]);
  await flushPromises();
  initial.resolve([]);
  await flushPromises();
  expect(wrapper.find(".comment-card").exists()).toBe(true);
});

it("案例切换后忽略旧案例的批注加载结果", async () => {
  const first = deferred();
  const second = deferred();
  const oldAnnotation = { ...annotation, content: "旧案例批注" };
  const nextAnnotation = { ...annotation, id: "annotation-2", caseId: "case-2", content: "新案例批注" };
  api.listAnnotations.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise);
  const wrapper = mount(CommentPanel, { props: { caseRecord, user, selection } });
  await wrapper.setProps({ caseRecord: { ...caseRecord, id: "case-2" } });
  second.resolve([nextAnnotation]);
  await flushPromises();
  first.resolve([oldAnnotation]);
  await flushPromises();
  expect(wrapper.text()).toContain("新案例批注");
  expect(wrapper.text()).not.toContain("旧案例批注");
});

it("正文保存后的批注刷新令牌会重新加载锚点状态", async () => {
  api.listAnnotations
    .mockResolvedValueOnce([annotation])
    .mockResolvedValueOnce([{ ...annotation, anchorState: "changed" }]);
  const wrapper = await mountPanel({ annotationRefreshToken: 1 });
  await wrapper.setProps({ annotationRefreshToken: 2 });
  await flushPromises();
  expect(api.listAnnotations).toHaveBeenCalledTimes(2);
  expect(wrapper.text()).toContain("原文已变动，旧修订不可合并");
});

it("关闭期间迟到的批注列表不会把已解决批注重新打开", async () => {
  const stale = deferred();
  const closing = deferred();
  api.listAnnotations.mockResolvedValueOnce([annotation]).mockReturnValueOnce(stale.promise);
  api.setAnnotationStatus.mockReturnValueOnce(closing.promise);
  const wrapper = await mountPanel();

  await wrapper.get(".comment-status-action").trigger("click");
  await wrapper.setProps({ annotationRefreshToken: 1 });
  closing.resolve({ ...resolvedDiscussion, id: annotation.id });
  await flushPromises();
  stale.resolve([annotation]);
  await flushPromises();

  expect(wrapper.findAll(".comment-card")).toHaveLength(0);
  await wrapper.get('[aria-label="查看已解决批注"]').trigger("click");
  expect(wrapper.get('[data-annotation-id="annotation-1"]').text()).toContain("已解决");
  expect(wrapper.emitted("annotations").at(-1)[0]).toEqual([]);
});

it("创建成功后刷新失败仍显示已保存批注且不能重复提交空输入", async () => {
  api.listAnnotations.mockResolvedValueOnce([]).mockRejectedValueOnce(new Error("批注加载失败"));
  const wrapper = await mountPanel();
  await wrapper.get('[aria-label="批注内容"]').setValue("请补充依据");
  const addButton = wrapper.findAll("button").find((button) => button.text() === "添加批注");
  await addButton.trigger("click");
  await flushPromises();
  expect(wrapper.findAll(".comment-card")).toHaveLength(1);
  expect(wrapper.text()).toContain("原始批注");
  expect(wrapper.text()).toContain("批注加载失败");
  expect(wrapper.get('[aria-label="批注内容"]').element.value).toBe("");
  await addButton.trigger("click");
  expect(api.createAnnotation).toHaveBeenCalledTimes(1);
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

it("已解决历史的陈旧锚点不显示待处理警告", async () => {
  api.listAnnotations.mockResolvedValue([{ ...resolvedDiscussion, anchorState: "changed" }]);
  const wrapper = await mountPanel();
  await wrapper.get('[aria-label="查看已解决批注"]').trigger("click");
  const card = wrapper.get('[data-annotation-id="annotation-resolved"]');
  expect(card.text()).toContain("已解决");
  expect(wrapper.text()).not.toContain("原文已变动，旧修订不可合并");
  expect(wrapper.text()).not.toContain("原文已删除");
});

it("原文改写或删除时保留讨论并显示锚点状态", async () => {
  api.listAnnotations.mockResolvedValue([
    { ...annotation, id: "changed", anchorState: "changed" },
    { ...annotation, id: "deleted", anchorState: "deleted" },
  ]);
  const wrapper = await mountPanel();
  expect(wrapper.text()).toContain("原文已变动，旧修订不可合并");
  expect(wrapper.text()).toContain("原文已删除");
  expect(wrapper.findAll(".comment-card")).toHaveLength(2);
});

it("关闭批注后清除仍在正文与 AI 间绑定的选区", async () => {
  api.listAnnotations.mockResolvedValue([annotation]);
  api.setAnnotationStatus.mockResolvedValue({ ...annotation, status: "resolved" });
  const wrapper = await mountPanel();
  await wrapper.get("button.comment-status-action").trigger("click");
  await flushPromises();
  expect(wrapper.emitted("clear-writing-context")).toHaveLength(1);
});

it("默认列表隐藏已解决批注并从正文标记事件剔除，历史入口显示完整讨论", async () => {
  api.listAnnotations.mockResolvedValue([annotation, resolvedDiscussion]);
  const wrapper = await mountPanel();

  expect(wrapper.findAll(".comment-card")).toHaveLength(1);
  expect(wrapper.get('[data-annotation-id="annotation-1"]').exists()).toBe(true);
  expect(wrapper.find('[data-annotation-id="annotation-resolved"]').exists()).toBe(false);
  expect(wrapper.emitted("annotations").at(-1)[0]).toEqual([annotation]);

  await wrapper.get('[aria-label="查看已解决批注"]').trigger("click");
  expect(wrapper.find('[data-annotation-id="annotation-resolved"]').text()).toContain("已完成处理");
  expect(wrapper.find('[data-annotation-id="annotation-1"]').exists()).toBe(false);
  expect(wrapper.emitted("annotations").at(-1)[0]).toEqual([annotation]);
});

it("直接关闭后从默认列表与正文标记移除，并可从历史入口回看", async () => {
  api.listAnnotations.mockResolvedValue([annotation]);
  api.setAnnotationStatus.mockResolvedValue({ ...resolvedDiscussion, id: annotation.id });
  const wrapper = await mountPanel();

  await wrapper.get(".comment-status-action").trigger("click");
  await flushPromises();

  expect(wrapper.find('[data-annotation-id="annotation-1"]').exists()).toBe(false);
  expect(wrapper.emitted("annotations").at(-1)[0]).toEqual([]);
  await wrapper.get('[aria-label="查看已解决批注"]').trigger("click");
  expect(wrapper.get('[data-annotation-id="annotation-1"]').text()).toContain("已完成处理");
});

it("显示多轮 AI 修订并从批注面板合并最新轮", async () => {
  api.listAnnotations.mockResolvedValue([revisedAnnotation]);
  api.mergeAnnotation.mockResolvedValue({
    annotation: resolvedAnnotation, case: { ...caseRecord, revision: 5 },
  });
  const wrapper = await mountPanel();
  expect(wrapper.text()).toContain("第一轮");
  expect(wrapper.text()).toContain("最新轮");
  await wrapper.findAll("button").find((button) => button.text().includes("让 AI 修订")).trigger("click");
  expect(wrapper.emitted("ask-ai")[0][0]).toMatchObject({ id: annotation.id });
  await wrapper.findAll("button").find((button) => button.text().includes("合并并关闭")).trigger("click");
  await flushPromises();
  expect(api.mergeAnnotation).toHaveBeenCalledWith(caseRecord.id, annotation.id, user.csrfToken);
  expect(wrapper.emitted("case-revised")[0][0]).toMatchObject({ revision: 5 });
  expect(wrapper.find('[data-annotation-id="annotation-1"]').exists()).toBe(false);
  await wrapper.get('[aria-label="查看已解决批注"]').trigger("click");
  expect(wrapper.get('[data-annotation-id="annotation-1"]').text()).toContain("已解决");
});
