import { mount } from "@vue/test-utils";
import { expect, test } from "vitest";
import PublicSourceList from "./PublicSourceList.vue";

const sources = [
  { id: "src-1", sourceType: "case", caseId: "case-9", versionId: "ver-3", version: "v3", title: "来源案例", contentAvailable: true },
  { id: "src-2", sourceType: "material", title: "受限资料", contentAvailable: false },
];

test("公开资料保留编号、版本与固定链接", () => {
  const wrapper = mount(PublicSourceList, { props: { sources } });
  expect(wrapper.text()).toContain("〔1〕来源案例");
  expect(wrapper.text()).toContain("v3");
  expect(wrapper.get("[aria-label='打开资料来源案例']").attributes("href"))
    .toBe("#/cases/case-9?versionId=ver-3");
  expect(wrapper.text()).toContain("内容按权限开放");
});

test("没有资料时显示空态", () => {
  const wrapper = mount(PublicSourceList, { props: { sources: [] } });
  expect(wrapper.text()).toContain("暂无资料");
});
