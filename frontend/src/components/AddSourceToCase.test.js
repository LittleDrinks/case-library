import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, expect, test, vi } from "vitest";
import { api } from "../api.js";
import AddSourceToCase from "./AddSourceToCase.vue";

vi.mock("../api.js", () => ({
  api: {
    listCases: vi.fn(),
    createCase: vi.fn(),
    getCase: vi.fn(),
    addCaseSource: vi.fn(),
  },
}));
vi.mock("../session.js", () => ({
  session: { csrfToken: "csrf", user: { id: "teacher-1" } },
}));

const drafts = [
  { id: "draft-1", title: "进行中的案例", workflowStatus: "draft", revision: 5 },
  { id: "pub-1", title: "已发布案例", workflowStatus: "published", revision: 9 },
];

function render() {
  return mount(AddSourceToCase, {
    props: { sourceCaseId: "case-9", versionId: "ver-3", sourceTitle: "来源案例" },
    global: { stubs: { Teleport: true, RouterLink: true } },
  });
}

async function openDialog(wrapper) {
  await wrapper.get(".source-collect").trigger("click");
  await flushPromises();
}

beforeEach(() => {
  vi.clearAllMocks();
  api.listCases.mockResolvedValue(drafts);
  api.addCaseSource.mockResolvedValue({});
  api.createCase.mockResolvedValue({ id: "draft-new", revision: 0 });
});

test("加入已有草稿时固定版本并携带修订号", async () => {
  const wrapper = render();
  await openDialog(wrapper);
  expect(wrapper.text()).toContain("进行中的案例");
  expect(wrapper.text()).not.toContain("已发布案例");
  await wrapper.get("button.primary").trigger("submit");
  await flushPromises();
  expect(api.addCaseSource).toHaveBeenCalledWith("draft-1", {
    sourceCaseId: "case-9", versionId: "ver-3", revision: 5,
  }, "csrf");
  expect(wrapper.text()).toContain("已将「来源案例」的固定版本加入资料区来源");
});

test("选择新建草稿时先创建再加入来源", async () => {
  const wrapper = render();
  await openDialog(wrapper);
  await wrapper.get("input[value='__new__']").setValue();
  await wrapper.get("button.primary").trigger("submit");
  await flushPromises();
  expect(api.createCase).toHaveBeenCalledWith({ title: "未命名案例" }, "csrf");
  expect(api.addCaseSource).toHaveBeenCalledWith("draft-new", {
    sourceCaseId: "case-9", versionId: "ver-3", revision: 0,
  }, "csrf");
});

test("重复加入时展示不重复提示", async () => {
  api.addCaseSource.mockRejectedValue({ status: 409, message: "conflict" });
  const wrapper = render();
  await openDialog(wrapper);
  await wrapper.get("button.primary").trigger("submit");
  await flushPromises();
  expect(wrapper.get("[role='alert']").text()).toContain("不会重复添加");
});
