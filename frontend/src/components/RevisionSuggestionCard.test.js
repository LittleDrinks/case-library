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

it("应用或微调时给旧标题划线并折叠卡片", async () => {
  vi.useFakeTimers();
  const wrapper = mount(RevisionSuggestionCard, { props: { artifact, expanded: true } });
  await wrapper.setProps({ artifact: { ...artifact, status: "superseded" } });
  await vi.advanceTimersByTimeAsync(260);

  expect(wrapper.classes()).toContain("complete");
  expect(wrapper.classes()).not.toContain("expanded");
  expect(wrapper.get(".revision-suggestion-title").text()).toBe("案例原文");
  expect(wrapper.emitted("collapse")).toEqual([["artifact-1"]]);
});

it("保留原文时折叠卡片但不划掉标题", async () => {
  vi.useFakeTimers();
  const wrapper = mount(RevisionSuggestionCard, { props: { artifact, expanded: true } });
  await wrapper.setProps({ artifact: { ...artifact, status: "rejected" } });
  await vi.advanceTimersByTimeAsync(260);

  expect(wrapper.classes()).not.toContain("complete");
  expect(wrapper.classes()).not.toContain("expanded");
  expect(wrapper.get(".revision-suggestion-title").text()).toBe("案例原文");
  expect(wrapper.emitted("collapse")).toEqual([["artifact-1"]]);
});
