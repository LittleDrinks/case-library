import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import WorkspaceHeader from "./WorkspaceHeader.vue";

describe("workbench AI entry", () => {
  it.each([false, true])("opens the AI panel with readOnly=%s", async (readOnly) => {
    const wrapper = mount(WorkspaceHeader, {
      props: { title: "案例", status: "草稿", saveState: "saved", editable: !readOnly, readOnly },
      global: { stubs: { RouterLink: true } },
    });
    await wrapper.get('[aria-label="AI"]').trigger("click");
    expect(wrapper.emitted("tool")).toEqual([["ai"]]);
  });
});
