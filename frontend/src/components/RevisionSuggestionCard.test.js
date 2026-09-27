import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, expect, it, vi } from "vitest";
import RevisionSuggestionCard from "./RevisionSuggestionCard.vue";

const artifact = {
  id: "artifact-1", kind: "range", status: "pending",
  target: { from: 9, to: 13, quote: "案例原文" },
  replacement: "修改后的正文", reason: "补足论证理由", sources: [],
};

afterEach(() => vi.useRealTimers());

it("默认折叠理由细节，展开时请求正文预览", async () => {
  const wrapper = mount(RevisionSuggestionCard, {
    props: { artifact },
  });

  expect(wrapper.find(".revision-suggestion-details").exists()).toBe(false);
  expect(wrapper.text()).toContain("补足论证理由");
  await wrapper.get(".revision-suggestion-head").trigger("click");

  expect(wrapper.get(".revision-suggestion-details").text()).toContain("案例原文");
  expect(wrapper.emitted("expand")[0][0]).toEqual(artifact);
  expect(wrapper.get('[data-testid="agent-accept"]').text()).toContain("应用修改");
  expect(wrapper.get('[data-testid="agent-reject"]').text()).toContain("保留原文");
});

it("原文变化状态可查看理由但没有应用或微调操作", async () => {
  const wrapper = mount(RevisionSuggestionCard, {
    props: { artifact: { ...artifact, status: "expired" } },
  });

  await wrapper.get(".revision-suggestion-head").trigger("click");
  await flushPromises();
  expect(wrapper.text()).toContain("原文已变化");
  expect(wrapper.text()).toContain("这条建议不能应用");
  expect(wrapper.find(".revision-suggestion-actions").exists()).toBe(false);
});

it("键盘聚焦会展开并定位建议", async () => {
  const wrapper = mount(RevisionSuggestionCard, { props: { artifact } });

  await wrapper.get(".revision-suggestion-head").trigger("focusin", { relatedTarget: null });

  expect(wrapper.get(".revision-suggestion").classes()).toContain("expanded");
  expect(wrapper.emitted("expand")[0][0]).toEqual(artifact);
});

it("已停用建议仍可展开查看记录，但没有应用操作", async () => {
  const wrapper = mount(RevisionSuggestionCard, {
    props: { artifact: { ...artifact, status: "superseded" } },
  });

  expect(wrapper.get(".revision-suggestion-head").attributes("disabled")).toBeUndefined();
  await wrapper.get(".revision-suggestion-head").trigger("click");

  expect(wrapper.get(".revision-suggestion-details").text()).toContain("案例原文");
  expect(wrapper.find(".revision-suggestion-actions").exists()).toBe(false);
});

it("微调后标记旧建议但保留展开状态", async () => {
  vi.useFakeTimers();
  const wrapper = mount(RevisionSuggestionCard, { props: { artifact, expanded: true } });
  await wrapper.setProps({ artifact: { ...artifact, status: "superseded" } });
  await vi.advanceTimersByTimeAsync(260);

  expect(wrapper.classes()).toContain("complete");
  expect(wrapper.classes()).toContain("expanded");
  expect(wrapper.get(".revision-suggestion-title").text()).toBe("案例原文");
  expect(wrapper.emitted("collapse")).toBeUndefined();
});

it("保留原文时维持卡片展开且不划掉标题", async () => {
  vi.useFakeTimers();
  const wrapper = mount(RevisionSuggestionCard, { props: { artifact, expanded: true } });
  await wrapper.setProps({ artifact: { ...artifact, status: "rejected" } });
  await vi.advanceTimersByTimeAsync(260);

  expect(wrapper.classes()).not.toContain("complete");
  expect(wrapper.classes()).toContain("expanded");
  expect(wrapper.get(".revision-suggestion-title").text()).toBe("案例原文");
  expect(wrapper.emitted("collapse")).toBeUndefined();
});

it("应用后保留展开状态，撤销入口位于卡片内", async () => {
  const wrapper = mount(RevisionSuggestionCard, { props: { artifact, expanded: true } });
  await wrapper.setProps({ artifact: { ...artifact, status: "accepted", writeId: "write-1" } });
  expect(wrapper.classes()).not.toContain("collapsing");
  const undo = wrapper.get('[data-testid="agent-undo-revision"]');
  await undo.trigger("click");
  expect(wrapper.emitted("undo")).toEqual([["write-1"]]);
  expect(wrapper.classes()).toContain("expanded");
});

it("撤销后显示真实状态并可再次应用", async () => {
  const wrapper = mount(RevisionSuggestionCard, {
    props: { artifact: { ...artifact, status: "accepted", writeId: "write-1" }, writeStatus: "undone", expanded: true },
  });
  expect(wrapper.get(".revision-suggestion-status").text()).toBe("已撤销");
  expect(wrapper.find('[data-testid="agent-undo-revision"]').exists()).toBe(false);
  await wrapper.get('[data-testid="agent-redo-revision"]').trigger("click");
  expect(wrapper.emitted("accept")).toEqual([["artifact-1"]]);
});

it.each(["written", "undone"])("已应用建议在 %s 状态仍可微调", async (writeStatus) => {
  const wrapper = mount(RevisionSuggestionCard, {
    props: { artifact: { ...artifact, status: "accepted", writeId: "write-1" }, writeStatus, expanded: true },
  });
  await wrapper.get('[data-testid="agent-refine"]').trigger("click");
  expect(wrapper.emitted("refine")).toEqual([[artifact.id]]);
});

it("流式建议可展开，但生成结束前不能应用", async () => {
  const wrapper = mount(RevisionSuggestionCard, { props: { artifact: { ...artifact, provisional: true } } });
  await wrapper.get(".revision-suggestion-head").trigger("click");
  expect(wrapper.get(".revision-suggestion-details").isVisible()).toBe(true);
  expect(wrapper.get('[data-testid="agent-accept"]').attributes("disabled")).toBeDefined();
  expect(wrapper.get(".revision-suggestion-status").text()).toBe("生成中");
});
