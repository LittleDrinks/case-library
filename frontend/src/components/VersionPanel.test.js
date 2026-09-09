import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, expect, it, vi } from "vitest";
import VersionPanel from "./VersionPanel.vue";
import { api } from "../api.js";

vi.mock("../api.js", () => ({ api: { caseHistory: vi.fn() } }));

const versions = [
  {
    id: "cv-2", number: 2, kind: "submission", title: "修改后重投",
    createdAt: "2026-09-02T08:00:00Z", document: { type: "doc", content: [] },
  },
  {
    id: "cv-1", number: 1, kind: "submission", title: "首次提交",
    createdAt: "2026-09-01T08:00:00Z", document: { type: "doc", content: [] },
  },
];

function render() {
  return mount(VersionPanel, { props: { caseRecord: { id: "case-1" } } });
}

beforeEach(() => {
  vi.clearAllMocks();
  api.caseHistory.mockResolvedValue({ versions, events: [] });
});

it("版本时间线按新到旧列出投稿版本并可打开只读 Tab", async () => {
  const wrapper = render();
  await flushPromises();
  const labels = wrapper.findAll(".version-timeline b").map((node) => node.text());
  expect(labels).toEqual(["v2 · 修改后重投", "v1 · 首次提交"]);
  await wrapper.get('button[aria-label="打开 v1 版本"]').trigger("click");
  expect(wrapper.emitted("open-version")).toEqual([[versions[1]]]);
});

it("时间线不展示内部快照，也不提供手动创建版本入口", async () => {
  api.caseHistory.mockResolvedValue({
    versions, events: [],
    snapshots: [{ id: "cs-internal", kind: "pre_agent_write" }],
  });
  const wrapper = render();
  await flushPromises();
  expect(wrapper.text()).not.toContain("创建快照");
  expect(wrapper.text()).not.toContain("pre_agent_write");
  expect(wrapper.text()).toContain("普通编辑与保存不新增版本");
});
