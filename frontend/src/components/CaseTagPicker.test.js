import { mount } from "@vue/test-utils";
import { afterEach, describe, expect, it } from "vitest";
import CaseTagPicker from "./CaseTagPicker.vue";

let view;

const groups = [
  { id: "g1", name: "课程", requiredForSubmission: true, enabled: true, sortKey: 0, tags: [
    { id: "t1", groupId: "g1", name: "自然辩证法概论", sortKey: 0, enabled: true },
  ] },
  { id: "g2", name: "思政元素", requiredForSubmission: false, enabled: true, sortKey: 1, tags: [
    { id: "t2", groupId: "g2", name: "科学家精神", sortKey: 0, enabled: true },
    { id: "t3", groupId: "g2", name: "劳动教育", sortKey: 1, enabled: false },
  ] },
];

function wrapper(extra = {}) {
  view = mount(CaseTagPicker, {
    props: { tagIds: [], groups, editable: true, ...extra },
    attachTo: document.body,
  });
  return view;
}

async function openPopover(currentView) {
  await currentView.get(".case-tag-trigger").trigger("click");
  await new Promise((resolve) => setTimeout(resolve, 60));
  const popover = document.querySelector(".case-tag-popover");
  expect(popover).not.toBeNull();
  expect(currentView.element.contains(popover)).toBe(false);
  return popover;
}

async function groupedMultiselectContract() {
  const currentView = wrapper({ tagIds: ["t2"] });
  const popover = await openPopover(currentView);
  expect(popover.textContent).toContain("投稿必填");
  const checkbox = popover.querySelector("fieldset input[type='checkbox']");
  checkbox.click();
  await currentView.vm.$nextTick();
  expect(currentView.emitted("update:tagIds")[0][0]).toEqual(["t2", "t1"]);
  expect(popover.getAttribute("aria-hidden")).toBe("false");
  expect(currentView.get(".case-tag-trigger").attributes("aria-expanded")).toBe("true");
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
  const currentView = wrapper({ tagIds: ["t3"] });
  const popover = await openPopover(currentView);
  const options = [...popover.querySelectorAll("label")].map((label) => label.textContent);
  expect(options).toEqual(["自然辩证法概论", "科学家精神"]);
  expect(currentView.get("[aria-label='案例标签']").text()).toContain("劳动教育");
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
  const trigger = view.get(".case-tag-trigger");
  const outside = document.createElement("button");
  let outsideClickCount = 0;
  outside.addEventListener("click", () => outsideClickCount += 1);
  document.body.appendChild(outside);
  try {
    await openPopover(view);
    outside.focus();
    outside.click();
    await view.vm.$nextTick();
    expect(trigger.attributes("aria-expanded")).toBe("false");
    expect(outsideClickCount).toBe(1);
    expect(document.activeElement).toBe(outside);
  } finally {
    outside.remove();
  }
}

async function escapeClosesAndReturnsFocus() {
  const view = wrapper();
  const trigger = view.get(".case-tag-trigger");
  const popover = await openPopover(view);
  const search = popover.querySelector("input[type='search']");
  search.focus();
  const event = new KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true });
  search.dispatchEvent(event);
  await view.vm.$nextTick();
  expect(trigger.attributes("aria-expanded")).toBe("false");
  expect(document.activeElement).toBe(trigger.element);
  expect(event.defaultPrevented).toBe(true);
}

async function escapeClosesAfterFocusLeavesPicker() {
  const view = wrapper();
  const trigger = view.get(".case-tag-trigger");
  const outside = document.createElement("button");
  document.body.appendChild(outside);
  try {
    await openPopover(view);
    outside.focus();
    const event = new KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true });
    outside.dispatchEvent(event);
    await view.vm.$nextTick();
    expect(trigger.attributes("aria-expanded")).toBe("false");
    expect(document.activeElement).toBe(trigger.element);
    expect(event.defaultPrevented).toBe(true);
  } finally {
    outside.remove();
  }
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
  it("焦点移出面板后按 Escape 仍关闭并返回触发按钮", escapeClosesAfterFocusLeavesPicker);
});

afterEach(() => {
  view?.unmount();
  view = undefined;
  document.body.innerHTML = "";
});
