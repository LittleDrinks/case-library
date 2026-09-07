import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";
import AdminTagCatalogView from "./AdminTagCatalogView.vue";
import { api } from "../api.js";

vi.mock("../api.js", () => ({
  api: {
    listTagGroups: vi.fn(),
    createTagGroup: vi.fn(),
    updateTagGroup: vi.fn(),
    createTag: vi.fn(),
    updateTag: vi.fn(),
  },
}));

const seeded = [
  { id: "g1", name: "思政元素", requiredForSubmission: false, enabled: true, sortKey: 0, tags: [
    { id: "t1", groupId: "g1", name: "科学家精神", sortKey: 0, enabled: true },
  ] },
];

function render() {
  return mount(AdminTagCatalogView, {
    global: { stubs: { SiteHeader: true, RouterLink: true } },
  });
}

function headerButton(view, label) {
  return view.findAll(".tag-group > header button").find((node) => node.text().includes(label));
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
  await view.get(".tag-group header input[type='checkbox']").setValue(true);
  await flushPromises();
  expect(api.updateTagGroup).toHaveBeenCalledWith("g1", { requiredForSubmission: true }, "");
}

async function disableGroupContract() {
  api.updateTagGroup.mockResolvedValue({});
  const view = render();
  await flushPromises();
  await headerButton(view, "停用").trigger("click");
  await flushPromises();
  expect(api.updateTagGroup).toHaveBeenCalledWith("g1", { enabled: false }, "");
}

async function enableTagContract() {
  api.listTagGroups.mockResolvedValue([
    { ...seeded[0], tags: [{ ...seeded[0].tags[0], enabled: false }] },
  ]);
  api.updateTag.mockResolvedValue({});
  const view = render();
  await flushPromises();
  expect(view.text()).toContain("已停用");
  await view.get("[aria-label='启用标签：科学家精神']").trigger("click");
  await flushPromises();
  expect(api.updateTag).toHaveBeenCalledWith("t1", { enabled: true }, "");
}

async function serverErrorContract() {
  api.updateTagGroup.mockRejectedValue(new Error("名称与现有标签目录冲突"));
  const view = render();
  await flushPromises();
  await headerButton(view, "停用").trigger("click");
  await flushPromises();
  expect(view.get(".tag-catalog-error").text()).toContain("名称与现有标签目录冲突");
}

beforeEach(() => {
  vi.clearAllMocks();
  api.listTagGroups.mockResolvedValue(seeded);
});

describe("标签目录管理", () => {
  it("加载并展示分组与标签", loadContract);
  it("新建标签组后刷新目录", createGroupContract);
  it("切换投稿必填", requiredToggleContract);
  it("停用标签组走 enabled 停用接口", disableGroupContract);
  it("启用已停用标签", enableTagContract);
  it("展示服务端冲突原因", serverErrorContract);
});
