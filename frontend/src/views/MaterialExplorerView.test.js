import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, expect, test, vi } from "vitest";
import MaterialExplorerView from "./MaterialExplorerView.vue";
import { api } from "../api.js";

const replace = vi.fn();
const route = { query: { caseId: "case-1" }, fullPath: "/materials?caseId=case-1" };

vi.mock("vue-router", () => ({
  useRoute: () => route,
  useRouter: () => ({ replace }),
}));
vi.mock("../api.js", () => ({
  api: {
    search: vi.fn(), getCase: vi.fn(), listCaseMaterials: vi.fn(),
    mountCaseMaterial: vi.fn(),
  },
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
  return mount(MaterialExplorerView, {
    global: {
      stubs: { SiteHeader: true, RouterLink: { template: "<a><slot /></a>" }, CatalogPagination: true, MaterialDownloadAction: true },
    },
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  sessionStorage.clear();
  api.search.mockResolvedValue({
    items: [available, restricted], facets: {}, total: 2, page: 1,
    metadataIncluded: true, nextCursor: null, previousCursor: null,
  });
  api.getCase.mockResolvedValue({
    id: "case-1", ownerId: "teacher-1", workflowStatus: "draft", revision: 1,
  });
  api.listCaseMaterials.mockResolvedValue([]);
  api.mountCaseMaterial.mockResolvedValue({});
});

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
  api.search.mockReset()
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

  expect(api.search).toHaveBeenLastCalledWith("", "material", "next-token", 20, {});
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
