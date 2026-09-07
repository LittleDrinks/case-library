import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, expect, it, vi } from "vitest";
import AgentSourcePicker from "./AgentSourcePicker.vue";
import { api } from "../api.js";
import { session } from "../session.js";

vi.mock("../api.js", () => ({
  api: {
    listSources: vi.fn(), search: vi.fn(), addCaseSource: vi.fn(),
    mountCaseMaterial: vi.fn(), getCase: vi.fn(),
  },
}));

const entries = { entries: [{ sourceType: "case", id: "src-1", title: "来源一" }] };

function mountPicker(selected = []) {
  return mount(AgentSourcePicker, {
    props: { caseId: "case-1", revision: 3, selected },
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  session.csrfToken = "csrf";
  api.listSources.mockResolvedValue(structuredClone(entries));
  api.getCase.mockResolvedValue({ id: "case-1", revision: 4 });
});

it("selects and removes compact source chips", async () => {
  const wrapper = mountPicker();
  await flushPromises();
  await wrapper.get(".agent-source-picker-toggle").trigger("click");
  await wrapper.get(".agent-source-option input").setValue(true);
  expect(wrapper.emitted("update:selected")[0][0][0].id).toBe("src-1");
  await wrapper.setProps({ selected: [entries.entries[0]] });
  await wrapper.get('[aria-label="移除来源一"]').trigger("click");
  expect(wrapper.emitted("update:selected").at(-1)[0]).toEqual([]);
});

it("adds a searched case only after the explicit confirmation button", async () => {
  api.search.mockResolvedValue({ items: [{ kind: "case", id: "case-9", title: "新来源" }] });
  api.addCaseSource.mockResolvedValue({});
  const wrapper = mountPicker();
  await flushPromises();
  await wrapper.get(".agent-source-picker-toggle").trigger("click");
  await wrapper.get('[aria-label="检索资料"]').setValue("新来源");
  await wrapper.get(".agent-source-search button").trigger("click");
  await flushPromises();
  expect(api.addCaseSource).not.toHaveBeenCalled();
  await wrapper.get(".agent-source-result button").trigger("click");
  await flushPromises();
  expect(api.addCaseSource).toHaveBeenCalledWith(
    "case-1", { sourceCaseId: "case-9", revision: 3 }, "csrf",
  );
  expect(wrapper.emitted("case-refreshed")[0][0].revision).toBe(4);
});
