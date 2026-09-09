import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import SearchView from "./SearchView.vue";
import SearchFilters from "../components/SearchFilters.vue";
import { api, ApiError } from "../api.js";

const replace = vi.fn();
const resolve = vi.fn((location) => ({ href: `resolved:${location.name}` }));
const route = { query: { q: "游标目录", kind: "material" } };

vi.mock("vue-router", () => ({
  useRoute: () => route,
  useRouter: () => ({ replace, resolve }),
}));
vi.mock("../api.js", () => ({
  api: { search: vi.fn(), listTagGroups: vi.fn() },
  ApiError: class ApiError extends Error {},
}));

const SearchAIAnswerStub = {
  props: ["snapshot", "hrefFor"],
  template: '<div class="ai-answer-stub" :data-revision="snapshot.revision" :data-query="snapshot.query" />',
};

const first = {
  items: [{ id: "one", kind: "material", title: "第一页" }],
  facets: { authority: [{ value: "original", count: 21 }] },
  counts: { all: 21, case: 0, knowledge: 0, material: 21 },
  total: 21, page: 1, pageSize: 20, metadataIncluded: true,
  nextCursor: "next-token", previousCursor: null,
};
const second = {
  items: [{ id: "two", kind: "material", title: "第二页" }],
  facets: null, counts: null, total: null, page: 2, pageSize: 20,
  metadataIncluded: false, nextCursor: null, previousCursor: "previous-token",
};

function apiError(status, message) {
  return Object.assign(new ApiError(message), { status });
}

function deferred() {
  let resolve;
  const promise = new Promise((done) => { resolve = done; });
  return { promise, resolve };
}

function render(options = {}) {
  return mount(SearchView, {
    ...options,
    global: { stubs: {
      SiteHeader: true, SearchGraph: true, SearchAIAnswer: SearchAIAnswerStub,
      SearchFilters: true, RouterLink: { template: "<a><slot /></a>" },
    } },
  });
}

function revisionOf(wrapper) {
  return Number(wrapper.get(".ai-answer-stub").attributes("data-revision"));
}

function tagFilters(tagIds, tagMode) {
  return {
    type: [], audience: [], authority: [], materialType: [], tags: [], time: "",
    tagIds, tagMode,
  };
}

test("标签条件切换写入路由并从第一页检索", async () => {
  route.query = { q: "思政", kind: "case" };
  const wrapper = render();
  await flushPromises();
  wrapper.findComponent(SearchFilters).vm.$emit("update:filters", tagFilters(["tag-1", "tag-2"], "any"));
  await flushPromises();

  expect(replace).toHaveBeenCalledWith(expect.objectContaining({
    name: "search",
    query: expect.objectContaining({ q: "思政", kind: "case", tagIds: ["tag-1", "tag-2"], tagMode: "any" }),
  }));
  await wrapper.get("[aria-label='下一页']").trigger("click");
  await flushPromises();
  expect(api.search).toHaveBeenLastCalledWith(
    "思政", "case", "next-token", 20, { tagIds: ["tag-1", "tag-2"], tagMode: "any" },
  );
});

test("URL 携带标签条件时刷新后按原条件检索", async () => {
  api.search.mockReset();
  api.search.mockResolvedValue(first);
  route.query = { kind: "case", tagIds: ["tag-1"], tagMode: "any" };
  render();
  await flushPromises();

  expect(api.search).toHaveBeenLastCalledWith("", "case", null, 20, { tagIds: ["tag-1"], tagMode: "any" });
});

beforeEach(() => {
  vi.clearAllMocks();
  replace.mockReset();
  resolve.mockClear();
  route.query = { q: "游标目录", kind: "material" };
  api.search.mockResolvedValueOnce(first).mockResolvedValueOnce(second);
  api.listTagGroups.mockResolvedValue([]);
});

afterEach(() => vi.useRealTimers());

test("翻页将游标保存在内存并保留首屏检索元数据", async () => {
  const wrapper = render();
  await flushPromises();
  await wrapper.get("[aria-label='下一页']").trigger("click");
  await flushPromises();

  expect(api.search).toHaveBeenLastCalledWith(
    "游标目录", "material", "next-token", 20, {},
  );
  expect(replace).not.toHaveBeenCalled();
  expect(wrapper.text()).toContain("素材 21");
  expect(wrapper.text()).toContain("第 2 页 · 共 21 条");
  expect(wrapper.text()).toContain("第二页");
});

test("空查询浏览目录时不渲染 AI 区域", async () => {
  route.query = {};
  const wrapper = render();
  await flushPromises();
  expect(wrapper.find(".ai-answer").exists()).toBe(false);
});

test("检索无可见结果时不渲染 AI 区域", async () => {
  api.search.mockReset();
  api.search.mockResolvedValue({ ...first, items: [], total: 0 });
  const wrapper = render();
  await flushPromises();
  expect(wrapper.find(".ai-answer").exists()).toBe(false);
  expect(wrapper.text()).toContain("平台内没有命中结果");
});

test("摘要修订仅随已应用的成功响应推进", async () => {
  const wrapper = render();
  await flushPromises();
  expect(revisionOf(wrapper)).toBe(1);
  const nextFilters = { type: [], audience: [], authority: ["original"], materialType: [], tags: [], time: "" };
  wrapper.findComponent(SearchFilters).vm.$emit("update:filters", nextFilters);
  await flushPromises();
  expect(revisionOf(wrapper)).toBe(1);
  await wrapper.get("[aria-label='下一页']").trigger("click");
  await flushPromises();
  expect(revisionOf(wrapper)).toBe(2);
  expect(wrapper.get(".ai-answer-stub").attributes("data-query")).toBe("游标目录");
});

test("相同查询再次提交仍推进摘要修订", async () => {
  api.search.mockReset();
  api.search.mockResolvedValue(first);
  const wrapper = render();
  await flushPromises();
  await wrapper.get("form.search-query").trigger("submit");
  await flushPromises();
  expect(api.search).toHaveBeenCalledTimes(2);
  expect(revisionOf(wrapper)).toBe(2);
});

test("新搜索路由提交前旧结果不覆盖", async () => {
  const pending = deferred();
  api.search.mockReset().mockReturnValue(pending.promise);
  const wrapper = render();
  await flushPromises();
  replace.mockReturnValue(new Promise(() => {}));
  await wrapper.get("form.search-query input").setValue("新的查询");
  await wrapper.get("form.search-query").trigger("submit");
  pending.resolve(first);
  await flushPromises();
  expect(wrapper.text()).not.toContain("第一页");
});

test("离页后不再重试503搜索", async () => {
  vi.useFakeTimers();
  api.search.mockReset().mockRejectedValue(apiError(503, "目录同步中"));
  const wrapper = render();
  await flushPromises();
  wrapper.unmount();
  await vi.advanceTimersByTimeAsync(30_000);
  expect(api.search).toHaveBeenCalledTimes(1);
});

test("检索失败不推进修订且 AI 区域随错误态隐藏", async () => {
  const wrapper = render();
  await flushPromises();
  api.search.mockReset();
  api.search.mockRejectedValue(new Error("网络错误"));
  await wrapper.get("[aria-label='下一页']").trigger("click");
  await flushPromises();
  expect(wrapper.find(".ai-answer-stub").exists()).toBe(false);
  expect(wrapper.text()).toContain("网络错误");
});

test("摘要来源交给真实链接处理，不再滚动结果卡片", async () => {
  api.search.mockReset();
  api.search.mockResolvedValue({ ...first, items: [
    { id: "one", kind: "material", title: "同名条目" },
    { id: "c-05", kind: "case", title: "同名条目" },
  ] });
  const wrapper = render({ attachTo: document.body });
  await flushPromises();
  expect(wrapper.findComponent(SearchAIAnswerStub).props("hrefFor")).toEqual(expect.any(Function));
  expect(wrapper.find(".mixed-result").attributes("id")).toBeUndefined();
  expect(wrapper.find(".mixed-result").attributes("tabindex")).toBeUndefined();
  wrapper.unmount();
});

test("详情链接使用对应资源路由与已知案例版本", async () => {
  api.search.mockReset().mockResolvedValue({ ...first, items: [
    { id: "c-05", kind: "case", title: "案例", versionId: "cv-05", versionNumber: 2 },
    { id: "kn-1", kind: "knowledge", title: "知识" },
    { id: "mat-1", kind: "material", title: "素材" },
  ] });
  const wrapper = render();
  await flushPromises();
  const hrefFor = wrapper.findComponent(SearchAIAnswerStub).props("hrefFor");

  expect(hrefFor({ id: "c-05", kind: "case", versionId: "cv-05" })).toBe("resolved:case-public");
  expect(resolve).toHaveBeenCalledWith(expect.objectContaining({
    name: "case-public", params: { id: "c-05" },
    query: expect.objectContaining({ versionId: "cv-05", q: "游标目录", from: "search" }),
  }));
  expect(hrefFor({ id: "kn-1", kind: "knowledge" })).toBe("resolved:knowledge-detail");
  expect(hrefFor({ id: "mat-1", kind: "material" })).toBe("resolved:material-detail");
  wrapper.unmount();
});
