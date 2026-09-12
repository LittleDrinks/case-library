import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, expect, it, vi } from "vitest";
import AnnotationFloat from "./AnnotationFloat.vue";
import { api } from "../api.js";

vi.mock("../api.js", () => ({
  api: {
    createAnnotation: vi.fn(),
    replyAnnotation: vi.fn(),
    setAnnotationStatus: vi.fn(),
    mergeAnnotation: vi.fn(),
  },
}));

const caseRecord = {
  id: "case-1", ownerId: "user-1", workflowStatus: "draft", revision: 4,
};
const user = { id: "user-1", role: "user", csrfToken: "csrf" };
const selection = {
  from: 9, to: 13, quote: "案例原文", quoteHash: "h-1",
  section: "正文", revision: 4, sameBlock: true,
};
const annotation = {
  id: "annotation-1", caseId: "case-1", from: 9, to: 13, quote: "案例原文",
  quoteHash: "h-1", section: "正文", revision: 4, anchorState: "active",
  status: "pending", content: "请润色这句", source: "manual", createdBy: "user-1",
  createdAt: "2026-09-12T08:00:00Z", replies: [],
  revisions: [{
    id: "arv-1", artifactId: "art-1", runId: "run-1", baseRevision: 4,
    target: { from: 9, to: 13, quote: "案例原文" }, replacement: "修订后的句子",
    reason: "更通顺", status: "pending", createdBy: "user-1",
    createdAt: "2026-09-12T08:05:00Z",
  }],
};

function mountFloat(props = {}) {
  return mount(AnnotationFloat, {
    props: {
      caseRecord, user, draft: null, ...props,
    },
  });
}

beforeEach(() => {
  vi.clearAllMocks();
});

it("草稿模式展示选区引用和输入框，不显示正式内容", () => {
  const wrapper = mountFloat({ draft: selection });
  expect(wrapper.text()).toContain("案例原文");
  expect(wrapper.find('[aria-label="批注内容"]').exists()).toBe(true);
  expect(wrapper.find(".comment-card").exists()).toBe(false);
});

it("保存意见携带完整正式锚点且不触发任何AI请求", async () => {
  api.createAnnotation.mockResolvedValue(annotation);
  const wrapper = mountFloat({ draft: selection });
  await wrapper.get('[aria-label="批注内容"]').setValue("请润色这句");
  const save = wrapper.findAll("button").find((button) => button.text() === "保存意见");
  await save.trigger("click");
  await flushPromises();
  expect(api.createAnnotation).toHaveBeenCalledWith("case-1", expect.objectContaining({
    from: 9, to: 13, quote: "案例原文", quoteHash: "h-1",
    section: "正文", revision: 4, content: "请润色这句", source: "manual",
  }), "csrf");
  expect(api.mergeAnnotation).not.toHaveBeenCalled();
  expect(wrapper.emitted("saved")[0][0]).toMatchObject({ id: "annotation-1" });
});

it("取消关闭浮窗并清除挂起状态", async () => {
  const wrapper = mountFloat({ draft: selection });
  const cancel = wrapper.findAll("button").find((button) => button.text() === "取消");
  await cancel.trigger("click");
  expect(wrapper.emitted("close")).toHaveLength(1);
});

it("点击标记打开线程：展示意见与多轮修订卡片", () => {
  const wrapper = mountFloat({

    thread: annotation,
  });
  expect(wrapper.text()).toContain("请润色这句");
  expect(wrapper.text()).toContain("第 1 轮");
  expect(wrapper.text()).toContain("修订后的句子");
  expect(wrapper.find(".float-revision-card").exists()).toBe(true);
});

it("解决批注不改正文且不触发合并", async () => {
  api.setAnnotationStatus.mockResolvedValue({ ...annotation, status: "resolved" });
  const wrapper = mountFloat({ thread: annotation });
  const resolve = wrapper.findAll("button").find((button) => button.text() === "解决批注");
  await resolve.trigger("click");
  await flushPromises();
  expect(api.setAnnotationStatus).toHaveBeenCalledWith("case-1", "annotation-1", "resolved", "csrf");
  expect(api.mergeAnnotation).not.toHaveBeenCalled();
  expect(wrapper.emitted("resolved")).toHaveLength(1);
});

it("采用并解决只合并修订并上报新案例", async () => {
  api.mergeAnnotation.mockResolvedValue({
    annotation: { ...annotation, status: "resolved" },
    case: { ...caseRecord, revision: 5 },
  });
  const wrapper = mountFloat({ thread: annotation });
  const adopt = wrapper.findAll("button").find((button) => button.text().includes("采用并解决"));
  await adopt.trigger("click");
  await flushPromises();
  expect(api.mergeAnnotation).toHaveBeenCalledWith("case-1", "annotation-1", "csrf");
  expect(api.setAnnotationStatus).not.toHaveBeenCalled();
  expect(wrapper.emitted("case-revised")[0][0]).toMatchObject({ revision: 5 });
});

it("过期修订禁用采用入口并给出原因", () => {
  const stale = {
    ...annotation,
    revisions: [{ ...annotation.revisions[0], status: "expired" }],
  };
  const wrapper = mountFloat({ thread: stale });
  expect(wrapper.find('[aria-label="采用并解决"]').exists()).toBe(false);
  expect(wrapper.text()).toContain("已失效");
});

it("非作者草稿不显示保存与询问入口", () => {
  const other = { ...caseRecord, ownerId: "someone-else" };
  const wrapper = mountFloat({ caseRecord: other, draft: selection });
  const buttons = wrapper.findAll("button").map((button) => button.text());
  expect(buttons).not.toContain("保存意见");
  expect(buttons).not.toContain("询问AI");
});

it("回复后追加讨论并保留既有修订轮次", async () => {
  api.replyAnnotation.mockResolvedValue({});
  const refreshed = {
    ...annotation,
    replies: [{ id: "ar-1", content: "已采纳建议", createdBy: "user-1", createdAt: "2026-09-12T09:00:00Z" }],
  };
  const wrapper = mountFloat({ thread: annotation });
  await wrapper.get('[aria-label="回复批注"]').setValue("已采纳建议");
  const reply = wrapper.findAll("button").find((button) => button.text() === "回复");
  await reply.trigger("click");
  await flushPromises();
  expect(api.replyAnnotation).toHaveBeenCalledWith("case-1", "annotation-1", { content: "已采纳建议" }, "csrf");
  expect(wrapper.emitted("replied")).toHaveLength(1);
  await wrapper.setProps({ thread: refreshed });
  expect(wrapper.text()).toContain("已采纳建议");
  expect(wrapper.text()).toContain("第 1 轮");
});
