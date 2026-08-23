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

function filterContract() {
  it("案例多选条件在刷新后完整恢复", caseFilterContract);
  it("知识页丢弃不适用的时间条件", knowledgeFilterContract);
}

describe("检索筛选路由", filterContract);
