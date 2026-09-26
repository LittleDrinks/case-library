import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import WorkspaceHeader from "./WorkspaceHeader.vue";

describe("workbench header", () => {
  it.each([false, true])("keeps navigation, status and export with readOnly=%s", async (readOnly) => {
    const wrapper = mount(WorkspaceHeader, {
      props: { title: "案例", status: "草稿", saveState: "saved", editable: !readOnly, readOnly },
      global: { stubs: { RouterLink: true } },
    });
    expect(wrapper.get('[aria-label="返回我的案例"]').attributes("to")).toBe("/my-cases");
    expect(wrapper.get(".case-status").text()).toBe("草稿");
    expect(wrapper.find(".save-state").exists()).toBe(!readOnly);
    expect(wrapper.find('[aria-label="AI"]').exists()).toBe(false);
    await wrapper.get('[aria-label="导出 DOCX"]').trigger("click");
    expect(wrapper.emitted("export")).toHaveLength(1);
    wrapper.unmount();
  });
});
