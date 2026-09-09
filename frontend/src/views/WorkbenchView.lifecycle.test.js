import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, expect, test, vi } from "vitest";
import WorkbenchView from "./WorkbenchView.vue";
import ReviewDecisionDialog from "../components/ReviewDecisionDialog.vue";
import { api } from "../api.js";

const state = vi.hoisted(() => ({
  route: { params: { id: "case-1" }, name: "workbench" },
  user: { id: "user-1", role: "user" },
}));

vi.mock("vue-router", () => ({ useRoute: () => state.route }));
vi.mock("../session.js", () => ({
  session: { user: state.user, csrfToken: "csrf-token" },
}));
vi.mock("../api.js", () => ({
  api: {
    getCase: vi.fn(),
    getPublicCase: vi.fn(),
    saveCase: vi.fn(),
    lifecycleCase: vi.fn(),
    listAnnotations: vi.fn().mockResolvedValue([]),
    listSources: vi.fn().mockResolvedValue({ entries: [] }),
  },
}));

const paragraph = { type: "paragraph", content: [{ type: "text", text: "正文" }] };

function caseFixture(overrides = {}) {
  return {
    id: "case-1", title: "示例案例", summary: "", revision: 3, ownerId: "user-1",
    workflowStatus: "draft", publicationStatus: "none",
    document: { type: "doc", content: [paragraph] },
    availableActions: ["submit", "snapshot", "rollback"],
    ...overrides,
  };
}

function render() {
  return mount(WorkbenchView, {
    global: {
      stubs: {
        SiteHeader: true, CanvasEditor: true, OutlinePanel: true, teleport: true,
        AssistantRail: true, RouterLink: { template: "<a><slot /></a>" },
      },
    },
  });
}

async function renderCase(overrides) {
  api.getCase.mockResolvedValue(caseFixture(overrides));
  const wrapper = render();
  await flushPromises();
  return wrapper;
}

beforeEach(() => {
  vi.clearAllMocks();
  state.route.name = "workbench";
  state.route.query = {};
  state.user = { id: "user-1", role: "user" };
});

test("草稿作者的动作按钮由服务端 availableActions 驱动", async () => {
  const wrapper = await renderCase();
  expect(wrapper.find('button[aria-label="提交审核"]').exists()).toBe(true);
  expect(wrapper.find('button[aria-label="撤回提交"]').exists()).toBe(false);
  expect(wrapper.find('button[aria-label="开始审核"]').exists()).toBe(false);
});

test("审核中作者可撤回，请求携带待审版本号", async () => {
  const wrapper = await renderCase({
    workflowStatus: "reviewing", submittedVersionId: "cv-1", availableActions: ["withdraw"],
  });
  api.lifecycleCase.mockResolvedValue({ case: caseFixture(), version: {}, event: {} });
  await wrapper.get('button[aria-label="撤回提交"]').trigger("click");
  await flushPromises();
  expect(api.lifecycleCase).toHaveBeenCalledWith(
    "case-1",
    { command: "withdraw", revision: 3, submittedVersionId: "cv-1" },
    "csrf-token",
  );
});

test("已发布作者可另开新稿并保留公开页入口", async () => {
  const wrapper = await renderCase({
    workflowStatus: "published", publicationStatus: "public",
    publishedVersionId: "cv-2", availableActions: ["reopen"],
  });
  expect(wrapper.text()).toContain("查看公开页");
  expect(wrapper.find('button[aria-label="另开新稿"]').exists()).toBe(true);
});

test("未知工作流状态不伪装成草稿", async () => {
  const wrapper = await renderCase({ workflowStatus: "future", availableActions: [] });
  expect(wrapper.get(".case-status").text()).toBe("未知状态");
});

test("审核工作台保留管理员下线隐藏版本动作", async () => {
  state.route.name = "case-review";
  state.user = { id: "admin-1", role: "admin" };
  const wrapper = await renderCase({
    ownerId: "user-1", workflowStatus: "published", publicationStatus: "hidden",
    availableActions: ["reopen", "restore"],
  });
  expect(wrapper.find('button[aria-label="下线编辑"]').exists()).toBe(true);
});

test("公开响应的 publishedVersionId 固定来源版本", async () => {
  state.route.name = "case-public";
  api.getPublicCase.mockResolvedValue(caseFixture({
    workflowStatus: "published", publicationStatus: "public", ownerId: "user-9",
    publishedVersionId: "published-2", versionId: undefined,
  }));
  const wrapper = render();
  await flushPromises();
  expect(api.listSources).toHaveBeenCalledWith("case-1", "published-2");
  expect(wrapper.findComponent({ name: "AssistantRail" }).props("versionId")).toBe("published-2");
});

test("历史阅读导出携带固定版本并使用公开接口", async () => {
  state.route.name = "case-public";
  state.route.query = { versionId: "published-1" };
  api.getPublicCase.mockResolvedValue(caseFixture({ publishedVersionId: "published-1" }));
  const wrapper = render();
  await flushPromises();
  let href;
  const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function () {
    href = this.getAttribute("href");
  });
  await wrapper.get('button[aria-label="导出 DOCX"]').trigger("click");
  expect(href).toBe("/api/cases/case-1/public/export.docx?versionId=published-1");
  click.mockRestore();
});

test("退回草稿展示最近审核意见", async () => {
  const lastReview = {
    action: "reject", reasonType: "事实待核实", summary: "第三节数据来源需标注",
    annotationIds: [], versionNumber: 2, actorId: "admin-1", createdAt: "2026-09-01T00:00:00Z",
  };
  const wrapper = await renderCase({ lastReview });
  const banner = wrapper.get(".review-return-banner");
  expect(banner.text()).toContain("退回修改（v2）：事实待核实");
  expect(banner.text()).toContain("第三节数据来源需标注");
});

test("提交校验失败展示服务端消息", async () => {
  const wrapper = await renderCase();
  api.lifecycleCase.mockRejectedValue(
    Object.assign(new Error("正文不能为空；必填标签组未选择标签：学科"), { status: 422 }),
  );
  await wrapper.get('button[aria-label="提交审核"]').trigger("click");
  await flushPromises();
  expect(wrapper.text()).toContain("正文不能为空；必填标签组未选择标签：学科");
});

test("动作冲突后自动刷新服务端状态", async () => {
  const wrapper = await renderCase({
    workflowStatus: "reviewing", submittedVersionId: "cv-1", availableActions: ["withdraw"],
  });
  api.lifecycleCase.mockRejectedValue(Object.assign(new Error("案例状态已变化"), { status: 409 }));
  api.getCase.mockResolvedValue(caseFixture({ revision: 5 }));
  await wrapper.get('button[aria-label="撤回提交"]').trigger("click");
  await flushPromises();
  expect(api.getCase).toHaveBeenCalledTimes(2);
  expect(wrapper.find('button[aria-label="提交审核"]').exists()).toBe(true);
});

test("审核模式下退回只需原因类型，不强制批注", async () => {
  state.route.name = "case-review";
  state.user = { id: "admin-1", role: "admin" };
  const wrapper = await renderCase({
    ownerId: "user-9", workflowStatus: "reviewing", submittedVersionId: "cv-1",
    availableActions: ["approve", "reject", "supplement"],
  });
  api.lifecycleCase.mockResolvedValue({ case: caseFixture(), version: {}, event: {} });
  await wrapper.get('button[aria-label="退回修改"]').trigger("click");
  await flushPromises();
  const dialog = wrapper.getComponent(ReviewDecisionDialog);
  await dialog.get("input").setValue("结构不完整");
  await dialog.get("form").trigger("submit");
  await flushPromises();
  expect(api.lifecycleCase).toHaveBeenCalledWith("case-1", rejectBody(), "csrf-token");
});

test("审核模式按钮来自服务端动作而非本地状态推断", async () => {
  state.route.name = "case-review";
  state.user = { id: "admin-1", role: "admin" };
  const wrapper = await renderCase({
    ownerId: "user-9", workflowStatus: "pending", availableActions: ["start"],
  });
  expect(wrapper.find('button[aria-label="开始审核"]').exists()).toBe(true);
  expect(wrapper.find('button[aria-label="通过发布"]').exists()).toBe(false);
});

function renderWorkbenchWithEditor() {
  return mount(WorkbenchView, {
    global: { stubs: {
      SiteHeader: true, OutlinePanel: true, teleport: true,
      AssistantRail: true, RouterLink: { template: "<a><slot /></a>" },
    } },
  });
}

async function renderDraftWorkspace() {
  api.getCase.mockResolvedValue(caseFixture());
  api.saveCase.mockResolvedValue({ revision: 4 });
  api.listSources.mockResolvedValue({ entries: [] });
  const wrapper = renderWorkbenchWithEditor();
  await flushPromises();
  return wrapper;
}

async function insertAnchorFromSources(wrapper, canvas) {
  await wrapper.get(".canvas-editor").trigger("focus");
  return canvas.vm.insertCitation({ sourceType: "case", id: "src-1", number: 1, title: "引用案例" });
}

test("引用变化保存成功后才重取资料区编号，普通正文改动不重取", async () => {
  vi.useFakeTimers();
  try {
    const wrapper = await renderDraftWorkspace();
    expect(api.listSources).toHaveBeenCalledTimes(1);
    const canvas = wrapper.findComponent({ name: "CanvasEditor" });
    expect(await insertAnchorFromSources(wrapper, canvas)).toBe("inserted");
    await vi.advanceTimersByTimeAsync(1100);
    expect(api.saveCase).toHaveBeenCalledTimes(1);
    expect(api.listSources).toHaveBeenCalledTimes(2);
    canvas.vm.editor.commands.insertContent("补充");
    await vi.advanceTimersByTimeAsync(1100);
    expect(api.saveCase).toHaveBeenCalledTimes(2);
    expect(api.listSources).toHaveBeenCalledTimes(2);
    wrapper.unmount();
  } finally {
    vi.useRealTimers();
  }
});

function rejectBody() {
  return {
    command: "reject", revision: 3, reasonType: "结构不完整", submittedVersionId: "cv-1",
  };
}
