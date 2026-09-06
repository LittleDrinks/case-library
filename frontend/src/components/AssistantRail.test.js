import { mount } from "@vue/test-utils";
import { expect, it, vi } from "vitest";
import AssistantRail from "./AssistantRail.vue";

const props = {
  active: "ai", open: true, caseRecord: { id: "case-1", revision: 1 }, user: null,
  caseTitle: "案例", caseDocument: { type: "doc", content: [] },
  editable: true, beforeAttachmentMutation: vi.fn(), beforeVersionMutation: vi.fn(),
  selection: null,
};

function render(overrides = {}) {
  return mount(AssistantRail, {
    props: { ...props, ...overrides },
    global: { stubs: {
      AgentChatPanel: true,
      CommentPanel: true, AttachmentPanel: true,
      VersionPanel: true, RouterLink: true, PublicSourceList: true,
    } },
  });
}

it("keeps the chat timeline as the only product surface on the Chat tab", () => {
  const wrapper = render({ user: { id: "u-1" } });
  expect(wrapper.findComponent({ name: "AgentChatPanel" }).exists()).toBe(true);
  expect(wrapper.text()).toContain("AI");
  expect(wrapper.text()).toContain("批注");
  expect(wrapper.text()).toContain("资料");
  expect(wrapper.text()).not.toContain("附件");
});

it("keeps comments and attachments on the same assistant rail", async () => {
  const wrapper = render({ active: "comments" });
  await wrapper.get(".assistant-tabs button:nth-child(1)").trigger("click");
  expect(wrapper.emitted("select")).toEqual([["ai"]]);
  await wrapper.setProps({ active: "files", user: { id: "u-1" } });
  expect(wrapper.text()).toContain("资料");
});

it("shows the public source list for read-only visitors instead of the chat", () => {
  const wrapper = render({ active: "files", readOnly: true });
  expect(wrapper.findComponent({ name: "PublicSourceList" }).exists()).toBe(true);
  expect(wrapper.findComponent({ name: "AgentChatPanel" }).exists()).toBe(false);
});
