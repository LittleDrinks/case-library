import { mount } from "@vue/test-utils";
import { expect, it } from "vitest";
import AgentArtifactCard from "./AgentArtifactCard.vue";

// 真实存储形状：validate_blocks 输出的规范化块（text/items/paragraphs），
// 与 AgentArtifactCard 的预览读取共用同一结构。
const DOCUMENT_ARTIFACT = {
  id: "artifact-doc-1",
  kind: "document",
  status: "pending",
  blocks: [
    { type: "heading", level: 1, text: "案例初稿" },
    { type: "paragraph", text: "首段正文。" },
    { type: "bullet_list", items: ["要点一", "要点二"] },
    { type: "ordered_list", items: ["第一步", "第二步"] },
    { type: "blockquote", paragraphs: ["引用原文"] },
  ],
  reason: "依据资料整理",
  sources: [],
  target: { from: 0, to: 0, quote: "" },
};

const RANGE_ARTIFACT = {
  id: "artifact-range-1",
  kind: "range",
  status: "pending",
  target: { from: 1, to: 5, quote: "第一段。" },
  replacement: "第一段已修订。",
  reason: "补充评价依据",
  sources: [],
};

it("previews whole-document candidates from the stored block shape", () => {
  const wrapper = mount(AgentArtifactCard, {
    props: { artifact: DOCUMENT_ARTIFACT },
  });
  expect(wrapper.find("[data-artifact-kind='document']").exists()).toBe(true);
  const preview = wrapper.find(".agent-artifact-draft").text();
  expect(preview).toContain("【案例初稿】");
  expect(preview).toContain("首段正文。");
  expect(preview).toContain("· 要点一");
  expect(preview).toContain("2. 第二步");
  expect(preview).toContain("「引用原文」");
  expect(wrapper.text()).toContain("全文初稿候选");
  expect(wrapper.text()).not.toContain("原文：");
});

it("keeps the range card on quote and replacement", () => {
  const wrapper = mount(AgentArtifactCard, {
    props: { artifact: RANGE_ARTIFACT },
  });
  expect(wrapper.find("[data-artifact-kind='range']").exists()).toBe(true);
  expect(wrapper.text()).toContain("修订候选");
  expect(wrapper.text()).toContain("原文：第一段。");
  expect(wrapper.text()).toContain("替换为：第一段已修订。");
  expect(wrapper.find(".agent-artifact-draft").exists()).toBe(false);
});
