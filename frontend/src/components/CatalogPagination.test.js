import { mount } from "@vue/test-utils";
import { expect, test } from "vitest";
import CatalogPagination from "./CatalogPagination.vue";

test("单页结果不展示无效翻页控件", () => {
  const wrapper = mount(CatalogPagination, {
    props: {
      page: 1,
      total: 9,
      nextCursor: null,
      previousCursor: null,
    },
  });

  expect(wrapper.find("nav").exists()).toBe(false);
});

test("大目录只按游标前进和返回，不生成深页链接", async () => {
  const wrapper = mount(CatalogPagination, {
    props: {
      page: 1, pageSize: 50, total: 12_480,
      nextCursor: "next-token", previousCursor: null,
    },
  });

  expect(wrapper.text()).toContain("第 1 页 · 共 12480 条");
  expect(wrapper.find("[aria-label='第 250 页']").exists()).toBe(false);
  expect(wrapper.get("[aria-label='上一页']").attributes("disabled")).toBeDefined();
  await wrapper.get("[aria-label='下一页']").trigger("click");
  expect(wrapper.emitted("change")).toEqual([["next-token"]]);
});
