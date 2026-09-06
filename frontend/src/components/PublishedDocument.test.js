import { mount } from "@vue/test-utils";
import { nextTick } from "vue";
import { expect, it } from "vitest";
import PublishedDocument from "./PublishedDocument.vue";

const citedDocument = {
  type: "doc",
  content: [{
    type: "paragraph",
    content: [{
      type: "text",
      text: "案例原文",
      marks: [{ type: "citation", attrs: { sourceType: "case", sourceId: "src-1" } }],
    }],
  }],
};

const sources = [
  { id: "src-0", sourceType: "case", caseId: "case-8", versionId: "ver-8", title: "先列来源" },
  { id: "src-1", sourceType: "case", caseId: "case-9", versionId: "ver-9", title: "来源案例" },
];

it("只读正文按来源顺序渲染引用上标", async () => {
  const wrapper = mount(PublishedDocument, {
    props: { document: citedDocument, sources },
  });
  await nextTick();
  await nextTick();
  const marker = wrapper.get(".citation-marker");
  expect(marker.text()).toBe("〔2〕");
  expect(marker.attributes("title")).toBe("来源：来源案例");
  expect(wrapper.get(".citation-anchor").text()).toBe("案例原文");
});
