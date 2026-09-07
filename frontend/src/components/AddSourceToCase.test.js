import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, expect, test, vi } from "vitest";
import AddSourceToCase from "./AddSourceToCase.vue";
import { api } from "../api.js";

vi.mock("../api.js", () => ({ api: {
  listCases: vi.fn(), createCase: vi.fn(), getCase: vi.fn(), addCaseSource: vi.fn(),
} }));
vi.mock("../session.js", () => ({ session: { csrfToken: "csrf" } }));

function render() {
  return mount(AddSourceToCase, {
    props: { sourceCaseId: "case-9", versionId: "ver-3", sourceTitle: "来源案例" },
    global: { stubs: { Teleport: true, RouterLink: true } },
  });
}

async function openDialog(wrapper) {
  await wrapper.get(".case-detail-collect").trigger("click");
  await flushPromises();
}

beforeEach(() => {
  vi.clearAllMocks();
  api.listCases.mockResolvedValue([{ id: "draft-1", title: "草稿", workflowStatus: "draft", revision: 5 }]);
  api.addCaseSource.mockResolvedValue({});
  api.createCase.mockResolvedValue({ id: "draft-new", revision: 1 });
});

test("把公开固定版本加入已有草稿", async () => {
  const wrapper = render();
  await openDialog(wrapper);
  await wrapper.get("form").trigger("submit");
  await flushPromises();
  expect(api.addCaseSource).toHaveBeenCalledWith("draft-1", {
    sourceCaseId: "case-9", versionId: "ver-3", revision: 5,
  }, "csrf");
});

test("选择新建草稿后再加入来源", async () => {
  const wrapper = render();
  await openDialog(wrapper);
  await wrapper.get("input[value='__new__']").setValue();
  await wrapper.get("form").trigger("submit");
  await flushPromises();
  expect(api.createCase).toHaveBeenCalledWith({ title: "未命名案例" }, "csrf");
  expect(api.addCaseSource).toHaveBeenCalledWith("draft-new", expect.any(Object), "csrf");
});
