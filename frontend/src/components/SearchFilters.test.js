import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import SearchFilters from "./SearchFilters.vue";

function wrapper(kind, facets = {}) {
  return mount(SearchFilters, {
    props: { kind, facets, filters: {
      type: [], audience: [], authority: [], materialType: [], tags: [], time: "",
    } },
  });
}

describe("高级筛选", () => {
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
});
