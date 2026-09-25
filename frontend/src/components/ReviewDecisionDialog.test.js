import { flushPromises, mount } from "@vue/test-utils";
import { expect, test } from "vitest";
import ReviewDecisionDialog from "./ReviewDecisionDialog.vue";

const REASONS = [
  "内容需要补充或修改",
  "事实、数据或来源需要核实",
  "格式或案例信息需要调整",
  "其他",
];

function mountDialog(props = {}, attachTo = undefined) {
  return mount(ReviewDecisionDialog, {
    props: { command: "reject", ...props },
    attachTo,
    global: { stubs: { teleport: true } },
  });
}

test("打开时将键盘焦点放到第一项退回原因", async () => {
  const wrapper = mountDialog({ command: "" }, document.body);
  await wrapper.setProps({ command: "reject" });
  await flushPromises();

  expect(wrapper.find('input[type="checkbox"]').element).toBe(document.activeElement);
  wrapper.unmount();
});

test("退回原因固定为四项，未选择原因时不能提交", async () => {
  const wrapper = mountDialog();
  const reasons = wrapper.findAll('input[type="checkbox"]');

  expect(reasons.map((input) => input.element.value)).toEqual(REASONS);
  expect(wrapper.get('button[type="submit"]').attributes("disabled")).toBeDefined();
  await wrapper.get("form").trigger("submit");
  expect(wrapper.emitted("confirm")).toBeUndefined();
});

test("可以多选原因并省略留言，失败后保留选择和留言", async () => {
  const wrapper = mountDialog();
  const reasons = wrapper.findAll('input[type="checkbox"]');
  await reasons[0].setChecked(true);
  await wrapper.findAll('input[type="checkbox"]')[2].setChecked(true);
  await wrapper.get("textarea").setValue("请核对第三节的案例信息来源。".repeat(80));
  await wrapper.get("form").trigger("submit");

  expect(wrapper.emitted("confirm")[0][0]).toEqual({
    reasonTypes: [REASONS[0], REASONS[2]],
    message: "请核对第三节的案例信息来源。".repeat(80),
  });

  await wrapper.setProps({ busy: true, error: "提交失败" });
  await wrapper.setProps({ busy: false });
  expect(wrapper.findAll('input[type="checkbox"]')[0].element.checked).toBe(true);
  expect(wrapper.findAll('input[type="checkbox"]')[2].element.checked).toBe(true);
  expect(wrapper.get("textarea").element.value).toBe("请核对第三节的案例信息来源。".repeat(80));
  expect(wrapper.get('[role="alert"]').text()).toBe("提交失败");
});

test("选择其他时留言可留空", async () => {
  const wrapper = mountDialog();
  await wrapper.get('input[type="checkbox"][value="其他"]').setValue(true);
  await wrapper.get("form").trigger("submit");

  expect(wrapper.emitted("confirm")[0][0]).toEqual({
    reasonTypes: ["其他"],
    message: undefined,
  });
});
