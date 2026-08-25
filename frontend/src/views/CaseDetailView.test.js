import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, expect, it, vi } from "vitest";
import CaseDetailView from "./CaseDetailView.vue";
import { api } from "../api.js";
import { session } from "../session.js";

vi.mock("../api.js", () => ({ api: { getPublicCase: vi.fn(), listCases: vi.fn() } }));
vi.mock("vue-router", () => ({ useRoute: () => ({ params: { id: "case-1" } }) }));

const caseRecord = {
  id: "case-1", title: "公开案例", publishedVersionId: "version-1",
  document: { type: "doc", content: [] },
};
const stubs = {
  SiteHeader: true, PublishedDocument: true, PublicAttachmentList: true,
  PublicMaterialList: true, RouterLink: { template: "<a><slot /></a>" },
};

beforeEach(() => {
  vi.clearAllMocks();
  api.getPublicCase.mockResolvedValue(caseRecord);
  api.listCases.mockResolvedValue([]);
  session.user = null;
});

async function render() {
  const wrapper = mount(CaseDetailView, { global: { stubs } });
  await flushPromises();
  return wrapper;
}

it("匿名读者看不到工作台入口", async () => {
  const wrapper = await render();

  expect(wrapper.text()).not.toContain("进入工作台");
  expect(api.listCases).not.toHaveBeenCalled();
});

it("作者看到自己的工作台入口", async () => {
  session.user = { id: "author", role: "user" };
  api.listCases.mockResolvedValue([{ id: "case-1" }]);

  expect((await render()).text()).toContain("进入工作台");
});

it("普通非作者看不到工作台入口", async () => {
  session.user = { id: "reader", role: "user" };

  expect((await render()).text()).not.toContain("进入工作台");
});

it("非作者管理员看不到工作台入口", async () => {
  session.user = { id: "admin", role: "admin" };

  expect((await render()).text()).not.toContain("进入工作台");
});
