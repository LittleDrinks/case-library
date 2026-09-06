import { describe, expect, it } from "vitest";
import { filterQuery, filtersFromQuery } from "./searchFilters.js";

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

function catalogFilterContract() {
  const query = { tagIds: ["tag-1", "tag-2"], tagMode: "any", publishedWithin: "7d" };
  const filters = filtersFromQuery(query, "case");
  expect(filterQuery(filters, "case")).toEqual({
    tagIds: ["tag-1", "tag-2"], tagMode: "any", publishedWithin: "7d",
  });
}

function catalogDefaultModeContract() {
  const filters = filtersFromQuery({ tagIds: ["tag-1"] }, "all");
  expect(filterQuery(filters, "all")).toEqual({ tagIds: ["tag-1"] });
}

function materialDropsCatalogContract() {
  const filters = filtersFromQuery({ tagIds: ["tag-1"], tagMode: "any" }, "material");
  expect(filterQuery(filters, "material")).toEqual({});
}

function filterContract() {
  it("案例多选条件在刷新后完整恢复", caseFilterContract);
  it("知识页丢弃不适用的时间条件", knowledgeFilterContract);
  it("目录标签与匹配方式经 URL 往返后完整恢复", catalogFilterContract);
  it("目录标签默认全部符合，URL 不冗余 tagMode", catalogDefaultModeContract);
  it("素材页丢弃不适用的目录标签条件", materialDropsCatalogContract);
}

describe("检索筛选路由", filterContract);
