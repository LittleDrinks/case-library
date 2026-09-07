import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, expect, test, vi } from "vitest";
import MyCasesView from "./MyCasesView.vue";
import { api } from "../api.js";

const push = vi.fn();

vi.mock("vue-router", () => ({ useRouter: () => ({ push }) }));
vi.mock("../session.js", () => ({
  session: { user: { id: "u-1", role: "user" }, csrfToken: "csrf" },
}));
vi.mock("../api.js", () => ({ api: { listCases: vi.fn(), createCase: vi.fn() } }));

const lastReview = {
  action: "reject", reasonType: "证据不足", summary: "请补充数据来源",
  annotationIds: ["ca-1"], versionNumber: 2, actorId: "admin-1",
  createdAt: "2026-09-01T00:00:00Z",
};

function card(overrides = {}) {
  return {
    id: "c-1", title: "退回稿", summary: "", ownerId: "u-1",
    workflowStatus: "draft", publicationStatus: "none",
    lastReview: null, pendingAnnotationCount: 0, ...overrides,
  };
}

function mountView() {
  return mount(MyCasesView, { global: { stubs: { SiteHeader: true, teleport: true } } });
}

async function renderCases(rows) {
  api.listCases.mockResolvedValue(rows);
  const wrapper = mountView();
  await flushPromises();
  return wrapper;
}

beforeEach(() => {
  vi.clearAllMocks();
});

test("退回稿进入退回修改分组并标注退回意见", async () => {
  const wrapper = await renderCases([card({ lastReview, pendingAnnotationCount: 2 })]);
  const groups = wrapper.findAll(".my-case-group").filter(
    (node) => node.get("h2").text() === "退回修改",
  );
  expect(groups.length).toBe(1);
  expect(groups[0].findAll(".case-card").length).toBe(1);
  const notice = wrapper.get(".case-card-notice");
  expect(notice.text()).toBe("证据不足：请补充数据来源");
  expect(wrapper.text()).toContain("待处理批注 2 条");
  expect(wrapper.text()).toContain("处理退回意见");
});

test("退回待办列出原因与待处理批注，重投后回到进行中", async () => {
  const wrapper = await renderCases([card({ lastReview, pendingAnnotationCount: 1 })]);
  expect(wrapper.get(".return-todo-list").text()).toContain("请补充数据来源");
  api.listCases.mockResolvedValue([card()]);
  await wrapper.vm.loadCases();
  await flushPromises();
  expect(wrapper.find(".return-todo-list").exists()).toBe(false);
  expect(wrapper.text()).toContain("继续编辑");
});

test("普通草稿不显示退回意见", async () => {
  const wrapper = await renderCases([card({ title: "普通稿" })]);
  expect(wrapper.find(".case-card-notice").exists()).toBe(false);
  expect(wrapper.text()).toContain("普通稿");
});

test("未知状态明确报错，重试后恢复案例列表", async () => {
  const wrapper = await renderCases([card({ workflowStatus: "unrecognized" })]);
  expect(wrapper.get('[role="alert"]').text()).toContain("部分案例状态异常");
  expect(wrapper.find(".my-case-groups").exists()).toBe(false);
  api.listCases.mockResolvedValue([card({ title: "恢复的案例" })]);
  await wrapper.get('[role="alert"] button').trigger("click");
  await flushPromises();
  expect(wrapper.find('[role="alert"]').exists()).toBe(false);
  expect(wrapper.text()).toContain("恢复的案例");
});
