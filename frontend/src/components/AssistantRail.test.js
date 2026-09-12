import { mount } from "@vue/test-utils";
import { expect, it, vi } from "vitest";
import AssistantRail from "./AssistantRail.vue";

const props = {
  active: "ai", open: true, caseRecord: { id: "case-1", revision: 1 }, user: null,
  historyAvailable: true,
  editable: true, beforeAttachmentMutation: vi.fn(), beforeVersionMutation: vi.fn(),
  selection: null, writingContext: null,
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

it("uses the persistent Agent chat as the only AI entry", () => {
  const wrapper = render();
  expect(wrapper.findComponent({ name: "AgentChatPanel" }).exists()).toBe(true);
  expect(wrapper.text()).toContain("AI");
  expect(wrapper.text()).not.toContain("对话");
});

it("keeps comments and attachments on the same assistant rail", async () => {
  const wrapper = render({ active: "comments" });
  await wrapper.get(".assistant-tabs button:nth-child(1)").trigger("click");
  expect(wrapper.emitted("select")).toEqual([["ai"]]);
  await wrapper.setProps({ active: "files" });
  expect(wrapper.text()).toContain("附件");
});

it("uses the read-only rail for public discussion and资料", () => {
  const wrapper = render({ readOnly: true, user: { id: "user-1" }, active: "ai" });
  expect(wrapper.findComponent({ name: "AgentChatPanel" }).props("readOnly")).toBe(true);
  expect(wrapper.findAll(".assistant-tabs > button")[1].isVisible()).toBe(true);
  expect(wrapper.findAll(".assistant-tabs > button")[2].isVisible()).toBe(false);
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

it("keeps review chat private to review mode while annotations stay available", () => {
  const wrapper = render({ review: true, user: { id: "admin-1" }, active: "ai" });
  const panel = wrapper.findComponent({ name: "AgentChatPanel" });
  expect(panel.props("review")).toBe(true);
  expect(wrapper.findAll(".assistant-tabs > button")[2].isVisible()).toBe(true);
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
