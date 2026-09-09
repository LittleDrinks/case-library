import { describe, expect, it } from "vitest";
import {
  emptyFilters, filterChips, filterQuery, filtersFromQuery, selected,
  updateFilter, updateTagMode,
} from "./searchFilters.js";

function caseFilterContract() {
  const query = {
    typeName: ["校本实践类", "科技创新与科技报国类"],
    audience: "ug", publishedWithin: "30d",
  };

  const filters = filtersFromQuery(query, "case");

  expect(filterQuery(filters, "case")).toEqual({
    typeName: ["校本实践类", "科技创新与科技报国类"],
    audience: ["ug"], publishedWithin: "30d",
  });
}

function knowledgeFilterContract() {
  const filters = filtersFromQuery({ publishedWithin: "7d" }, "knowledge");
  expect(filterQuery(filters, "knowledge")).toEqual({});
}

function tagRoundTripContract() {
  const filters = filtersFromQuery({ tagIds: ["tag-a", "tag-b"], tagMode: "any" }, "case");

  expect(filters.tagMode).toBe("any");
  expect(filterQuery(filters, "case")).toEqual({ tagIds: ["tag-a", "tag-b"], tagMode: "any" });
}

function tagDefaultAndContract() {
  const filters = filtersFromQuery({ tagIds: "tag-a" }, "all");

  expect(filterQuery(filters, "all")).toEqual({ tagIds: ["tag-a"] });
}

function tagScopedToTagKindsContract() {
  const filters = filtersFromQuery({ tagIds: "tag-a", tagMode: "any" }, "material");

  expect(filterQuery(filters, "material")).toEqual({});
  expect(filterQuery(filters, "knowledge")).toEqual({});
}

function tagToggleContract() {
  let filters = updateFilter(emptyFilters(), "tagCatalog", "tag-a", true);
  filters = updateFilter(filters, "tagCatalog", "tag-b", true);
  expect(filters.tagIds).toEqual(["tag-a", "tag-b"]);
  filters = updateTagMode(filters, "any");
  filters = updateFilter(filters, "tagCatalog", "tag-a", false);
  expect(filters.tagIds).toEqual(["tag-b"]);
  expect(filters.tagMode).toBe("any");
  expect(selected(filters, "tagCatalog", "tag-b")).toBe(true);
}

function tagChipContract() {
  const catalog = [{ id: "g1", name: "课程", tags: [{ id: "tag-a", name: "纲要" }] }];
  const filters = { ...emptyFilters(), tagIds: ["tag-a", "tag-x"] };

  expect(filterChips(filters, "case", catalog)).toEqual([
    { group: "tagCatalog", value: "tag-a", label: "纲要" },
    { group: "tagCatalog", value: "tag-x", label: "tag-x" },
  ]);
}

function filterContract() {
  it("案例多选条件在刷新后完整恢复", caseFilterContract);
  it("知识页丢弃不适用的时间条件", knowledgeFilterContract);
  it("标签条件与模式在刷新后完整恢复", tagRoundTripContract);
  it("默认 AND 时路由省略 tagMode", tagDefaultAndContract);
  it("标签条件只提交给案例与全部页签", tagScopedToTagKindsContract);
  it("标签可多选、逐个移除并切换模式", tagToggleContract);
  it("标签胶囊用目录名称展示未知标签回退为 ID", tagChipContract);
}

describe("检索筛选路由", filterContract);
