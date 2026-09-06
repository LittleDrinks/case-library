import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, expect, test, vi } from "vitest";
import CaseDetailView from "./CaseDetailView.vue";
import { api } from "../api.js";

const route = { params: { id: "case-1" }, query: {} };

vi.mock("vue-router", () => ({ useRoute: () => route }));
vi.mock("../api.js", () => ({
  api: {
    getPublicCase: vi.fn(),
    listCaseSources: vi.fn().mockResolvedValue([]),
    listCases: vi.fn().mockResolvedValue([]),
  },
}));
vi.mock("../session.js", () => ({
  session: { csrfToken: "csrf", user: { id: "teacher-1" } },
}));

const publicCase = {
  id: "case-1", title: "公开案例", publishedVersionId: "ver-9",
  document: { type: "doc", content: [{ type: "paragraph" }] },
};

function render() {
  return mount(CaseDetailView, {
    global: {
      stubs: {
        SiteHeader: true, RouterLink: true, PublishedDocument: true,
        PublicAttachmentList: true, PublicMaterialList: true,
        PublicSourceList: true, AddSourceToCase: true,
      },
    },
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  route.query = {};
  api.getPublicCase.mockResolvedValue(publicCase);
});

test("默认读取最新发布版本并使用其来源列表", async () => {
  render();
  await flushPromises();
  expect(api.getPublicCase).toHaveBeenCalledWith("case-1", undefined);
  expect(api.listCaseSources).toHaveBeenCalledWith("case-1", "ver-9");
});

test("versionId 查询参数固定读取指定发布版本", async () => {
  route.query = { versionId: "ver-7" };
  const wrapper = render();
  await flushPromises();
  expect(api.getPublicCase).toHaveBeenCalledWith("case-1", "ver-7");
  expect(api.listCaseSources).toHaveBeenCalledWith("case-1", "ver-7");
  expect(wrapper.get(".version-pin-banner").text()).toContain("固定的发布版本");
});

test("固定版本不可读时展示错误而不回退到最新版本", async () => {
  route.query = { versionId: "ver-x" };
  api.getPublicCase.mockRejectedValue(new Error("该版本不可访问"));
  const wrapper = render();
  await flushPromises();
  expect(wrapper.get("[role='alert']").text()).toContain("该版本不可访问");
  expect(api.getPublicCase).toHaveBeenCalledTimes(1);
});
