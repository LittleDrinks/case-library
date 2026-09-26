import { mount } from "@vue/test-utils";
import { afterEach, describe, expect, it } from "vitest";
import CaseTagPicker from "./CaseTagPicker.vue";

const groups = [
  { id: "g1", name: "课程", requiredForSubmission: true, enabled: true, sortKey: 0, tags: [
    { id: "t1", groupId: "g1", name: "自然辩证法概论", sortKey: 0, enabled: true },
  ] },
  { id: "g2", name: "思政元素", requiredForSubmission: false, enabled: true, sortKey: 1, tags: [
    { id: "t2", groupId: "g2", name: "科学家精神", sortKey: 0, enabled: true },
    { id: "t3", groupId: "g2", name: "劳动教育", sortKey: 1, enabled: false },
  ] },
];

const mounted = [];

afterEach(() => {
  while (mounted.length) mounted.pop().unmount();
});

function wrapper(extra = {}, options = {}) {
  const view = mount(CaseTagPicker, {
    props: { tagIds: [], groups, editable: true, ...extra },
    ...options,
  });
  mounted.push(view);
  return view;
}

async function groupedMultiselectContract() {
  const view = wrapper({ tagIds: ["t2"] });
  await view.get(".case-tag-editor > button").trigger("click");
  expect(view.text()).toContain("投稿必填");
  await view.get(".case-tag-popover fieldset input[type='checkbox']").setValue(true);
  expect(view.emitted("update:tagIds")[0][0]).toEqual(["t2", "t1"]);
  await view.get(".case-tag-popover").trigger("click");
  expect(view.find(".case-tag-popover").exists()).toBe(true);
}

async function chipRemovalContract() {
  const view = wrapper({ tagIds: ["t1", "t2"] });
  await view.get("[aria-label='移除标签：自然辩证法概论']").trigger("click");
  expect(view.emitted("update:tagIds")[0][0]).toEqual(["t2"]);
}

function readonlyContract() {
  const view = wrapper({ tagIds: ["t2"], editable: false });
  expect(view.text()).toContain("科学家精神");
  expect(view.find(".case-tag-editor").exists()).toBe(false);
}

async function errorRetryContract() {
  const view = wrapper({ groups: [], error: "标签目录加载失败" });
  await view.get(".case-tags-state button").trigger("click");
  expect(view.emitted("retry")).toHaveLength(1);
}

async function disabledTagContract() {
  const view = wrapper({ tagIds: ["t3"] });
  await view.get(".case-tag-editor > button").trigger("click");
  const options = view.findAll(".case-tag-popover label").map((label) => label.text());
  expect(options).toEqual(["自然辩证法概论", "科学家精神"]);
  expect(view.get("[aria-label='案例标签']").text()).toContain("劳动教育");
}

function unknownTagContract() {
  const view = wrapper({ tagIds: ["t2", "tag-ghost"], editable: false });
  const chips = view.get("[aria-label='案例标签']").text();
  expect(chips).toContain("科学家精神");
  expect(chips).not.toContain("tag-ghost");
}

async function readonlyErrorRetryContract() {
  const view = wrapper({ tagIds: ["t2"], groups: [], editable: false, error: "标签目录加载失败" });
  await view.get(".case-tags-state button").trigger("click");
  expect(view.emitted("retry")).toHaveLength(1);
}

async function outsideClickClosesWithoutTakingFocus() {
  const view = wrapper();
  const trigger = view.get(".case-tag-editor > button");
  const outside = document.createElement("button");
  document.body.appendChild(outside);
  try {
    await trigger.trigger("click");
    outside.focus();
    outside.click();
    await view.vm.$nextTick();
    expect(trigger.attributes("aria-expanded")).toBe("false");
    expect(document.activeElement).toBe(outside);
  } finally {
    outside.remove();
  }
}

async function escapeClosesAndReturnsFocus() {
  const view = wrapper({}, { attachTo: document.body });
  const trigger = view.get(".case-tag-editor > button");
  await trigger.trigger("click");
  const search = view.get(".case-tag-popover input[type='search']");
  search.element.focus();
  const event = new KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true });
  search.element.dispatchEvent(event);
  await view.vm.$nextTick();
  expect(trigger.attributes("aria-expanded")).toBe("false");
  expect(document.activeElement).toBe(trigger.element);
  expect(event.defaultPrevented).toBe(true);
}

describe("案例标签设置", () => {
  it("按目录分组多选并回传完整标签集合", groupedMultiselectContract);
  it("已选标签可通过 chip 移除", chipRemovalContract);
  it("只读形态展示标签但不提供编辑入口", readonlyContract);
  it("目录加载失败展示错误与重试", errorRetryContract);
  it("停用标签不进入候选，已选停用标签仍回显", disabledTagContract);
  it("无法解析的条目不把内部 ID 当作标签名称", unknownTagContract);
  it("只读目录加载失败仍提供重试", readonlyErrorRetryContract);
  it("点击外部关闭面板且不夺回外部焦点", outsideClickClosesWithoutTakingFocus);
  it("Escape 关闭面板并将焦点交还触发按钮", escapeClosesAndReturnsFocus);
});
