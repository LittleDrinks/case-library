import { mount } from "@vue/test-utils";
import { expect, it, vi } from "vitest";
import AssistantRail from "./AssistantRail.vue";

const props = {
  active: "ai", open: true, caseRecord: { id: "case-1" }, user: null,
  editable: true, beforeAttachmentMutation: vi.fn(), beforeVersionMutation: vi.fn(),
  selection: null,
};

function render(overrides = {}) {
  return mount(AssistantRail, {
    props: { ...props, ...overrides },
    global: { stubs: {
      AgentChatPanel: true, CommentPanel: true, AttachmentPanel: true,
      VersionPanel: true, RouterLink: true,
    } },
  });
}

it("uses the persistent Agent Chat panel as the only AI tab", () => {
  const wrapper = render();
  expect(wrapper.findComponent({ name: "AgentChatPanel" }).exists()).toBe(true);
  expect(wrapper.text()).toContain("AI");
  expect(wrapper.text()).not.toContain("对话");
  expect(wrapper.findComponent({ name: "WritingCandidatePanel" }).exists()).toBe(false);
});

it("keeps comments and attachments on the same assistant rail", async () => {
  const wrapper = render({ active: "comments" });
  await wrapper.get(".assistant-tabs button:nth-child(1)").trigger("click");
  expect(wrapper.emitted("select")).toEqual([["ai"]]);
  await wrapper.setProps({ active: "files" });
  expect(wrapper.text()).toContain("附件");
});
