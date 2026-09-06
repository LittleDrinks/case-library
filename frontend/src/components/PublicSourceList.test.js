import { mount } from "@vue/test-utils";
import { expect, test } from "vitest";
import PublicSourceList from "./PublicSourceList.vue";

const sources = [
  {
    id: "src-1", sourceType: "case", caseId: "case-9", versionId: "ver-3",
    versionNumber: 3, title: "引用案例甲", contentAvailable: true,
    publishedAt: "2026-08-01T00:00:00Z",
  },
  {
    id: "src-2", sourceType: "case", caseId: "case-8", versionId: "ver-1",
    versionNumber: 1, title: "受限案例乙", contentAvailable: false, publishedAt: null,
  },
];

test("公开来源列表保留编号、版本与固定链接", () => {
  const wrapper = mount(PublicSourceList, { props: { sources } });
  const items = wrapper.findAll("li");
  expect(items).toHaveLength(2);
  expect(items[0].text()).toContain("〔1〕引用案例甲");
  expect(items[0].text()).toContain("v3 · 2026-08-01");
  expect(wrapper.get("[aria-label='打开来源引用案例甲']").attributes("href"))
    .toBe("#/cases/case-9?versionId=ver-3");
  expect(items[1].text()).toContain("内容按权限开放");
});

test("没有来源时显示空态", () => {
  const wrapper = mount(PublicSourceList, { props: { sources: [] } });
  expect(wrapper.text()).toContain("暂无来源");
});
