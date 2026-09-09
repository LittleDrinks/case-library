import { mount } from "@vue/test-utils";
import { expect, it } from "vitest";
import SearchFilters from "./SearchFilters.vue";
import { emptyFilters } from "../lib/searchFilters.js";

const CATALOG = [
  { id: "g1", name: "课程", tags: [
    { id: "tag-1", name: "纲要", enabled: true },
    { id: "tag-2", name: "概论", enabled: true },
  ] },
  { id: "g2", name: "思政元素", tags: [{ id: "tag-3", name: "科学家精神" }] },
];

function wrapper(kind, facets = {}, filters = emptyFilters()) {
  return mount(SearchFilters, {
    props: { kind, facets, filters, catalog: CATALOG },
  });
}

function emittedFilters(view) {
  return view.emitted("update:filters").at(-1)[0];
}

it("知识页不展示没有时间语义的更新时间分面", async () => {
  const view = wrapper("knowledge", { publishedWithin: [{ value: "7d", count: 2 }] });

  expect(view.find(".advanced-filter > button").exists()).toBe(false);
  expect(view.text()).not.toContain("更新时间");
});

it("分面选项展示服务端全库计数", async () => {
  const view = wrapper("material", { authority: [
    { value: "original", count: 76 }, { value: "pending", count: 1 },
  ] });

  await view.get(".advanced-filter > button").trigger("click");

  expect(view.text()).toContain("原始权威来源76");
  expect(view.text()).toContain("待核验线索1");
});

it("标签目录按分组展示并支持按名称查找", async () => {
  const view = wrapper("case");
  await view.get(".advanced-filter > button").trigger("click");

  expect(view.text()).toContain("课程");
  expect(view.text()).toContain("科学家精神");

  await view.get("input[type='search']").setValue("科学");

  expect(view.text()).toContain("思政元素");
  expect(view.text()).not.toContain("纲要");
});

it("标签展示当前结果计数且零计数仍可选", async () => {
  const view = wrapper("case", { tagCatalog: [{ value: "tag-1", count: 5 }] });
  await view.get(".advanced-filter > button").trigger("click");

  expect(view.text()).toContain("纲要5");
  expect(view.text()).toContain("科学家精神0");

  await view.findAll(".tag-group input[type='checkbox']")[2].setValue(true);

  expect(emittedFilters(view).tagIds).toEqual(["tag-3"]);
});

it("已选标签可切换 AND/OR 且保留已选集合", async () => {
  const view = wrapper("case", {}, { ...emptyFilters(), tagIds: ["tag-1"], tagMode: "all" });
  await view.get(".advanced-filter > button").trigger("click");
  await view.get("[aria-label='标签匹配方式'] button:nth-child(2)").trigger("click");

  expect(emittedFilters(view).tagMode).toBe("any");
  expect(emittedFilters(view).tagIds).toEqual(["tag-1"]);
});

it("标签胶囊用目录名展示并可逐个移除与清空", async () => {
  const view = wrapper("case", {}, { ...emptyFilters(), tagIds: ["tag-1", "tag-3"] });

  expect(view.text()).toContain("纲要");
  await view.get("[aria-label='移除筛选：纲要']").trigger("click");
  expect(emittedFilters(view).tagIds).toEqual(["tag-3"]);

  await view.get(".clear-filters").trigger("click");
  expect(emittedFilters(view)).toEqual(emptyFilters());
});
