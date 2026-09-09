import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import AgentSourcePicker from "./AgentSourcePicker.vue";
import { CONVERSATION_SOURCES_KEY, createConversationSources } from "../composables/useConversationSources.js";
import { api } from "../api.js";

vi.mock("../api.js", () => ({
  api: { listSources: vi.fn() },
}));

const entries = { entries: [{ sourceType: "case", id: "src-1", title: "来源一" }] };
let wrapper;
let store;

function mountPicker(overrides = {}) {
  wrapper = mount(AgentSourcePicker, {
    props: { caseId: "case-1", ...overrides },
    global: { provide: { [CONVERSATION_SOURCES_KEY]: store } },
    attachTo: document.body,
  });
  return wrapper;
}

async function openPicker() {
  await wrapper.get('[data-testid="agent-source-picker-toggle"]').trigger("click");
  await new Promise((resolve) => setTimeout(resolve, 60));
  return document.querySelector(".source-popover");
}

afterEach(() => {
  wrapper?.unmount();
  wrapper = undefined;
  document.body.innerHTML = "";
});

beforeEach(() => {
  vi.clearAllMocks();
  store = createConversationSources();
  api.listSources.mockResolvedValue(structuredClone(entries));
});

it("opens a searchable popover and toggles sources through the shared store", async () => {
  mountPicker();
  await flushPromises();
  const panel = await openPicker();
  expect(panel.textContent).toContain("本次对话参考资料");
  panel.querySelector('[data-testid="agent-source-option"] input').click();
  await flushPromises();
  expect(store.sources.value.map((row) => row.id)).toEqual(["src-1"]);
  expect(wrapper.get(".context-trigger .count").text()).toBe("1");
});

it("filters entries locally by the search term", async () => {
  api.listSources.mockResolvedValue({ entries: [
    { sourceType: "case", id: "src-1", title: "来源一" },
    { sourceType: "material", id: "mat-1", title: "课堂素材" },
  ] });
  mountPicker();
  await flushPromises();
  const panel = await openPicker();
  const input = panel.querySelector('[aria-label="搜索本案例资料"]');
  input.value = "素材";
  input.dispatchEvent(new Event("input"));
  await flushPromises();
  expect(panel.textContent).toContain("课堂素材");
  expect(panel.textContent).not.toContain("来源一");
  input.value = "不存在";
  input.dispatchEvent(new Event("input"));
  await flushPromises();
  expect(panel.textContent).toContain("没有匹配的资料");
});

it("readonly picker reads the fixed version without any platform search", async () => {
  mountPicker({ versionId: "v-pub-1", readOnly: true });
  await flushPromises();
  expect(api.listSources).toHaveBeenCalledWith("case-1", "v-pub-1");
  const panel = await openPicker();
  expect(panel.textContent).toContain("来源一");
});

it("clears the shared selection and reloads on version change", async () => {
  store.toggle({ sourceType: "case", id: "src-old" });
  mountPicker();
  await flushPromises();
  expect(wrapper.get(".context-trigger .count").text()).toBe("1");
  await wrapper.setProps({ versionId: "v-2" });
  await flushPromises();
  expect(api.listSources).toHaveBeenLastCalledWith("case-1", "v-2");
  expect(store.sources.value).toEqual([]);
  expect(wrapper.find(".context-trigger .count").exists()).toBe(false);
});

it("ignores a stale fixed-version response after the version changes", async () => {
  let resolveFirst;
  api.listSources.mockImplementationOnce(
    () => new Promise((resolve) => { resolveFirst = resolve; }),
  );
  mountPicker({ versionId: "v-1", readOnly: true });
  await flushPromises();
  api.listSources.mockResolvedValueOnce({
    entries: [{ sourceType: "case", id: "src-2", title: "新版来源" }],
  });
  await wrapper.setProps({ versionId: "v-2" });
  await flushPromises();
  resolveFirst({ entries: [{ sourceType: "case", id: "src-stale", title: "旧版来源" }] });
  await flushPromises();
  const panel = await openPicker();
  expect(panel.textContent).toContain("新版来源");
  expect(panel.textContent).not.toContain("旧版来源");
});

it("shows a load error with retry and clears it on success", async () => {
  api.listSources.mockRejectedValueOnce(new Error("boom"));
  mountPicker();
  await flushPromises();
  const panel = await openPicker();
  expect(panel.querySelector('[role="alert"]').textContent).toContain("资料区加载失败");
  api.listSources.mockResolvedValue(structuredClone(entries));
  panel.querySelector('[aria-label="重新加载资料"]').click();
  await flushPromises();
  expect(document.querySelector(".source-popover").textContent).toContain("来源一");
});
