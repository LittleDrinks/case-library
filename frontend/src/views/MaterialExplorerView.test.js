import { reactive } from "vue";
import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import MaterialExplorerView from "./MaterialExplorerView.vue";
import { api, ApiError } from "../api.js";

const { resultSearch, overviewSearch } = vi.hoisted(() => ({ resultSearch: vi.fn(), overviewSearch: vi.fn() }));

const replace = vi.fn();
const push = vi.fn();
const route = reactive({ query: { caseId: "case-1" }, fullPath: "/materials?caseId=case-1" });
const wrappers = [];

vi.mock("vue-router", () => ({
  useRoute: () => route,
  useRouter: () => ({ replace, push }),
}));
vi.mock("../api.js", () => ({
  api: {
    search: (...args) => (args[3] === 1 ? overviewSearch : resultSearch)(...args), getCase: vi.fn(), listCaseMaterials: vi.fn(),
    mountCaseMaterial: vi.fn(),
  },
  ApiError: class ApiError extends Error {},
}));
vi.mock("../session.js", () => ({
  session: { csrfToken: "csrf", user: { id: "teacher-1" } },
}));

const available = {
  id: "material-1", title: "可用素材", contentAvailable: true,
  source: "来源", materialType: "文档", authority: "original",
};
const restricted = {
  id: "material-2", title: "受限素材", contentAvailable: false,
  materialType: "文档", authority: "original",
};

function render() {
  const wrapper = mount(MaterialExplorerView, {
    global: {
      stubs: { SiteHeader: true, RouterLink: { template: "<a><slot /></a>" }, CatalogPagination: true, MaterialDownloadAction: true },
    },
  });
  wrappers.push(wrapper);
  return wrapper;
}

beforeEach(() => {
  vi.clearAllMocks();
  overviewSearch.mockResolvedValue({ total: 85, facets: { authority: [{ value: "original", count: 76 }] } });
  replace.mockReset();
  push.mockReset();
  route.query = { caseId: "case-1" };
  route.fullPath = "/materials?caseId=case-1";
  sessionStorage.clear();
  resultSearch.mockResolvedValue({
    items: [available, restricted], facets: {}, total: 2, page: 1,
    metadataIncluded: true, nextCursor: null, previousCursor: null,
  });
  api.getCase.mockResolvedValue({
    id: "case-1", ownerId: "teacher-1", workflowStatus: "draft", revision: 1,
  });
  api.listCaseMaterials.mockResolvedValue([]);
  api.mountCaseMaterial.mockResolvedValue({});
});

afterEach(() => {
  wrappers.splice(0).forEach((wrapper) => wrapper.unmount());
  vi.useRealTimers();
});

function apiError(status, message = "请求失败") {
  return Object.assign(new ApiError(message), { status });
}

function deferred() {
  let resolve;
  const promise = new Promise((done) => { resolve = done; });
  return { promise, resolve };
}

test("受限素材不可选择且批量挂载只提交可访问项", async () => {
  const wrapper = render();
  await flushPromises();

  expect(wrapper.get("[aria-label='选择受限素材']").attributes("disabled")).toBeDefined();
  await wrapper.get("[aria-label='选择可用素材']").setValue(true);
  await wrapper.get("[aria-label='加入当前案例']").trigger("click");
  await flushPromises();

  expect(api.mountCaseMaterial).toHaveBeenCalledTimes(1);
  expect(api.mountCaseMaterial).toHaveBeenCalledWith(
    "case-1", available.id, 1, "csrf",
  );
});

test("选材成功后返回原案例工作台", async () => {
  const wrapper = render();
  await flushPromises();
  await wrapper.get("[aria-label='选择可用素材']").setValue(true);
  await wrapper.get("[aria-label='加入当前案例']").trigger("click");
  await flushPromises();

  expect(push).toHaveBeenCalledWith({ name: "workbench", params: { id: "case-1" }, query: { panel: "files" } });
  expect(api.listCaseMaterials).toHaveBeenCalledTimes(2);
});

test("选材失败后留在原页并保留选择和错误", async () => {
  api.mountCaseMaterial.mockRejectedValueOnce(new Error("版本已变化"));
  const wrapper = render();
  await flushPromises();
  await wrapper.get("[aria-label='选择可用素材']").setValue(true);
  await wrapper.get("[aria-label='加入当前案例']").trigger("click");
  await flushPromises();

  expect(push).not.toHaveBeenCalled();
  expect(wrapper.get("[aria-label='选择可用素材']").element.checked).toBe(true);
  expect(wrapper.get("[role='alert']").text()).toContain("版本已变化");
});

test("素材表格为移动布局保留字段标签", async () => {
  const wrapper = render();
  await flushPromises();

  const row = wrapper.get("tbody tr");
  expect(row.get("td[data-label='素材']").text()).toContain("可用素材");
  expect(row.get("td[data-label='来源']").text()).toBe("来源");
  expect(row.get("td[data-label='类型']").text()).toBe("文档");
  expect(row.get("td[data-label='权威性']").text()).toBe("原始权威来源");
  expect(row.get("td[data-label='下载']").exists()).toBe(true);
});

function mockMaterialPages() {
  resultSearch.mockReset()
    .mockResolvedValueOnce({
      items: [available], facets: { authority: [{ value: "original", count: 51 }] },
      total: 51, page: 1, metadataIncluded: true,
      nextCursor: "next-token", previousCursor: null,
    })
    .mockResolvedValueOnce({
      items: [restricted], facets: null, total: null, page: 2,
      metadataIncluded: false, nextCursor: null, previousCursor: "previous-token",
    });
}

test("素材翻页不写 URL 并保留首屏分面与总数", async () => {
  mockMaterialPages();
  const wrapper = render();
  await flushPromises();
  wrapper.getComponent({ name: "CatalogPagination" }).vm.$emit("change", "next-token");
  await flushPromises();

  expect(resultSearch).toHaveBeenLastCalledWith("", "material", "next-token", 10, {});
  expect(replace).not.toHaveBeenCalled();
  expect(wrapper.getComponent({ name: "CatalogPagination" }).props()).toMatchObject({
    page: 2, total: 51,
  });
  expect(wrapper.text()).toContain("受限素材");
});

test("翻页清除上一页的素材选择", async () => {
  mockMaterialPages();
  const wrapper = render();
  await flushPromises();
  await wrapper.get("[aria-label='选择可用素材']").setValue(true);
  wrapper.getComponent({ name: "CatalogPagination" }).vm.$emit("change", "next-token");
  await flushPromises();

  expect(wrapper.text()).toContain("已选择 0 条");
});

test("筛选重置素材列表的分页状态和选择", async () => {
  const wrapper = render();
  await flushPromises();
  await wrapper.get("[aria-label='选择可用素材']").setValue(true);
  await wrapper.findAll("input[name='authority']")[1].trigger("change");

  expect(replace).toHaveBeenCalledWith({
    name: "materials", query: { caseId: "case-1", authority: "original" },
  });
  expect(wrapper.text()).toContain("已选择 0 条");
});

test("素材分页503后重试并显示成功结果", async () => {
  vi.useFakeTimers();
  resultSearch.mockReset().mockResolvedValueOnce(firstPage())
    .mockRejectedValueOnce(apiError(503, "目录同步中"))
    .mockResolvedValueOnce(secondPage());
  const wrapper = render();
  await flushPromises();
  wrapper.getComponent({ name: "CatalogPagination" }).vm.$emit("change", "next-token");
  await flushPromises();
  await vi.advanceTimersByTimeAsync(1000);
  await flushPromises();
  expect(wrapper.text()).toContain("受限素材");
});

test("素材分页持续503在30秒窗口后失败", async () => {
  vi.useFakeTimers();
  resultSearch.mockReset().mockResolvedValueOnce(firstPage()).mockImplementation(() => Promise.reject(apiError(503, "目录同步中")));
  const wrapper = render();
  await flushPromises();
  wrapper.getComponent({ name: "CatalogPagination" }).vm.$emit("change", "next-token");
  await flushPromises();
  await vi.advanceTimersByTimeAsync(30_000);
  await flushPromises();
  expect(resultSearch.mock.calls.length).toBe(31);
  expect(wrapper.text()).toContain("目录同步中");
});

test("素材分页非503错误立即显示", async () => {
  resultSearch.mockReset().mockResolvedValueOnce(firstPage()).mockRejectedValueOnce(apiError(500, "服务错误"));
  const wrapper = render();
  await flushPromises();
  wrapper.getComponent({ name: "CatalogPagination" }).vm.$emit("change", "next-token");
  await flushPromises();
  expect(resultSearch).toHaveBeenCalledTimes(2);
  expect(wrapper.text()).toContain("服务错误");
});

test("切换筛选后旧素材重试不再发请求或覆盖结果", async () => {
  vi.useFakeTimers();
  resultSearch.mockReset().mockResolvedValueOnce(firstPage())
    .mockRejectedValueOnce(apiError(503, "目录同步中"))
    .mockResolvedValueOnce({ ...firstPage(), items: [restricted] });
  const wrapper = render();
  await flushPromises();
  wrapper.getComponent({ name: "CatalogPagination" }).vm.$emit("change", "next-token");
  await flushPromises();
  replace.mockImplementation(({ query }) => {
    route.query = query;
    route.fullPath = `/materials?${new URLSearchParams(query)}`;
  });
  await wrapper.findAll("input[name='authority']")[1].trigger("change");
  await wrapper.vm.$nextTick(); await flushPromises();
  await vi.advanceTimersByTimeAsync(1000);
  expect(resultSearch).toHaveBeenCalledTimes(3);
  expect(wrapper.text()).toContain("受限素材");
});

test("异步路由提交前旧素材结果不覆盖", async () => {
  const pending = deferred();
  resultSearch.mockReset().mockReturnValue(pending.promise);
  const wrapper = render();
  await flushPromises();
  replace.mockReturnValue(new Promise(() => {}));
  await wrapper.findAll("input[name='authority']")[1].trigger("change");
  pending.resolve(firstPage());
  await flushPromises();
  expect(wrapper.find("tbody tr").exists()).toBe(false);
});

test("离页后不再重试503素材请求", async () => {
  vi.useFakeTimers();
  resultSearch.mockReset().mockRejectedValue(apiError(503, "目录同步中"));
  const wrapper = render();
  await flushPromises();
  wrapper.unmount();
  await vi.advanceTimersByTimeAsync(30_000);
  expect(resultSearch).toHaveBeenCalledTimes(1);
});

function firstPage() {
  return {
    items: [available], facets: {}, total: 2, page: 1,
    metadataIncluded: true, nextCursor: "next-token", previousCursor: null,
  };
}

function secondPage() {
  return {
    items: [restricted], facets: null, total: null, page: 2,
    metadataIncluded: false, nextCursor: null, previousCursor: "previous-token",
  };
}

test("工作视图数量不被当前案例或权威性筛选结果覆盖", async () => {
  api.listCaseMaterials.mockResolvedValue(Array.from({ length: 5 }, (_,i) => ({ id: `mounted-${i}` })));
  resultSearch.mockImplementation(async (_term, _kind, _cursor, _size, filters = {}) => {
    const count = filters.mountedInCaseId ? 1 : filters.authority ? 76 : 85;
    return {
      ...firstPage(), total: count,
      facets: { authority: [{ value: "original", count: count === 1 ? 1 : 76 }] },
    };
  });
  replace.mockImplementation(({ query }) => {
    route.query = query;
    route.fullPath = `/materials?${new URLSearchParams(query)}`;
  });
  const wrapper = render();
  await flushPromises();
  const buttons = wrapper.findAll(".material-filter > button");
  expect(buttons.map(button => button.get("b").text())).toEqual(["5", "76", "0", "85"]);
  await buttons[0].trigger("click");
  await flushPromises();
  expect(buttons.map(button => button.get("b").text())).toEqual(["5", "76", "0", "85"]);
  expect(wrapper.getComponent({ name: "CatalogPagination" }).props("total")).toBe(1);
  await buttons[1].trigger("click");
  await flushPromises();
  expect(buttons.map(button => button.get("b").text())).toEqual(["5", "76", "0", "85"]);
  expect(wrapper.getComponent({ name: "CatalogPagination" }).props("total")).toBe(76);
});

test("从权威视图进入当前案例候选时清除权威性条件", async () => {
  route.query = { caseId: "case-1", authority: "original" };
  route.fullPath = "/materials?caseId=case-1&authority=original";
  const wrapper = render();
  await flushPromises();
  expect(wrapper.findAll(".material-filter > button")[3].text()).toContain("85");
  await wrapper.findAll(".material-filter > button")[0].trigger("click");
  expect(replace).toHaveBeenCalledWith({ name: "materials", query: { caseId: "case-1", view: "mounted" } });
});

test("总览计数失败显示未知与重试，不冒充零或阻塞素材列表", async () => {
  overviewSearch.mockRejectedValueOnce(new Error("failed"));
  const wrapper = render();
  await flushPromises();
  expect(wrapper.findAll(".material-filter > button")[3].get("b").text()).toBe("—");
  expect(wrapper.get("tbody tr").text()).toContain("可用素材");
  await wrapper.get(".material-count-error button").trigger("click");
  await flushPromises();
  expect(wrapper.findAll(".material-filter > button")[3].get("b").text()).toBe("85");
  expect(wrapper.find(".material-count-error").exists()).toBe(false);
});
