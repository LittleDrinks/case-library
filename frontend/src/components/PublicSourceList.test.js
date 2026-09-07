import { mount } from "@vue/test-utils";
import { expect, test } from "vitest";
import PublicSourceList from "./PublicSourceList.vue";

const sources = [
  {
    id: "src-1", number: 1, sourceType: "case", version: "v3",
    title: "引用案例甲", contentAvailable: true,
    publishedAt: "2026-08-01T00:00:00Z", url: "#/cases/case-9?versionId=ver-3",
  },
  {
    id: "att-2", number: 2, sourceType: "attachment", title: "课堂附件.txt",
    contentAvailable: true, url: "/api/cases/case-1/attachments/att-2/content",
  },
  {
    id: "mat-3", number: 3, sourceType: "material", title: "受限素材乙",
    contentAvailable: false, url: "/api/materials/mat-3/content",
  },
];

test("公开资料列表统一保留编号、版本与固定链接", () => {
  const wrapper = mount(PublicSourceList, { props: { sources } });
  const items = wrapper.findAll("li");
  expect(items).toHaveLength(3);
  expect(items[0].text()).toContain("〔1〕引用案例甲");
  expect(items[0].text()).toContain("v3 · 2026-08-01");
  expect(wrapper.get("[aria-label='打开来源引用案例甲']").attributes("href"))
    .toBe("#/cases/case-9?versionId=ver-3");
  expect(items[1].text()).toContain("〔2〕课堂附件.txt");
  expect(wrapper.get("[aria-label='打开来源课堂附件.txt']").attributes("href"))
    .toBe("/api/cases/case-1/attachments/att-2/content");
  expect(items[2].text()).toContain("〔3〕受限素材乙");
  expect(items[2].text()).toContain("内容按权限开放");
  expect(wrapper.find("[aria-label='打开来源受限素材乙']").exists()).toBe(false);
});

test("没有来源时显示空态", () => {
  const wrapper = mount(PublicSourceList, { props: { sources: [] } });
  expect(wrapper.text()).toContain("暂无来源");
});
