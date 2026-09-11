import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, expect, test, vi } from "vitest";
import WorkbenchView from "./WorkbenchView.vue";
import OverwriteConfirmDialog from "../components/OverwriteConfirmDialog.vue";
import ReviewDecisionDialog from "../components/ReviewDecisionDialog.vue";
import { useConversationSources } from "../composables/useConversationSources.js";
import { api } from "../api.js";

const AssistantRailProbe = {
  name: "AssistantRailProbe",
  setup() {
    const { sources, toggle } = useConversationSources();
    return { sources, toggle };
  },
  template: `<div data-testid="conversation-probe">
    <b data-testid="probe-count">{{ sources.length }}</b>
    <button data-testid="probe-toggle" type="button" @click="toggle({ sourceType: 'case', id: 'probe-src' })">勾选</button>
    <button data-testid="probe-refresh" type="button" @click="$emit('case-refreshed', { id: 'case-1', publishedVersionId: 'pub-v2', revision: 4 })">刷新版本</button>
  </div>`,
};

function versionFixture(overrides = {}) {
  return {
    id: "cv-9", number: 1, kind: "submission", title: "首次提交",
    createdAt: "2026-09-01T08:00:00Z",
    document: { type: "doc", content: [{ type: "paragraph", content: [{ type: "text", text: "冻结版本正文" }] }] },
    metadata: { course: "思政课" },
    ...overrides,
  };
}

const VersionRailProbe = {
  name: "VersionRailProbe",
  props: { historical: Boolean },
  setup() {
    return { version: versionFixture() };
  },
  template: `<div data-testid="version-probe">
    <button data-testid="rail-open" type="button" @click="$emit('open-version', version)">打开版本</button>
  </div>`,
};

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
    agentThread: vi.fn(),
    listSources: vi.fn().mockResolvedValue({ entries: [] }),
    caseHistory: vi.fn().mockResolvedValue({ versions: [], events: [] }),
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

function render(railStub = true) {
  return mount(WorkbenchView, {
    global: {
      stubs: {
        SiteHeader: true, CanvasEditor: true, OutlinePanel: true, teleport: true,
        AssistantRail: railStub, RouterLink: { template: "<a><slot /></a>" },
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

test("「用于对话」上下文随工作台真实重挂载重建，切案例不泄漏", async () => {
  api.getCase.mockResolvedValue(caseFixture());
  const first = render(AssistantRailProbe);
  await flushPromises();
  expect(first.get('[data-testid="probe-count"]').text()).toBe("0");
  await first.get('[data-testid="probe-toggle"]').trigger("click");
  expect(first.get('[data-testid="probe-count"]').text()).toBe("1");
  first.unmount();

  const second = render(AssistantRailProbe);
  await flushPromises();
  expect(second.get('[data-testid="probe-count"]').text()).toBe("0");
  second.unmount();
});

test("读者版本变化时 provider 清理对话上下文", async () => {
  state.route.name = "case-public";
  api.getPublicCase.mockResolvedValue(caseFixture({ publicationStatus: "public", publishedVersionId: "pub-v1" }));
  const wrapper = render(AssistantRailProbe);
  await flushPromises();
  await wrapper.get('[data-testid="probe-toggle"]').trigger("click");
  expect(wrapper.get('[data-testid="probe-count"]').text()).toBe("1");
  await wrapper.get('[data-testid="probe-refresh"]').trigger("click");
  await flushPromises();
  expect(wrapper.get('[data-testid="probe-count"]').text()).toBe("0");
});

function renderWithRail(rail) {
  return mount(WorkbenchView, {
    global: {
      stubs: {
        SiteHeader: true, CanvasEditor: true, OutlinePanel: true, teleport: true,
        AssistantRail: rail, RouterLink: { template: "<a><slot /></a>" },
      },
    },
  });
}

async function renderVersionWorkbench() {
  api.getCase.mockResolvedValue(caseFixture());
  const wrapper = renderWithRail(VersionRailProbe);
  await flushPromises();
  return wrapper;
}

test("首 Tab 固定当前教师稿，历史版本以只读 Tab 打开且可关闭", async () => {
  const wrapper = await renderVersionWorkbench();
  expect(wrapper.get("button.draft-tab").text()).toContain("当前教师稿");
  expect(wrapper.get("textarea.document-title").attributes("readonly")).toBeUndefined();

  await wrapper.get('[data-testid="rail-open"]').trigger("click");
  expect(wrapper.find("textarea.document-title").exists()).toBe(false);
  expect(wrapper.text()).toContain("首次提交");
  const editor = wrapper.findComponent({ name: "CanvasEditor" });
  expect(editor.props("editable")).toBe(false);
  expect(editor.props("document")).toEqual(versionFixture().document);
  expect(wrapper.findComponent(VersionRailProbe).props("historical")).toBe(true);

  await wrapper.get('button[aria-label="关闭 v1 · 首次提交"]').trigger("click");
  expect(wrapper.get("textarea.document-title").attributes("readonly")).toBeUndefined();
});

async function openOverwriteDialog(wrapper) {
  await wrapper.get('[data-testid="rail-open"]').trigger("click");
  await wrapper.get("button.overwrite-entry").trigger("click");
  return wrapper.getComponent(OverwriteConfirmDialog);
}

test("确认覆盖调用 overwrite 接口并回首 Tab 继续编辑", async () => {
  api.lifecycleCase.mockResolvedValue({
    case: caseFixture({ revision: 9, title: "投稿标题" }), version: {}, event: {},
  });
  const wrapper = await renderVersionWorkbench();
  const dialog = await openOverwriteDialog(wrapper);
  expect(dialog.props("versionLabel")).toContain("v1 · 首次提交");
  await dialog.get('button[aria-label="确认覆盖"]').trigger("click");
  await flushPromises();

  expect(api.lifecycleCase).toHaveBeenCalledWith(
    "case-1",
    { command: "overwrite", revision: 3, targetId: "cv-9", submittedVersionId: undefined },
    "csrf-token",
  );
  expect(wrapper.get("textarea.document-title").element.value).toBe("投稿标题");
});

test("取消覆盖不发任何请求且停留在只读 Tab", async () => {
  const wrapper = await renderVersionWorkbench();
  const dialog = await openOverwriteDialog(wrapper);
  await dialog.get('button[aria-label="取消覆盖"]').trigger("click");
  await flushPromises();

  expect(api.lifecycleCase).not.toHaveBeenCalled();
  expect(wrapper.find("textarea.document-title").exists()).toBe(false);
});

test("覆盖冲突时关闭对话框、提示并回刷服务端状态", async () => {
  api.lifecycleCase.mockRejectedValue(Object.assign(new Error("案例已在其他位置更新"), { status: 409 }));
  api.getCase.mockResolvedValue(caseFixture({ revision: 7 }));
  const wrapper = await renderVersionWorkbench();
  const dialog = await openOverwriteDialog(wrapper);
  await dialog.get('button[aria-label="确认覆盖"]').trigger("click");
  await flushPromises();

  expect(wrapper.findComponent(OverwriteConfirmDialog).props("open")).toBe(false);
  expect(wrapper.text()).toContain("案例已在其他位置更新");
  expect(api.getCase).toHaveBeenCalledTimes(2);
  expect(wrapper.find("textarea.document-title").exists()).toBe(false);
  await wrapper.get("button.draft-tab").trigger("click");
  expect(wrapper.get("textarea.document-title").element.value).toBe("示例案例");
  expect(wrapper.get("textarea.document-title").attributes("readonly")).toBeUndefined();
});

test("读者模式不渲染版本 Tab 栏", async () => {
  state.route.name = "case-public";
  api.getPublicCase.mockResolvedValue(caseFixture({ publicationStatus: "public" }));
  const wrapper = renderWithRail(VersionRailProbe);
  await flushPromises();
  expect(wrapper.find("button.draft-tab").exists()).toBe(false);
});

const annotationRailStub = {
  name: "AssistantRailStub", emits: ["annotation-run"],
  template: `<button data-testid="rail-annotation-run" type="button"
    @click="$emit('annotation-run', 'thread-9')">run</button>`,
};

async function emitAnnotationRun(wrapper, threadId) {
  wrapper.getComponent(annotationRailStub).vm.$emit("annotation-run", threadId);
  await flushPromises();
}

test("annotation run finishing after panel switch refreshes the annotation history", async () => {
  vi.useFakeTimers();
  try {
    api.getCase.mockResolvedValue(caseFixture());
    api.agentThread.mockResolvedValueOnce({ id: "thread-9", activeRun: { id: "run-1" } })
      .mockResolvedValue({ id: "thread-9", activeRun: null,
        latestRun: { id: "run-1", status: "completed" } });
    const wrapper = render(annotationRailStub);
    await flushPromises();
    const loadsBefore = api.listAnnotations.mock.calls.length;
    await emitAnnotationRun(wrapper, "thread-9");
    await flushPromises();
    await vi.advanceTimersByTimeAsync(4000);
    expect(api.agentThread).toHaveBeenCalledWith("case-1", "thread-9");
    expect(api.listAnnotations.mock.calls.length).toBeGreaterThan(loadsBefore);
  } finally {
    vi.useRealTimers();
  }
});

function advanceTwoSeconds() {
  return vi.advanceTimersByTimeAsync(2000);
}

function concurrentThreadMock(finished) {
  return (_caseId, threadId) => {
    const running = threadId === "thread-a" ? !finished.threadA : !finished.threadB;
    return Promise.resolve(running
      ? { id: threadId, activeRun: { id: `run-${threadId.at(-1)}` } }
      : { id: threadId, activeRun: null,
        latestRun: { id: `run-${threadId.at(-1)}`, status: "completed" } });
  };
}

test("two concurrent annotation runs refresh independently when they finish in reverse order", async () => {
  vi.useFakeTimers();
  try {
    const finished = { threadA: false, threadB: false };
    const loadsBefore = await renderConcurrentRuns(finished);
    await advanceTwoSeconds();
    finished.threadB = true;
    await advanceTwoSeconds();
    finished.threadA = true;
    await advanceTwoSeconds();
    expect(loadsFor("thread-a")).toBeGreaterThan(1);
    expect(loadsFor("thread-b")).toBeGreaterThan(1);
    expect(api.listAnnotations.mock.calls.length).toBeGreaterThan(loadsBefore + 1);
  } finally {
    vi.useRealTimers();
  }
});

async function renderConcurrentRuns(finished) {
  api.getCase.mockResolvedValue(caseFixture());
  api.agentThread.mockImplementation(concurrentThreadMock(finished));
  const wrapper = render(annotationRailStub);
  await flushPromises();
  await emitAnnotationRun(wrapper, "thread-b");
  await emitAnnotationRun(wrapper, "thread-a");
  return api.listAnnotations.mock.calls.length;
}

function loadsFor(threadId) {
  return api.agentThread.mock.calls.filter(([, id]) => id === threadId).length;
}

function transientThreadMock() {
  return api.agentThread
    .mockResolvedValueOnce({ id: "thread-9", activeRun: { id: "run-1" } })
    .mockRejectedValueOnce(Object.assign(new Error("网络抖动"), { status: 0 }))
    .mockResolvedValue({ id: "thread-9", activeRun: null,
      latestRun: { id: "run-1", status: "completed" } });
}

test("a transient thread snapshot failure does not abandon the annotation watch", async () => {
  vi.useFakeTimers();
  try {
    api.getCase.mockResolvedValue(caseFixture());
    transientThreadMock();
    const wrapper = render(annotationRailStub);
    await flushPromises();
    const loadsBefore = api.listAnnotations.mock.calls.length;
    await emitAnnotationRun(wrapper, "thread-9");
    await vi.advanceTimersByTimeAsync(6000);
    expect(api.listAnnotations.mock.calls.length).toBeGreaterThan(loadsBefore);
  } finally {
    vi.useRealTimers();
  }
});
