import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import SearchFilters from "./SearchFilters.vue";

const catalog = [
  { id: "g1", name: "思政元素", requiredForSubmission: true, sortKey: 0, tags: [
    { id: "t1", groupId: "g1", name: "科学家精神", sortKey: 0 },
    { id: "t2", groupId: "g1", name: "爱国主义教育", sortKey: 1 },
  ] },
];

function blankFilters() {
  return {
    type: [], audience: [], authority: [], materialType: [], tags: [], time: "",
    tagIds: [], tagMode: "all",
  };
}

function wrapper(kind, facets = {}, extra = {}) {
  return mount(SearchFilters, {
    props: { kind, facets, filters: blankFilters(), ...extra },
  });
}

async function knowledgeTimeContract() {
  const view = wrapper("knowledge", { publishedWithin: [{ value: "7d", count: 2 }] });
  expect(view.find(".advanced-filter > button").exists()).toBe(false);
  expect(view.text()).not.toContain("更新时间");
}

async function facetCountContract() {
  const view = wrapper("material", { authority: [
    { value: "original", count: 76 }, { value: "pending", count: 1 },
  ] });
  await view.get(".advanced-filter > button").trigger("click");
  expect(view.text()).toContain("原始权威来源76");
  expect(view.text()).toContain("待核验线索1");
}

async function catalogGroupingContract() {
  const view = wrapper("case", { tagCatalog: [{ value: "t1", count: 3 }] }, { catalog });
  await view.get(".advanced-filter > button").trigger("click");
  const boxes = view.findAll(".filter-popover fieldset input[type='checkbox']");
  expect(view.text()).toContain("思政元素");
  expect(view.text()).toContain("科学家精神3");
  expect(view.text()).toContain("爱国主义教育0");
  expect(boxes).toHaveLength(2);
  expect(boxes[1].attributes("disabled")).toBeUndefined();
  await boxes[1].setValue(true);
  expect(view.emitted("update:filters")[0][0].tagIds).toEqual(["t2"]);
}

function materialCatalogContract() {
  const view = wrapper("material", {}, { catalog });
  expect(view.find(".advanced-filter > button").exists()).toBe(false);
  expect(view.text()).not.toContain("思政元素");
}

async function tagChipContract() {
  const view = wrapper("case", {}, {
    catalog, filters: { ...blankFilters(), tagIds: ["t1"] },
  });
  await view.get("[aria-label='移除标签：科学家精神']").trigger("click");
  expect(view.emitted("update:filters")[0][0].tagIds).toEqual([]);
}

async function tagModeContract() {
  const view = wrapper("case", {}, {
    catalog, filters: { ...blankFilters(), tagIds: ["t1"] },
  });
  await view.get(".advanced-filter > button").trigger("click");
  await view.get(".tag-mode button:last-child").trigger("click");
  expect(view.emitted("update:filters")[0][0].tagMode).toBe("any");
}

describe("高级筛选", () => {
  it("知识页不展示没有时间语义的更新时间分面", knowledgeTimeContract);
  it("分面选项展示服务端全库计数", facetCountContract);
  it("案例页按目录分组展示全部标签，零计数仍可选", catalogGroupingContract);
  it("素材页不展示目录标签分组", materialCatalogContract);
  it("已选目录标签以 chip 回显并可移除", tagChipContract);
  it("标签匹配方式默认全部符合，可切换任一符合", tagModeContract);
});
