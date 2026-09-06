import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";
import AdminTagCatalogView from "./AdminTagCatalogView.vue";
import { api } from "../api.js";

vi.mock("../api.js", () => ({
  api: {
    listTagGroups: vi.fn(),
    createTagGroup: vi.fn(),
    updateTagGroup: vi.fn(),
    deleteTagGroup: vi.fn(),
    createTag: vi.fn(),
    updateTag: vi.fn(),
    deleteTag: vi.fn(),
  },
}));

const seeded = [
  { id: "g1", name: "思政元素", requiredForSubmission: false, sortKey: 0, tags: [
    { id: "t1", groupId: "g1", name: "科学家精神", sortKey: 0 },
  ] },
];

function render() {
  return mount(AdminTagCatalogView, {
    global: { stubs: { SiteHeader: true, RouterLink: true } },
  });
}

async function loadContract() {
  const view = render();
  await flushPromises();
  expect(view.text()).toContain("思政元素");
  expect(view.text()).toContain("科学家精神");
}

async function createGroupContract() {
  api.createTagGroup.mockResolvedValue({});
  const view = render();
  await flushPromises();
  await view.get(".tag-group-create input").setValue("学科");
  await view.get(".tag-group-create").trigger("submit");
  await flushPromises();
  expect(api.createTagGroup).toHaveBeenCalledWith({ name: "学科" }, "");
  expect(api.listTagGroups).toHaveBeenCalledTimes(2);
}

async function requiredToggleContract() {
  api.updateTagGroup.mockResolvedValue({});
  const view = render();
  await flushPromises();
  await view.get(".tag-group header label input[type='checkbox']").setValue(true);
  await flushPromises();
  expect(api.updateTagGroup).toHaveBeenCalledWith("g1", { requiredForSubmission: true }, "");
}

async function usedTagConflictContract() {
  vi.stubGlobal("confirm", vi.fn(() => true));
  api.deleteTag.mockRejectedValue(new Error("标签已被案例使用，不能删除"));
  const view = render();
  await flushPromises();
  await view.get("[aria-label='删除标签：科学家精神']").trigger("click");
  await flushPromises();
  expect(view.get(".tag-catalog-error").text()).toBe("标签已被案例使用，不能删除");
  vi.unstubAllGlobals();
}

beforeEach(() => {
  vi.clearAllMocks();
  api.listTagGroups.mockResolvedValue(seeded);
});

describe("标签目录管理", () => {
  it("加载并展示分组与标签", loadContract);
  it("新建标签组后刷新目录", createGroupContract);
  it("切换投稿必填", requiredToggleContract);
  it("删除被引用标签时展示服务端冲突原因", usedTagConflictContract);
});
