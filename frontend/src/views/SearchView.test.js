import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { defineComponent, h, reactive } from "vue";
import SearchView from "./SearchView.vue";
import { api } from "../api.js";

const replace = vi.fn();
const route = reactive({ query: { q: "游标目录", kind: "material" } });
const answerClear = vi.fn();
const answerMounts = vi.fn();
const wrappers = [];

vi.mock("vue-router", () => ({
  useRoute: () => route,
  useRouter: () => ({ replace }),
}));
vi.mock("../api.js", () => ({ api: { search: vi.fn() } }));

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

const SearchAIAnswerStub = defineComponent({
  setup(_props, { expose }) {
    answerMounts();
    expose({ clear: answerClear });
    return () => h("div");
  },
});

function render() {
  const wrapper = mount(SearchView, {
    global: { stubs: {
      SiteHeader: true, SearchAIAnswer: SearchAIAnswerStub, SearchGraph: true,
      SearchFilters: true, RouterLink: true,
    } },
  });
  wrappers.push(wrapper);
  return wrapper;
}

afterEach(() => wrappers.splice(0).forEach(wrapper => wrapper.unmount()));

beforeEach(() => {
  vi.clearAllMocks();
  route.query = { q: "游标目录", kind: "material" };
  replace.mockImplementation(({ query }) => {
    route.query = query;
    return Promise.resolve();
  });
  answerClear.mockClear();
  answerMounts.mockClear();
  api.search.mockResolvedValueOnce(first).mockResolvedValueOnce(second);
});

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

test("空白查询保持目录浏览且不挂载 AI 回答", async () => {
  route.query = { q: "   " };
  const wrapper = render();
  await flushPromises();

  expect(api.search).toHaveBeenCalledWith("", "all", null, 20, {});
  expect(replace).toHaveBeenCalledWith({ name: "search", query: {} });
  expect(answerMounts).not.toHaveBeenCalled();
});

test("新请求开始时立即清除旧 AI 回答", async () => {
  let resolvePage;
  api.search.mockReset();
  api.search.mockResolvedValueOnce(first).mockImplementationOnce(() => new Promise((resolve) => {
    resolvePage = resolve;
  }));
  const wrapper = render();
  await flushPromises();
  answerClear.mockClear();
  await wrapper.get("[aria-label='下一页']").trigger("click");

  expect(answerClear).toHaveBeenCalledTimes(1);
  expect(wrapper.findComponent(SearchAIAnswerStub).exists()).toBe(false);
  resolvePage(second);
  await flushPromises();
});

test("切换图谱不会重新挂载当前 AI 回答", async () => {
  const wrapper = render();
  await flushPromises();
  await wrapper.get("button[aria-pressed='false']").trigger("click");
  await wrapper.get("button[aria-pressed='false']").trigger("click");

  expect(answerMounts).toHaveBeenCalledTimes(1);
  expect(api.search).toHaveBeenCalledTimes(1);
});
