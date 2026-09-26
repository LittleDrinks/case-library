import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import AssistantRail from "./AssistantRail.vue";
import { api } from "../api.js";
import { CONVERSATION_SOURCES_KEY, createConversationSources } from "../composables/useConversationSources.js";
import { REVISION_WORKBENCH_KEY } from "../composables/revisionWorkbench.js";

vi.mock("../api.js", () => ({
  api: {
    agentThread: vi.fn(), agentThreads: vi.fn(), aiSettings: vi.fn(), listSkills: vi.fn(),
    listSources: vi.fn(), caseHistory: vi.fn(), agentCancel: vi.fn(), agentDecide: vi.fn(),
    agentUndoWrite: vi.fn(), getCase: vi.fn(), getPublicCase: vi.fn(), getMaterial: vi.fn(), search: vi.fn(),
  },
}));

const props = {
  active: "ai", open: true, caseRecord: { id: "case-1", revision: 1 }, user: null,
  historyAvailable: true,
  editable: true, beforeAttachmentMutation: vi.fn(), beforeVersionMutation: vi.fn(),
  writingContext: null,
};

function render(overrides = {}) {
  return mount(AssistantRail, {
    props: { ...props, ...overrides },
    global: { stubs: {
      AgentChatPanel: true,
      CommentPanel: true, AttachmentPanel: true,
      PublicSourceList: true, VersionPanel: true, RouterLink: true,
    } },
  });
}

function renderWithRealChat(overrides = {}) {
  return mount(AssistantRail, {
    props: { ...props, ...overrides },
    global: { provide: {
      [CONVERSATION_SOURCES_KEY]: createConversationSources(),
      [REVISION_WORKBENCH_KEY]: {
        flush: () => Promise.resolve(true),
        preview: () => Promise.resolve(true),
        clearPreview() {},
        isCurrent: () => true,
        apply: () => Promise.resolve(true),
      },
    }, stubs: {
      AgentArtifactCard: true, AgentResourceTrace: true, AgentSourcePicker: true, AgentThreadList: true,
      CommentPanel: true, AttachmentPanel: true, PublicSourceList: true, VersionPanel: true, RouterLink: true,
    } },
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  api.agentThread.mockResolvedValue({ id: "thread-1", messages: [], artifacts: [], activeRun: null, latestRun: null });
  api.agentThreads.mockResolvedValue([]);
  api.aiSettings.mockResolvedValue({ configured: true, effectiveModel: "test-model" });
  api.listSkills.mockResolvedValue([]);
  api.listSources.mockResolvedValue({ entries: [] });
  api.caseHistory.mockResolvedValue({ versions: [] });
});

afterEach(() => {
  vi.unstubAllGlobals();
  document.body.innerHTML = "";
});

async function switchThroughPanels(wrapper, panel, request) {
  await wrapper.setProps({ active: "files" });
  expect(wrapper.findComponent({ name: "AttachmentPanel" }).exists()).toBe(true);
  expect(wrapper.findComponent({ name: "AgentChatPanel" }).element).toBe(panel.element);
  await wrapper.setProps({ active: "history" });
  expect(wrapper.findComponent({ name: "VersionPanel" }).exists()).toBe(true);
  await wrapper.setProps({ active: "ai", promptRequest: request });
}

const settle = () => new Promise((resolve) => setTimeout(resolve, 60));

async function openSkillPopover(wrapper) {
  await wrapper.get('[data-testid="skill-picker-toggle"]').trigger("click");
  await settle();
  return document.querySelector(".skill-popover");
}

function streamAnswer() {
  return new Response('data: {"type":"start","messageId":"message-2"}\n\ndata: [DONE]\n\n', {
    headers: { "Content-Type": "text/event-stream", "x-vercel-ai-ui-message-stream": "v1" },
  });
}

async function sendComposer(wrapper, composer) {
  await composer.setValue("用户编辑后的修订要求");
  await wrapper.get('[aria-label="发送"]').trigger("click");
}

function expectAnnotationPost(fetch) {
  const parts = JSON.parse(fetch.mock.calls[0][1].body).messages.at(-1).parts;
  expect(parts).toContainEqual({ type: "data-selection", data: { from: 9, to: 13 } });
  expect(parts).toContainEqual({ type: "data-annotation", data: { id: "an-1" } });
  expect(parts).toContainEqual({ type: "data-skill", data: { skillId: "skill-pub" } });
}

it("uses the persistent Agent chat as the only AI entry", () => {
  const wrapper = render();
  expect(wrapper.findComponent({ name: "AgentChatPanel" }).exists()).toBe(true);
  expect(wrapper.text()).toContain("AI");
  expect(wrapper.text()).not.toContain("对话");
});

it("keeps AI and attachments on the rail without an annotation entry", async () => {
  const wrapper = render({ active: "files" });
  expect(wrapper.find('[aria-label="批注"]').exists()).toBe(false);
  await wrapper.get('[aria-label="AI"]').trigger("click");
  expect(wrapper.emitted("select")).toEqual([["ai"]]);
  await wrapper.setProps({ active: "files" });
  expect(wrapper.text()).toContain("附件");
});

it("places collapse first and toggles the active panel like the confirmed workbench", async () => {
  const wrapper = render();
  const collapse = wrapper.get(".panel-collapse-toggle");
  expect(wrapper.findAll(".assistant-tabs > button")[0].classes()).toContain("panel-collapse-toggle");

  await wrapper.get('[aria-label="AI"]').trigger("click");
  expect(wrapper.get(".assistant-rail").classes()).toContain("collapsed");
  await wrapper.get('[aria-label="AI"]').trigger("click");
  expect(wrapper.get(".assistant-rail").classes()).not.toContain("collapsed");

  await wrapper.get('[aria-label="历史版本"]').trigger("click");
  await wrapper.setProps({ active: "history" });
  await wrapper.get('[aria-label="历史版本"]').trigger("click");
  expect(wrapper.get(".assistant-rail").classes()).toContain("collapsed");
  await collapse.trigger("click");
  expect(wrapper.get(".assistant-rail").classes()).not.toContain("collapsed");
});

it("opens the selected panel on the first click while the drawer is closed", async () => {
  vi.stubGlobal("matchMedia", vi.fn().mockReturnValue({ matches: true }));
  const wrapper = render({ open: false, active: "ai" });

  await wrapper.get('[aria-label="AI"]').trigger("click");

  expect(wrapper.emitted("select")).toEqual([["ai"]]);
  expect(wrapper.get(".assistant-rail").classes()).not.toContain("collapsed");
});

it("collapses the current desktop panel on its first click", async () => {
  vi.stubGlobal("matchMedia", vi.fn().mockReturnValue({ matches: false }));
  const wrapper = render({ open: false, active: "ai" });

  await wrapper.get('[aria-label="AI"]').trigger("click");

  expect(wrapper.get(".assistant-rail").classes()).toContain("collapsed");
});

it("closes the mobile drawer when its active tab is clicked and reopens on the next click", async () => {
  vi.stubGlobal("matchMedia", vi.fn().mockReturnValue({ matches: true }));
  const wrapper = render({ open: true, active: "ai" });
  await wrapper.get('[aria-label="AI"]').trigger("click");
  expect(wrapper.emitted("toggle")).toHaveLength(1);
  expect(wrapper.emitted("select")).toBeUndefined();
  await wrapper.setProps({ open: false });
  await wrapper.get('[aria-label="AI"]').trigger("click");
  expect(wrapper.emitted("select")).toEqual([["ai"]]);
  expect(wrapper.classes()).not.toContain("collapsed");
  wrapper.unmount();
});

it("keeps the AI draft while switching through integrated rail panels", async () => {
  vi.stubGlobal("fetch", vi.fn());
  const wrapper = renderWithRealChat();
  await flushPromises();
  const panel = wrapper.findComponent({ name: "AgentChatPanel" });
  await wrapper.get('[aria-label="向 AI 提问"]').setValue("已有问题");
  const request = { text: "请按批注修订" };
  await switchThroughPanels(wrapper, panel, request);
  expect(wrapper.get('[aria-label="向 AI 提问"]').element.value).toBe("已有问题\n\n请按批注修订");
  expect(fetch).not.toHaveBeenCalled();
  wrapper.unmount();
});

it("sends annotation context through the real rail chat after editable prefill", async () => {
  const fetch = vi.fn().mockResolvedValue(streamAnswer());
  vi.stubGlobal("fetch", fetch);
  api.listSkills.mockResolvedValue([{ id: "skill-pub", version: "v1", name: "思政案例生成", description: "按模板生成教学案例" }]);
  const wrapper = renderWithRealChat({ writingContext: { annotationId: "an-1", from: 9, to: 13, sameBlock: true, quote: "第二段原文" }, promptRequest: { text: "请根据批注修订选中的正文" } });
  await flushPromises();
  const composer = wrapper.get('[aria-label="向 AI 提问"]');
  expect(fetch).not.toHaveBeenCalled();
  expect(composer.element.value).toContain("请根据批注修订选中的正文");
  const panel = await openSkillPopover(wrapper);
  panel.querySelector('[data-testid="skill-option"]').click();
  await flushPromises();
  await sendComposer(wrapper, composer);
  await vi.waitFor(() => expect(fetch).toHaveBeenCalled());
  expectAnnotationPost(fetch);
  wrapper.unmount();
});

it("uses the read-only rail for public discussion and资料", () => {
  const wrapper = render({ readOnly: true, user: { id: "user-1" }, active: "ai" });
  expect(wrapper.findComponent({ name: "AgentChatPanel" }).props("readOnly")).toBe(true);
  expect(wrapper.get('[aria-label="历史版本"]').isVisible()).toBe(true);
  expect(wrapper.find('[aria-label="批注"]').exists()).toBe(false);
});

it("requires login before opening a private reader discussion", () => {
  const wrapper = render({ readOnly: true, active: "ai" });
  expect(wrapper.findComponent({ name: "AgentChatPanel" }).exists()).toBe(false);
  expect(wrapper.findComponent({ name: "RouterLink" }).exists()).toBe(true);
});

it("does not expose a writable AI thread on a historical version", () => {
  const wrapper = render({
    historical: true, readOnly: true, user: { id: "user-1" }, active: "ai",
  });
  expect(wrapper.findComponent({ name: "AgentChatPanel" }).exists()).toBe(false);
  expect(wrapper.text()).toContain("恢复此版本");
});

it("keeps review chat private to review mode without an annotation entry", () => {
  const wrapper = render({ review: true, user: { id: "admin-1" }, active: "ai" });
  const panel = wrapper.findComponent({ name: "AgentChatPanel" });
  expect(panel.props("review")).toBe(true);
  expect(wrapper.find('[aria-label="批注"]').exists()).toBe(false);
});

it("exposes the fourth history entry and forwards manual version creation", () => {
  const wrapper = render({ active: "history" });
  const panel = wrapper.findComponent({ name: "VersionPanel" });
  expect(wrapper.text()).toContain("历史");
  const version = { id: "cv-4", number: 4 };
  panel.vm.$emit("version-created", version);
  expect(wrapper.emitted("version-created")).toEqual([[version]]);
});

it("forwards source citation inserts from the attachment panel", () => {
  const wrapper = render({ active: "files" });
  const row = { sourceType: "case", id: "src-1", number: 1, title: "来源" };
  wrapper.findComponent({ name: "AttachmentPanel" }).vm.$emit("insert-citation", row);
  expect(wrapper.emitted("insert-citation")).toEqual([[row]]);
});
