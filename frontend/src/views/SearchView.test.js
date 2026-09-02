import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, expect, test, vi } from "vitest";
import SearchView from "./SearchView.vue";
import { api } from "../api.js";

const replace = vi.fn();
const route = { query: { q: "游标目录", kind: "material" } };

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

function render() {
  return mount(SearchView, {
    global: { stubs: {
      SiteHeader: true, SearchGraph: true,
      SearchFilters: true, RouterLink: true,
    } },
  });
}

beforeEach(() => {
  vi.clearAllMocks();
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
