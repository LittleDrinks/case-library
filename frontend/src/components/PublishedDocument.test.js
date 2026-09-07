import { mount } from "@vue/test-utils";
import { nextTick } from "vue";
import { expect, test } from "vitest";
import PublishedDocument from "./PublishedDocument.vue";

const document = {
  type: "doc",
  content: [{ type: "paragraph", content: [
    { type: "text", text: "甲", marks: [{ type: "citation", attrs: { sourceType: "case", sourceId: "case-1" } }] },
    { type: "text", text: "乙", marks: [{ type: "citation", attrs: { sourceType: "material", sourceId: "mat-1" } }] },
  ] }],
};

test("公开正文显示与资料区一致的引用编号", async () => {
  const wrapper = mount(PublishedDocument, {
    props: { document, sources: [] },
  });
  await nextTick();
  await nextTick();
  await wrapper.setProps({ sources: [
    { sourceType: "material", id: "mat-1", number: 1 },
    { sourceType: "case", id: "case-1", number: 2 },
  ] });
  await nextTick();
  expect(wrapper.findAll(".citation-number").map((item) => item.text()))
    .toEqual(["〔2〕", "〔1〕"]);
});
