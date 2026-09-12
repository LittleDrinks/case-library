import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, expect, it, vi } from "vitest";
import VersionPanel from "./VersionPanel.vue";
import { api } from "../api.js";

vi.mock("../api.js", () => ({ api: { caseHistory: vi.fn(), createManualVersion: vi.fn() } }));

const versions = [
  {
    id: "cv-ai", number: 3, kind: "ai", title: "AI草稿",
    createdAt: "2026-09-03T08:00:00Z", document: { type: "doc", content: [] },
  },
  {
    id: "cv-2", number: 2, kind: "submission", title: "修改后重投",
    createdAt: "2026-09-02T08:00:00Z", document: { type: "doc", content: [] },
  },
  {
    id: "cv-1", number: 1, kind: "submission", title: "首次提交",
    createdAt: "2026-09-01T08:00:00Z", document: { type: "doc", content: [] },
  },
];

function render(overrides = {}) {
  return mount(VersionPanel, {
    props: { caseRecord: { id: "case-1", revision: 3 }, editable: true, csrfToken: "csrf", ...overrides },
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  api.caseHistory.mockResolvedValue({ versions, events: [] });
});

it("版本时间线按新到旧列出投稿版本并可打开只读 Tab", async () => {
  const wrapper = render();
  await flushPromises();
  const labels = wrapper.findAll(".version-timeline b").map((node) => node.text());
  expect(labels).toEqual(["AI版本 v3 · AI草稿", "v2 · 修改后重投", "v1 · 首次提交"]);
  await wrapper.get('button[aria-label="查看历史版本 v1 · 首次提交"]').trigger("click");
  expect(wrapper.emitted("open-version")).toEqual([[versions[2]]]);
});

it("时间线不展示内部快照，并保留普通保存不建版本说明", async () => {
  api.caseHistory.mockResolvedValue({
    versions, events: [],
    snapshots: [{ id: "cs-internal", kind: "pre_agent_write" }],
  });
  const wrapper = render();
  await flushPromises();
  expect(wrapper.text()).not.toContain("创建快照");
  expect(wrapper.text()).not.toContain("pre_agent_write");
  expect(wrapper.text()).toContain("接受 AI 建议或手动命名后会生成历史版本");
});

it("命名版本表单保存后折叠并通知工作台同步 revision", async () => {
  const created = { ...versions[0], id: "cv-manual", number: 4, kind: "manual", title: "补充教学目标" };
  api.createManualVersion.mockResolvedValue(created);
  const wrapper = render();
  await flushPromises();

  await wrapper.get('button[aria-label="新建版本"]').trigger("click");
  await wrapper.get("#version-title").setValue("补充教学目标");
  await wrapper.get(".version-create-form").trigger("submit");
  await flushPromises();

  expect(api.createManualVersion).toHaveBeenCalledWith("case-1", "补充教学目标", 3, "csrf");
  expect(wrapper.find(".version-create-form").exists()).toBe(false);
  expect(wrapper.findAll(".version-timeline b")[0].text()).toContain("补充教学目标");
  expect(wrapper.emitted("version-created")).toEqual([[created]]);
});

it("投稿版本号变化后刷新时间线", async () => {
  const wrapper = render();
  await flushPromises();
  expect(api.caseHistory).toHaveBeenCalledTimes(1);

  await wrapper.setProps({ caseRecord: { id: "case-1", versionNumber: 1 } });
  await flushPromises();
  expect(api.caseHistory).toHaveBeenCalledTimes(2);
});

it("AI版本事件触发后刷新时间线", async () => {
  const wrapper = render();
  await flushPromises();
  await wrapper.setProps({ refreshKey: 1 });
  await flushPromises();
  expect(api.caseHistory).toHaveBeenCalledTimes(2);
});
