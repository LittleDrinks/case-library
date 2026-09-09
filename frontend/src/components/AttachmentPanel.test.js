import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, expect, test, vi } from "vitest";
import { api } from "../api.js";
import AttachmentPanel from "./AttachmentPanel.vue";

vi.mock("../api.js", () => ({
  api: {
    listAttachments: vi.fn().mockResolvedValue([]),
    listCaseMaterials: vi.fn().mockResolvedValue([]),
    listSources: vi.fn(),
    removeCaseSource: vi.fn().mockResolvedValue(null),
    getCase: vi.fn().mockResolvedValue({ id: "case-1" }),
    attachmentContentUrl: (id, attachmentId) => `/api/cases/${id}/attachments/${attachmentId}/content`,
  },
}));

const sourceRows = [
  {
    sourceType: "case", id: "src-1", title: "引用案例甲", number: 1, version: "v3",
    publishedAt: "2026-08-01T00:00:00Z", contentAvailable: true,
    url: "http://testserver/#/cases/case-9?versionId=ver-3",
  },
  {
    sourceType: "case", id: "src-2", title: "受限案例乙", number: 2, version: "v1",
    publishedAt: null, contentAvailable: false,
    url: "http://testserver/#/cases/case-8?versionId=ver-1",
  },
  {
    sourceType: "attachment", id: "att-1", title: "notes.txt", number: 3,
    contentAvailable: true, url: "http://testserver/api/cases/case-1/attachments/att-1/content",
  },
];

async function setup(props = {}) {
  api.listSources.mockResolvedValue({ entries: sourceRows });
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

test("来源页签统一编号并链接固定版本", async () => {
  const wrapper = await setup();
  const items = wrapper.findAll(".source-list li");
  expect(items).toHaveLength(3);
  expect(items[0].text()).toContain("〔1〕引用案例甲");
  expect(items[0].text()).toContain("v3 · 2026-08-01");
  expect(wrapper.get("[aria-label='打开来源引用案例甲']").attributes("href"))
    .toBe("http://testserver/#/cases/case-9?versionId=ver-3");
  expect(items[2].text()).toContain("〔3〕notes.txt");
});

test("无权限来源条目保留但隐藏链接并提示按权限开放", async () => {
  const wrapper = await setup();
  const items = wrapper.findAll(".source-list li");
  expect(items[1].text()).toContain("内容按权限开放");
  expect(wrapper.find("[aria-label='打开来源受限案例乙']").exists()).toBe(false);
  expect(wrapper.get("[aria-label='移除来源受限案例乙']").exists()).toBe(true);
});

test("显式移除来源调用删除接口", async () => {
  const wrapper = await setup();
  await wrapper.get("[aria-label='移除来源引用案例甲']").trigger("click");
  await flushPromises();
  expect(api.removeCaseSource).toHaveBeenCalledWith("case-1", "src-1", 3, "csrf");
});

test("插入引用是独立动作，按下不抢正文光标并携带条目", async () => {
  const wrapper = await setup();
  const insert = wrapper.get("[aria-label='插入引用引用案例甲']");
  const stolen = !insert.element.dispatchEvent(
    new MouseEvent("mousedown", { bubbles: true, cancelable: true }),
  );
  expect(stolen).toBe(true);
  await insert.trigger("click");
  expect(wrapper.emitted("insert-citation")).toEqual([[sourceRows[0]]]);
  expect(wrapper.get("[aria-label='打开来源引用案例甲']").exists()).toBe(true);
  expect(wrapper.get("[aria-label='移除来源引用案例甲']").exists()).toBe(true);
});

test("非编辑状态不提供插入引用入口", async () => {
  const wrapper = await setup({ editable: false });
  expect(wrapper.find("[aria-label='插入引用引用案例甲']").exists()).toBe(false);
  expect(wrapper.get("[aria-label='打开来源引用案例甲']").exists()).toBe(true);
});
