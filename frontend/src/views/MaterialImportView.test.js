import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, expect, test, vi } from "vitest";
import MaterialImportView from "./MaterialImportView.vue";
import { api } from "../api.js";

vi.mock("../api.js", () => ({
  api: {
    listMaterialCandidates: vi.fn(),
    decideMaterialCandidate: vi.fn(),
    createMaterialImport: vi.fn(),
  },
}));
vi.mock("../session.js", () => ({
  session: { csrfToken: "csrf-token", user: { role: "admin" } },
}));

const candidate = {
  id: "candidate-1",
  filename: "待审核资料.txt",
  mediaType: "text/plain",
  size: 24,
  accessLevel: "campus",
  status: "candidate",
  createdBy: "admin",
  createdAt: "2026-08-13T00:00:00Z",
};
const pageWithCandidate = { page: 1, pageSize: 20, total: 1, items: [candidate] };
const emptyPage = { page: 1, pageSize: 20, total: 0, items: [] };

function render() {
  return mount(MaterialImportView, {
    global: { stubs: { SiteHeader: true } },
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  api.listMaterialCandidates.mockResolvedValue(pageWithCandidate);
  api.decideMaterialCandidate.mockResolvedValue({
    ...candidate, status: "approved", materialId: candidate.id,
  });
});

test("管理员待审核列表按服务端分页", async () => {
  api.listMaterialCandidates
    .mockResolvedValueOnce({ page: 1, pageSize: 20, total: 21, items: [candidate] })
    .mockResolvedValueOnce({ page: 2, pageSize: 20, total: 21, items: [candidate] });
  const wrapper = render();
  await flushPromises();
  expect(wrapper.text()).toContain("第 1 页，共 2 页");
  await wrapper.get("nav[aria-label='待审核素材分页'] button:last-child").trigger("click");
  await flushPromises();
  expect(api.listMaterialCandidates).toHaveBeenLastCalledWith("candidate", 2, 20);
  expect(wrapper.text()).toContain("第 2 页，共 2 页");
});

test("管理员刷新后看到候选并批准为可检索素材", async () => {
  api.listMaterialCandidates
    .mockResolvedValueOnce(pageWithCandidate).mockResolvedValueOnce(emptyPage);
  const wrapper = render();
  await flushPromises();
  expect(wrapper.get("[aria-label='素材标题：待审核资料.txt']").element.value)
    .toBe("待审核资料");
  await wrapper.get("[aria-label='素材标题：待审核资料.txt']")
    .setValue("批准后的教学素材");
  await wrapper.get("[aria-label='批准入库：待审核资料.txt']").trigger("click");
  await flushPromises();
  expect(api.decideMaterialCandidate).toHaveBeenCalledWith(
    "candidate-1",
    expect.objectContaining({ decision: "approve", title: "批准后的教学素材" }),
    "csrf-token",
  );
  expect(wrapper.text()).not.toContain("待审核资料.txt");
  expect(wrapper.get("[role='status']").text()).toContain("已批准入库");
});

test("管理员拒绝候选后待审核列表立即移除", async () => {
  api.listMaterialCandidates
    .mockResolvedValueOnce(pageWithCandidate).mockResolvedValueOnce(emptyPage);
  const wrapper = render();
  await flushPromises();
  await wrapper.get("[aria-label='拒绝候选：待审核资料.txt']").trigger("click");
  await flushPromises();
  expect(api.decideMaterialCandidate).toHaveBeenCalledWith(
    "candidate-1", { decision: "reject" }, "csrf-token",
  );
  expect(wrapper.find("[aria-label='待审核：待审核资料.txt']").exists()).toBe(false);
  expect(wrapper.get("[role='status']").text()).toContain("已拒绝");
});
