import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import AgentComposer from "./AgentComposer.vue";
import { CONVERSATION_SOURCES_KEY, createConversationSources } from "../composables/useConversationSources.js";

vi.mock("../api.js", () => ({ api: { listSources: vi.fn().mockResolvedValue({ entries: [] }) } }));

const skills = [{ id: "skill-pub", version: "v1", name: "思政案例生成", description: "按模板生成教学案例" }];
let wrapper;
let store;

function mountComposer(props = {}, overrides = {}) {
  wrapper = mount(AgentComposer, {
    props: { caseId: "case-1", configured: true, skills, catalog: "ready", ...props },
    global: { provide: { [CONVERSATION_SOURCES_KEY]: store }, ...overrides.global },
    attachTo: document.body,
  });
  return wrapper;
}

const settle = () => new Promise((resolve) => setTimeout(resolve, 60));

async function openSkillPopover() {
  await wrapper.get('[data-testid="skill-picker-toggle"]').trigger("click");
  await settle();
  return document.querySelector(".skill-popover");
}

async function chooseSkill(title) {
  const panel = await openSkillPopover();
  const option = [...panel.querySelectorAll('[data-testid="skill-option"]')]
    .find((row) => row.textContent.includes(title));
  option.click();
  await flushPromises();
}

afterEach(() => {
  wrapper?.unmount();
  wrapper = undefined;
  document.body.innerHTML = "";
});

beforeEach(() => {
  vi.clearAllMocks();
  store = createConversationSources();
});

it("sends the draft and clears it for the next message", async () => {
  mountComposer();
  await wrapper.get('[aria-label="向 AI 提问"]').setValue("生成一个案例");
  await wrapper.get('[aria-label="发送"]').trigger("click");
  expect(wrapper.emitted("send")[0][0]).toEqual({ text: "生成一个案例", skillId: "" });
  expect(wrapper.get('[aria-label="向 AI 提问"]').element.value).toBe("");
  expect(wrapper.get('[aria-label="发送"]').attributes("disabled")).toBeDefined();
});

it("inserts a removable skill block that travels with the pending message", async () => {
  mountComposer();
  await wrapper.get('[aria-label="向 AI 提问"]').setValue("生成一个案例");
  await chooseSkill("思政案例生成");
  expect(wrapper.get('[data-testid="composer-skill-block"]').text()).toContain("思政案例生成");
  await wrapper.get('[aria-label="移除 Skill 调用"]').trigger("click");
  expect(wrapper.find('[data-testid="composer-skill-block"]').exists()).toBe(false);
  await wrapper.get('[aria-label="发送"]').trigger("click");
  expect(wrapper.emitted("send")[0][0].skillId).toBe("");
});

it("sends the chosen skill once and starts the next message without it", async () => {
  mountComposer();
  await wrapper.get('[aria-label="向 AI 提问"]').setValue("生成一个案例");
  await chooseSkill("思政案例生成");
  await wrapper.get('[aria-label="发送"]').trigger("click");
  expect(wrapper.emitted("send")[0][0]).toEqual({ text: "生成一个案例", skillId: "skill-pub" });
  expect(wrapper.find('[data-testid="composer-skill-block"]').exists()).toBe(false);
  await wrapper.get('[aria-label="向 AI 提问"]').setValue("继续追问");
  await wrapper.get('[aria-label="发送"]').trigger("click");
  expect(wrapper.emitted("send")[1][0]).toEqual({ text: "继续追问", skillId: "" });
});

it("opens the same skill popover by typing a dollar trigger and strips it", async () => {
  mountComposer();
  const input = wrapper.get('[aria-label="向 AI 提问"]');
  await input.setValue("帮我 $案例");
  await settle();
  const panel = document.querySelector(".skill-popover");
  expect(panel).not.toBeNull();
  expect(panel.querySelector('[aria-label="搜索 Skill"]').value).toBe("案例");
  panel.querySelector('[data-testid="skill-option"]').click();
  await flushPromises();
  expect(wrapper.get('[aria-label="向 AI 提问"]').element.value).toBe("帮我 ");
  expect(wrapper.get('[data-testid="composer-skill-block"]').exists()).toBe(true);
});

it("filters skill options by the search term", async () => {
  mountComposer({ skills: [...skills, { id: "skill-two", version: "v2", name: "讨论题设计" }] });
  const panel = await openSkillPopover();
  const input = panel.querySelector('[aria-label="搜索 Skill"]');
  input.value = "讨论";
  input.dispatchEvent(new Event("input"));
  await flushPromises();
  const text = panel.textContent;
  expect(text).toContain("讨论题设计");
  expect(text).not.toContain("思政案例生成");
});

it("shows catalog loading, error and empty states with retry", async () => {
  mountComposer({ skills: [], catalog: "loading" });
  await openSkillPopover();
  expect(document.querySelector('[data-testid="skill-catalog-loading"]').textContent).toContain("正在加载目录");
  await wrapper.get('[data-testid="skill-picker-toggle"]').trigger("click");

  await wrapper.setProps({ catalog: "error" });
  await flushPromises();
  expect(document.querySelector('[data-testid="skill-catalog-error"]').textContent).toContain("目录加载失败");
  await document.querySelector('[data-testid="skill-catalog-retry"]').click();
  expect(wrapper.emitted("reload-catalog")).toHaveLength(1);

  await wrapper.setProps({ catalog: "ready", skills: [] });
  await flushPromises();
  expect(document.querySelector('[data-testid="skill-catalog-empty"]').textContent).toContain("暂无已发布 Skill");
});

it("keeps the reader composer free of skill controls", async () => {
  mountComposer({ readOnly: true });
  expect(wrapper.find('[data-testid="skill-picker-toggle"]').exists()).toBe(false);
  expect(wrapper.find('[data-testid="tools-placeholder"]').exists()).toBe(false);
  expect(wrapper.findAll(".capability")).toHaveLength(0);
  await wrapper.get('[aria-label="向 AI 提问"]').setValue("只读问题");
  await wrapper.get('[aria-label="发送"]').trigger("click");
  expect(wrapper.emitted("send")[0][0]).toEqual({ text: "只读问题", skillId: "" });
});

it("disables sending while unconfigured or busy and blocks empty drafts", async () => {
  mountComposer({ configured: false });
  expect(wrapper.get('[aria-label="发送"]').attributes("disabled")).toBeDefined();
  await wrapper.setProps({ configured: true });
  await wrapper.get('[aria-label="向 AI 提问"]').setValue("排队中的问题");
  expect(wrapper.get('[aria-label="发送"]').attributes("disabled")).toBeUndefined();
  await wrapper.setProps({ busy: true });
  expect(wrapper.get('[aria-label="发送"]').attributes("disabled")).toBeDefined();
  await wrapper.setProps({ busy: false });
  expect(wrapper.get('[aria-label="发送"]').attributes("disabled")).toBeUndefined();
});

it("renders no placeholder tool switches in the capability bar", async () => {
  mountComposer();
  expect(wrapper.find('[data-testid="tools-placeholder"]').exists()).toBe(false);
  expect(wrapper.findAll(".capability")).toHaveLength(1);
});

it("reflects attachment-panel conversation toggles through the provided store", async () => {
  mountComposer();
  store.toggle({ sourceType: "case", id: "src-1", title: "引用案例甲" });
  await flushPromises();
  expect(wrapper.get(".context-strip .context-chip").text()).toContain("引用案例甲");
  store.remove({ sourceType: "case", id: "src-1" });
  await flushPromises();
  expect(wrapper.find(".context-strip .context-chip").exists()).toBe(false);
});

it("resets the skill popover state when sending with the popover left open", async () => {
  mountComposer();
  const input = wrapper.get('[aria-label="向 AI 提问"]');
  await input.setValue("问题一 $案");
  await settle();
  await wrapper.get('[aria-label="发送"]').trigger("click");
  expect(wrapper.emitted("send")).toHaveLength(1);
  await wrapper.get('[data-testid="skill-picker-toggle"]').trigger("click");
  await settle();
  const panel = document.querySelector(".skill-popover");
  expect(panel.querySelector('[aria-label="搜索 Skill"]').value).toBe("");
});

it("offers clearing the writing-context chip from the strip", async () => {
  mountComposer({ writingContext: { quote: "第二段原文", sameBlock: true, from: 1, to: 5 } });
  expect(wrapper.get('[data-testid="composer-selection"]').text()).toContain("正文选区 5 字");
  await wrapper.get('[aria-label="移除正文选区"]').trigger("click");
  expect(wrapper.emitted("clear-selection")).toHaveLength(1);
});
