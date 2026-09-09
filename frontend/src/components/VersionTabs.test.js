import { mount } from "@vue/test-utils";
import { expect, it } from "vitest";
import VersionTabs from "./VersionTabs.vue";

const tabs = [
  { id: "cv-1", label: "v1 · 首次提交" },
  { id: "cv-2", label: "v2 · 修改后重投" },
];

function render(overrides = {}) {
  return mount(VersionTabs, { props: { tabs, active: "draft", ...overrides } });
}

it("首 Tab 固定为当前教师稿并默认选中", () => {
  const wrapper = render();
  const draft = wrapper.get("button.draft-tab");
  expect(draft.attributes("aria-selected")).toBe("true");
  expect(draft.text()).toContain("当前教师稿");
  expect(wrapper.findAll(".version-tab-chip")).toHaveLength(2);
});

it("切换与关闭版本 Tab 只发事件，不改 Tab 数据", async () => {
  const wrapper = render({ active: "cv-2" });
  await wrapper.get('button[aria-label="关闭 v1 · 首次提交"]').trigger("click");
  await wrapper.get('button[aria-label="v1 · 首次提交"]').trigger("click");
  expect(wrapper.emitted("close")).toEqual([["cv-1"]]);
  expect(wrapper.emitted("select")).toEqual([["cv-1"]]);
  expect(wrapper.findAll(".version-tab-chip")).toHaveLength(2);
});

it("覆盖入口只在只读版本 Tab 激活时出现", async () => {
  const draft = render();
  expect(draft.find("button.overwrite-entry").exists()).toBe(false);
  const version = render({ active: "cv-1" });
  expect(version.get("button.overwrite-entry").text()).toContain("覆盖当前教师稿");
  await version.get("button.overwrite-entry").trigger("click");
  expect(version.emitted("overwrite")).toHaveLength(1);
});

it("没有可打开的版本时只显示固定的教师稿 Tab", () => {
  const wrapper = render({ tabs: [] });
  expect(wrapper.findAll('[role="tab"]')).toHaveLength(1);
});
