import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import WorkbenchView from "./WorkbenchView.vue";
import OverwriteConfirmDialog from "../components/OverwriteConfirmDialog.vue";
import ReviewDecisionDialog from "../components/ReviewDecisionDialog.vue";
import { useConversationSources } from "../composables/useConversationSources.js";
import { api } from "../api.js";
import { clearLocalDraft } from "../lib/localDraft.js";

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

const ActionNoticeRailProbe = {
  name: "ActionNoticeRailProbe",
  emits: ["open-version", "insert-citation"],
  setup() {
    return { version: versionFixture() };
  },
  template: `<div>
    <button data-testid="notice-open-version" type="button" @click="$emit('open-version', version)">打开版本</button>
    <button data-testid="notice-insert-citation" type="button" @click="$emit('insert-citation', { sourceType: 'case', id: 'src-1', number: 1 })">插入引用</button>
  </div>`,
};

const ActionNoticeEditorProbe = {
  name: "CanvasEditor",
  emits: ["change"],
  setup(_props, { expose }) {
    expose({ insertCitation: () => "inserted" });
  },
  template: `<div class="canvas-editor">
    <button data-testid="notice-edit" type="button" @click="$emit('change', { document: { type: 'doc', content: [] }, steps: [] })">编辑</button>
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
    createAnnotation: vi.fn(), deleteAnnotation: vi.fn(),
    agentThread: vi.fn(), aiSettings: vi.fn(), listSkills: vi.fn(),
    listSources: vi.fn().mockResolvedValue({ entries: [] }),
    caseHistory: vi.fn().mockResolvedValue({ versions: [], events: [] }),
    listTagGroups: vi.fn().mockResolvedValue([]),
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

afterEach(() => vi.unstubAllGlobals());

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
  vi.useFakeTimers();
  let wrapper;
  try {
    wrapper = await renderCase();
    api.lifecycleCase.mockRejectedValue(
      Object.assign(new Error("正文不能为空；必填标签组未选择标签：学科"), { status: 422 }),
    );
    await wrapper.get('button[aria-label="提交审核"]').trigger("click");
    await flushPromises();
    await vi.advanceTimersByTimeAsync(5000);
    expect(wrapper.get('.action-notice[role="alert"]').text())
      .toContain("正文不能为空；必填标签组未选择标签：学科");
  } finally {
    wrapper?.unmount();
    vi.useRealTimers();
  }
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
  expect(wrapper.get('.action-notice[role="alert"]').text()).toContain("案例状态已变化");
});

test("复制与插入引用共用可关闭的成功提示，旧计时器不清除新提示", async () => {
  vi.useFakeTimers();
  let wrapper;
  try {
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal("navigator", { clipboard: { writeText } });
    clearLocalDraft("user-1", "case-1");
    api.getCase.mockResolvedValue(caseFixture({ lastReview: {
      action: "reject", reasonType: "事实待核实", summary: "补充来源", versionNumber: 2,
    } }));
    api.saveCase.mockRejectedValue(Object.assign(new Error("revision conflict"), { status: 409 }));
    wrapper = mount(WorkbenchView, {
      global: { stubs: {
        SiteHeader: true, CanvasEditor: ActionNoticeEditorProbe, OutlinePanel: true,
        teleport: true, AssistantRail: ActionNoticeRailProbe,
        RouterLink: { template: "<a><slot /></a>" },
      } },
    });
    await flushPromises();
    await wrapper.get('[data-testid="notice-edit"]').trigger("click");
    await vi.advanceTimersByTimeAsync(1000);
    await wrapper.vm.$nextTick();
    expect(wrapper.get('.conflict-banner[role="alert"]').text())
      .toContain("案例已在其他页面更新");

    await wrapper.get('[data-testid="notice-open-version"]').trigger("click");
    await wrapper.get(".version-copy").trigger("click");
    await flushPromises();
    expect(writeText).toHaveBeenCalledWith("冻结版本正文");
    expect(wrapper.get('.action-notice[role="status"]').classes()).toContain("action-notice-success");
    await vi.advanceTimersByTimeAsync(2000);

    await wrapper.get("button.draft-tab").trigger("click");
    await wrapper.get('[data-testid="notice-insert-citation"]').trigger("click");
    expect(wrapper.get('.action-notice[role="status"]').text()).toContain("已插入引用〔1〕");
    await vi.advanceTimersByTimeAsync(1000);
    await wrapper.vm.$nextTick();
    expect(wrapper.find('.action-notice[role="status"]').exists()).toBe(true);
    await wrapper.get('[aria-label="关闭成功提示"]').trigger("click");
    expect(wrapper.find(".action-notice").exists()).toBe(false);

    await wrapper.get('[data-testid="notice-insert-citation"]').trigger("click");
    await vi.advanceTimersByTimeAsync(2999);
    await wrapper.vm.$nextTick();
    expect(wrapper.find('.action-notice[role="status"]').exists()).toBe(true);
    await vi.advanceTimersByTimeAsync(1);
    await wrapper.vm.$nextTick();
    expect(wrapper.find(".action-notice").exists()).toBe(false);
    expect(wrapper.get('.conflict-banner[role="alert"]').text())
      .toContain("案例已在其他页面更新");
    expect(wrapper.get(".review-return-banner").text()).toContain("事实待核实");
  } finally {
    wrapper?.unmount();
    clearLocalDraft("user-1", "case-1");
    vi.useRealTimers();
  }
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

function renderWorkbenchWithEditor(rail = true) {
  return mount(WorkbenchView, {
    global: { stubs: {
      SiteHeader: true, OutlinePanel: true, teleport: true,
      AssistantRail: rail, RouterLink: { template: "<a><slot /></a>" },
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

async function renderVersionWorkbench(overrides = {}) {
  api.getCase.mockResolvedValue(caseFixture(overrides));
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

test("非作者打开历史版本时不显示恢复入口", async () => {
  const wrapper = await renderVersionWorkbench({ ownerId: "other-user" });
  await wrapper.get('[data-testid="rail-open"]').trigger("click");
  expect(wrapper.find(".version-paper-actions .version-return").exists()).toBe(true);
  expect(wrapper.find(".version-paper-actions .version-restore").exists()).toBe(false);
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
  await dialog.get('button[aria-label="确认恢复"]').trigger("click");
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
  await dialog.get('button[aria-label="取消恢复"]').trigger("click");
  await flushPromises();

  expect(api.lifecycleCase).not.toHaveBeenCalled();
  expect(wrapper.find("textarea.document-title").exists()).toBe(false);
});

test("覆盖冲突时关闭对话框、提示并回刷服务端状态", async () => {
  api.lifecycleCase.mockRejectedValue(Object.assign(new Error("案例已在其他位置更新"), { status: 409 }));
  api.getCase.mockResolvedValue(caseFixture({ revision: 7 }));
  const wrapper = await renderVersionWorkbench();
  const dialog = await openOverwriteDialog(wrapper);
  await dialog.get('button[aria-label="确认恢复"]').trigger("click");
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
  name: "AssistantRailStub", props: ["active"], emits: ["annotation-run", "select", "mutation-state"],
  template: `<button data-testid="rail-annotation-run" type="button"
    @click="$emit('annotation-run', 'thread-9')">run</button>`,
};

const annotationEventRailStub = {
  name: "AnnotationEventRailStub", emits: ["annotations", "annotations-refresh"],
  template: `<div>
    <button data-testid="annotation-clear" type="button"
      @click="$emit('annotations', [])">clear</button>
    <button data-testid="annotation-refresh" type="button"
      @click="$emit('annotations-refresh')">refresh</button>
  </div>`,
};

function deferred() {
  let resolve;
  const promise = new Promise((done) => { resolve = done; });
  return { promise, resolve };
}

test("关闭通知使 Workbench 中迟到的批注刷新失效", async () => {
  const stale = deferred();
  api.getCase.mockResolvedValue(caseFixture());
  api.listAnnotations.mockResolvedValueOnce([]).mockReturnValueOnce(stale.promise);
  const wrapper = render(annotationEventRailStub);
  await flushPromises();
  await wrapper.get('[data-testid="annotation-refresh"]').trigger("click");
  await wrapper.get('[data-testid="annotation-clear"]').trigger("click");
  stale.resolve([{ id: "annotation-1", status: "pending" }]);
  await flushPromises();
  await new Promise((done) => setTimeout(done, 0));
  expect(wrapper.findComponent({ name: "CanvasEditor" }).props("annotations")).toEqual([]);
});

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

const readerTagCatalog = [
  {
    id: "g1", name: "思政元素", requiredForSubmission: false, enabled: true, sortKey: 0,
    tags: [{ id: "t-spirit", groupId: "g1", name: "科学家精神", sortKey: 0, enabled: true }],
  },
];

function publicCaseWithTag() {
  return caseFixture({
    publicationStatus: "public", publishedVersionId: "pub-v1", tagIds: ["t-spirit"],
  });
}

test("公开阅读页加载标签目录并以名称呈现", async () => {
  state.route.name = "case-public";
  api.getPublicCase.mockResolvedValue(publicCaseWithTag());
  api.listTagGroups.mockResolvedValue(readerTagCatalog);
  const wrapper = render();
  await flushPromises();
  expect(api.listTagGroups).toHaveBeenCalledTimes(1);
  expect(wrapper.get("[aria-label='案例标签']").text()).toContain("科学家精神");
});

test("公开阅读页标签目录失败时提示且不回退内部 ID", async () => {
  state.route.name = "case-public";
  api.getPublicCase.mockResolvedValue(publicCaseWithTag());
  api.listTagGroups.mockRejectedValue(new Error("网络错误"));
  const wrapper = render();
  await flushPromises();
  const tags = wrapper.get(".case-tags").text();
  expect(tags).toContain("标签目录加载失败");
  expect(tags).not.toContain("t-spirit");
  await wrapper.get(".case-tags-state button").trigger("click");
  expect(api.listTagGroups).toHaveBeenCalledTimes(2);
});

test("公开阅读页目录加载中不把内部 ID 当作名称", async () => {
  state.route.name = "case-public";
  api.getPublicCase.mockResolvedValue(publicCaseWithTag());
  let resolveCatalog;
  api.listTagGroups.mockReturnValue(new Promise((resolve) => { resolveCatalog = resolve; }));
  const wrapper = render();
  await flushPromises();
  const tags = wrapper.get(".case-tags").text();
  expect(tags).toContain("标签目录加载中");
  expect(tags).not.toContain("t-spirit");
  resolveCatalog(readerTagCatalog);
  await flushPromises();
  expect(wrapper.get("[aria-label='案例标签']").text()).toContain("科学家精神");
});

async function openDraftFloat(wrapper, canvas) {
  canvas.vm.$emit("selection", {
    from: 1, to: 3, quote: "正文", section: "正文", revision: 3,
  });
  canvas.vm.$emit("annotate");
  await flushPromises();
  expect(wrapper.get(".annotation-float")).toBeTruthy();
}

function emitAnnotationEntry(canvas, event) {
  if (event === "annotate") {
    canvas.vm.$emit("selection", {
      from: 1, to: 3, quote: "正文", section: "正文", revision: 3,
    });
  }
  canvas.vm.$emit(event, event === "annotation-click" ? "annotation-1" : undefined);
}

async function editOpenDraft(canvas, wrapper) {
  canvas.get(".canvas-editor p").element.textContent = "正文后缀";
  await canvas.get(".canvas-editor").trigger("input");
  await flushPromises();
  const float = wrapper.get(".annotation-float");
  await float.get('[aria-label="批注内容"]').setValue("编辑后保存");
  await float.findAll("button").find((button) => button.text() === "保存意见").trigger("click");
  await flushPromises();
}

test("编辑后立即保存批注：dirty flush 后仍按映射锚点提交最新修订", async () => {
  api.createAnnotation.mockResolvedValue({
    id: "annotation-new", caseId: "case-1", from: 1, to: 3, quote: "正文",
    section: "正文", revision: 4, anchorState: "active",
    status: "pending", content: "编辑后保存", source: "manual", createdBy: "user-1",
    createdAt: "2026-09-13T00:00:00Z", replies: [],
  });
  const wrapper = await renderDraftWorkspace();
  const canvas = wrapper.findComponent({ name: "CanvasEditor" });
  await openDraftFloat(wrapper, canvas);
  await editOpenDraft(canvas, wrapper);
  expect(api.createAnnotation).toHaveBeenCalledWith("case-1", expect.objectContaining({
    from: 1, to: 3, quote: "正文", revision: 4, content: "编辑后保存",
  }), "csrf-token");
  expect(api.saveCase).toHaveBeenCalledTimes(1);
  wrapper.unmount();
});

function annotationThread(overrides = {}) {
  return {
    id: "annotation-1", from: 1, to: 3, quote: "正文", section: "正文",
    revision: 3, anchorState: "active", status: "pending", content: "旧意见",
    createdBy: "user-1", replies: [], revisions: [], ...overrides,
  };
}

const annotationAiRailStub = {
  name: "AnnotationAiRailStub",
  props: ["writingContext", "promptRequest"],
  emits: ["ask-ai", "clear-writing-context"],
  template: "<div />",
};

function renderWorkbenchWithRealRail() {
  return mount(WorkbenchView, {
    global: { stubs: {
      SiteHeader: true, OutlinePanel: true, teleport: true,
      AgentArtifactCard: true, AgentResourceTrace: true, AgentSourcePicker: true,
      AgentThreadList: true, AttachmentPanel: true,
      PublicSourceList: true, VersionPanel: true,
      RouterLink: { template: "<a><slot /></a>" },
    } },
  });
}

function railTab(wrapper, label) {
  return wrapper.findComponent({ name: "AssistantRail" })
    .findAll(".assistant-tabs > button").find((button) => button.text().includes(label));
}

async function openRailComments(wrapper) {
  await railTab(wrapper, "批注").trigger("click");
  await flushPromises();
  return wrapper.findComponent({ name: "AssistantRail" }).findComponent({ name: "CommentPanel" });
}

async function askAiFromComments(wrapper) {
  const comments = await openRailComments(wrapper);
  await comments.findAll("button").find((button) => button.text().includes("让 AI 修订")).trigger("click");
  await flushPromises();
  return wrapper.findComponent({ name: "AssistantRail" }).findComponent({ name: "AgentChatPanel" });
}

async function deleteFromComments(wrapper) {
  const comments = await openRailComments(wrapper);
  await comments.get('[aria-label="删除批注"]').trigger("click");
  await flushPromises();
}

async function editAgentPrompt(chat, annotation) {
  const composer = chat.get('[aria-label="向 AI 提问"]');
  await vi.waitFor(() => expect(composer.element.value).toContain(annotation.content));
  const edited = `${composer.element.value}\n\n用户编辑后的修订要求`;
  await composer.setValue(edited);
  return edited;
}

async function sendAgentPrompt(chat, fetchMock) {
  await chat.get('[aria-label="发送"]').trigger("click");
  await vi.waitFor(() => expect(fetchMock).toHaveBeenCalled());
  return JSON.parse(fetchMock.mock.calls.at(-1)[1].body).messages.at(-1).parts;
}

function agentStream() {
  return new Response('data: {"type":"start","messageId":"message-2"}\n\ndata: [DONE]\n\n', {
    headers: { "Content-Type": "text/event-stream", "x-vercel-ai-ui-message-stream": "v1" },
  });
}

function setupRealChat(annotation) {
  api.getCase.mockResolvedValue(caseFixture());
  api.listAnnotations.mockResolvedValue([annotation]);
  api.deleteAnnotation.mockResolvedValue(null);
  api.agentThread.mockResolvedValue({ id: "thread-1", messages: [], artifacts: [], activeRun: null, latestRun: null });
  api.aiSettings.mockResolvedValue({ configured: true, effectiveModel: "test-model" });
  api.listSkills.mockResolvedValue([]);
  const fetchMock = vi.fn().mockResolvedValue(agentStream());
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

async function finishDeletedAnnotationSend(wrapper, chat, fetchMock, annotation, prompt) {
  await deleteFromComments(wrapper);
  expect(wrapper.findComponent({ name: "CanvasEditor" }).props("annotations")).toEqual([]);
  expect(chat.props("writingContext")).toMatchObject({ from: annotation.from, to: annotation.to });
  expect(chat.props("writingContext")).not.toHaveProperty("annotationId");
  await railTab(wrapper, "AI").trigger("click");
  await flushPromises();
  expect(chat.get('[aria-label="向 AI 提问"]').element.value).toBe(prompt);
  return sendAgentPrompt(chat, fetchMock);
}

async function openAnnotationThread(wrapper) {
  wrapper.findComponent({ name: "CanvasEditor" }).vm.$emit("annotation-click", "annotation-1");
  await flushPromises();
  expect(wrapper.get(".annotation-float").text()).toContain("旧意见");
}

test("真实编辑器重捕获保留批注 AI 关联，切线程清除关联", async () => {
  const annotation = annotationThread();
  api.getCase.mockResolvedValue(caseFixture());
  api.listAnnotations.mockResolvedValue([annotation]);
  const wrapper = renderWorkbenchWithEditor(annotationAiRailStub);
  await flushPromises();
  wrapper.getComponent(annotationAiRailStub).vm.$emit("ask-ai", annotation);
  await flushPromises();
  expect(wrapper.getComponent(annotationAiRailStub).props("writingContext"))
    .toMatchObject({ annotationId: annotation.id, from: annotation.from, to: annotation.to });
  expect(wrapper.getComponent(annotationAiRailStub).props("promptRequest").text).toContain(annotation.content);
  wrapper.getComponent(annotationAiRailStub).vm.$emit("clear-writing-context");
  await flushPromises();
  expect(wrapper.getComponent(annotationAiRailStub).props("writingContext")).toBe(null);
  wrapper.unmount();
});

test("真实辅助栏删除批注刷新编辑器时解除 AI 关联并保留预填提示", async () => {
  const annotation = annotationThread();
  const fetchMock = setupRealChat(annotation);
  const wrapper = renderWorkbenchWithRealRail();
  await flushPromises();
  const chat = await askAiFromComments(wrapper);
  const prompt = await editAgentPrompt(chat, annotation);
  expect(chat.props("writingContext")).toMatchObject({ annotationId: annotation.id });
  const parts = await finishDeletedAnnotationSend(wrapper, chat, fetchMock, annotation, prompt);
  expect(parts).toContainEqual({ type: "data-selection", data: { from: annotation.from, to: annotation.to } });
  expect(parts).not.toContainEqual({ type: "data-annotation", data: { id: annotation.id } });
  expect(parts.find((part) => part.type === "text")?.text).toContain("用户编辑后的修订要求");
  wrapper.unmount();
});

test("相同正文范围的新上下文会替换旧批注关联", async () => {
  api.getCase.mockResolvedValue(caseFixture());
  const wrapper = render(annotationAiRailStub);
  await flushPromises();
  const canvas = wrapper.findComponent({ name: "CanvasEditor" });
  const rail = wrapper.getComponent(annotationAiRailStub);
  const range = { from: 1, to: 3, quote: "正文", sameBlock: true };
  canvas.vm.$emit("writing-context", { ...range, annotationId: "an-old" });
  await flushPromises();
  expect(rail.props("writingContext")).toMatchObject({ annotationId: "an-old" });
  canvas.vm.$emit("writing-context", range);
  await flushPromises();
  expect(rail.props("writingContext")).not.toHaveProperty("annotationId");
  canvas.vm.$emit("writing-context", { ...range, annotationId: "an-new" });
  await flushPromises();
  expect(rail.props("writingContext")).toMatchObject({ annotationId: "an-new" });
  wrapper.unmount();
});

async function finishAnnotationRun(wrapper) {
  wrapper.getComponent(annotationRailStub).vm.$emit("annotation-run", "thread-9");
  await flushPromises();
  await vi.advanceTimersByTimeAsync(4000);
  await flushPromises();
}

async function renderPollingWorkspace() {
  const thread = annotationThread();
  api.getCase.mockResolvedValue(caseFixture());
  api.listAnnotations.mockResolvedValueOnce([thread]).mockResolvedValueOnce([
    annotationThread({ content: "更新意见", replies: [{ id: "reply-1", content: "第二轮" }] }),
  ]);
  api.agentThread.mockResolvedValueOnce({ id: "thread-9", activeRun: { id: "run-1" } })
    .mockResolvedValue({ id: "thread-9", activeRun: null, latestRun: { status: "completed" } });
  const wrapper = renderWorkbenchWithEditor(annotationRailStub);
  await flushPromises();
  return wrapper;
}

test("AI轮询完成后同步仍打开的浮窗线程", async () => {
  vi.useFakeTimers();
  try {
    const wrapper = await renderPollingWorkspace();
    await openAnnotationThread(wrapper);
    await finishAnnotationRun(wrapper);
    expect(wrapper.get(".annotation-float").text()).toContain("更新意见");
    expect(wrapper.get(".annotation-float").text()).toContain("第二轮");
    wrapper.unmount();
  } finally {
    vi.useRealTimers();
  }
});


test("从批注浮窗切换历史面板后清除遮挡", async () => {
  api.getCase.mockResolvedValue(caseFixture());
  api.listAnnotations.mockResolvedValue([annotationThread()]);
  const wrapper = renderWorkbenchWithEditor(annotationRailStub);
  await flushPromises();
  await openAnnotationThread(wrapper);
  wrapper.getComponent(annotationRailStub).vm.$emit("select", "history");
  await flushPromises();
  expect(wrapper.find(".annotation-float").exists()).toBe(false);
  wrapper.unmount();
});

async function annotationWorkspace() {
  api.getCase.mockResolvedValue(caseFixture());
  api.listAnnotations.mockResolvedValue([annotationThread()]);
  const wrapper = renderWorkbenchWithEditor(annotationRailStub);
  await flushPromises();
  return wrapper;
}

test("历史面板打开后点正文批注切换到批注工具", async () => {
  const wrapper = await annotationWorkspace();
  const rail = wrapper.getComponent(annotationRailStub);
  rail.vm.$emit("select", "history");
  await flushPromises();
  expect(rail.props("active")).toBe("history");
  await openAnnotationThread(wrapper);
  expect(rail.props("active")).toBe("comments");
  wrapper.unmount();
});

test("浮窗保存中不能切换工具且完成后可以切换", async () => {
  const wrapper = await annotationWorkspace();
  await openAnnotationThread(wrapper);
  const float = wrapper.findComponent({ name: "AnnotationFloat" });
  const rail = wrapper.getComponent(annotationRailStub);
  float.vm.$emit("mutation-state", true);
  rail.vm.$emit("select", "history");
  await flushPromises();
  expect(wrapper.find(".annotation-float").exists()).toBe(true);
  expect(rail.props("active")).toBe("comments");
  float.vm.$emit("mutation-state", false);
  rail.vm.$emit("select", "history");
  await flushPromises();
  expect(wrapper.find(".annotation-float").exists()).toBe(false);
  expect(rail.props("active")).toBe("history");
  wrapper.unmount();
});


for (const event of ["annotate", "annotation-click"]) {
  test(`附件请求在途时不能通过 ${event} 切换批注工具`, async () => {
    const wrapper = await annotationWorkspace();
    const rail = wrapper.getComponent(annotationRailStub);
    const canvas = wrapper.findComponent({ name: "CanvasEditor" });
    emitAnnotationEntry(canvas, event);
    rail.vm.$emit("select", "files");
    rail.vm.$emit("mutation-state", true);
    emitAnnotationEntry(canvas, event);
    await flushPromises();
    expect(rail.props("active")).toBe("files");
    expect(wrapper.find(".annotation-float").exists()).toBe(false);
    rail.vm.$emit("mutation-state", false);
    emitAnnotationEntry(canvas, event);
    await flushPromises();
    expect(rail.props("active")).toBe("comments");
    expect(wrapper.find(".annotation-float").exists()).toBe(true);
    wrapper.unmount();
  });
}
