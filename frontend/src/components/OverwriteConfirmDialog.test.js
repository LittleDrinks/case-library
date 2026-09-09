import { mount } from "@vue/test-utils";
import { expect, it } from "vitest";
import OverwriteConfirmDialog from "./OverwriteConfirmDialog.vue";

function render(overrides = {}) {
  return mount(OverwriteConfirmDialog, {
    props: {
      open: true, versionLabel: "v2 · 修改后重投", busy: false, error: "", ...overrides,
    },
    global: { stubs: { teleport: true } },
  });
}

it("覆盖警告写明内容替换、旧批注清除且其他版本不受影响", () => {
  const wrapper = render();
  const text = wrapper.get('[role="dialog"]').text();
  expect(text).toContain("覆盖当前教师稿");
  expect(text).toContain("v2 · 修改后重投");
  expect(text).toContain("现有批注将被清除");
  expect(text).toContain("其他历史版本不受影响");
});

it("取消只发 cancel，不发 confirm", async () => {
  const wrapper = render();
  await wrapper.get('button[aria-label="取消覆盖"]').trigger("click");
  expect(wrapper.emitted("cancel")).toHaveLength(1);
  expect(wrapper.emitted("confirm")).toBeUndefined();
});

it("确认发 confirm；处理中禁用两个按钮", async () => {
  const wrapper = render();
  await wrapper.get('button[aria-label="确认覆盖"]').trigger("click");
  expect(wrapper.emitted("confirm")).toHaveLength(1);

  const busy = render({ busy: true });
  expect(busy.get('button[aria-label="确认覆盖"]').attributes("disabled")).toBeDefined();
  expect(busy.get('button[aria-label="取消覆盖"]').attributes("disabled")).toBeDefined();
});
