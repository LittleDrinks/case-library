import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, expect, test, vi } from "vitest";
import { api } from "../api.js";
import AttachmentPanel from "./AttachmentPanel.vue";

vi.mock("../api.js", () => ({
  api: {
    listAttachments: vi.fn().mockResolvedValue([]),
    listCaseMaterials: vi.fn().mockResolvedValue([]),
    listCaseSources: vi.fn(),
    removeCaseSource: vi.fn().mockResolvedValue(null),
    getCase: vi.fn().mockResolvedValue({ id: "case-1" }),
    attachmentContentUrl: (id, attachmentId) => `/api/cases/${id}/attachments/${attachmentId}/content`,
  },
}));

const sourceRows = [
  {
    id: "src-1", sourceType: "case", caseId: "case-9", versionId: "ver-3",
    versionNumber: 3, title: "引用案例甲", contentAvailable: true,
    publishedAt: "2026-08-01T00:00:00Z",
  },
  {
    id: "src-2", sourceType: "case", caseId: "case-8", versionId: "ver-1",
    versionNumber: 1, title: "受限案例乙", contentAvailable: false, publishedAt: null,
  },
];

async function setup(props = {}) {
  api.listCaseSources.mockResolvedValue(sourceRows);
  const wrapper = mount(AttachmentPanel, {
    props: {
      caseRecord: { id: "case-1", ownerId: "u1" },
      user: { id: "u1", role: "teacher", csrfToken: "csrf" },
      editable: true,
      beforeMutation: vi.fn().mockResolvedValue(3),
      ...props,
    },
    global: { stubs: { RouterLink: true } },
  });
  await flushPromises();
  await wrapper.findAll(".folder-tabs button")[2].trigger("click");
  return wrapper;
}

beforeEach(() => vi.clearAllMocks());

test("来源页签按保留顺序编号并链接固定版本", async () => {
  const wrapper = await setup();
  const items = wrapper.findAll(".source-list li");
  expect(items).toHaveLength(2);
  expect(items[0].text()).toContain("〔1〕引用案例甲");
  expect(items[0].text()).toContain("v3 · 2026-08-01");
  expect(wrapper.get("[aria-label='打开来源引用案例甲']").attributes("href"))
    .toBe("#/cases/case-9?versionId=ver-3");
  expect(items[1].text()).toContain("内容按权限开放");
});

test("正文已有引用时阻止移除来源并提示先处理标记", async () => {
  const wrapper = await setup({ citedKeys: ["case:src-1"] });
  await wrapper.get("[aria-label='移除来源引用案例甲']").trigger("click");
  expect(api.removeCaseSource).not.toHaveBeenCalled();
  expect(wrapper.get(".source-conflict").text()).toContain("「引用案例甲」在正文中已有引用");
});

test("未引用来源带修订号移除并刷新案例", async () => {
  const wrapper = await setup();
  await wrapper.get("[aria-label='移除来源受限案例乙']").trigger("click");
  await flushPromises();
  expect(api.removeCaseSource).toHaveBeenCalledWith("case-1", "src-2", 3, "csrf");
  expect(api.getCase).toHaveBeenCalledWith("case-1");
  expect(wrapper.emitted("case-refreshed")).toBeTruthy();
});

test("插入引用与取消引用按光标处的引用切换", async () => {
  const wrapper = await setup();
  await wrapper.get("[aria-label='插入对引用案例甲的引用']").trigger("click");
  expect(wrapper.emitted("insert-citation")[0][0]).toMatchObject({ id: "src-1" });
  await wrapper.setProps({ activeCitation: { sourceType: "case", sourceId: "src-1" } });
  await wrapper.get("[aria-label='取消对引用案例甲的引用']").trigger("click");
  expect(wrapper.emitted("remove-citation")).toHaveLength(1);
});
