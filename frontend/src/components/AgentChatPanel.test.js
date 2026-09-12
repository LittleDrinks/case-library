import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import AgentChatPanel from "./AgentChatPanel.vue";
import { api } from "../api.js";
import { session } from "../session.js";
import { CONVERSATION_SOURCES_KEY, createConversationSources } from "../composables/useConversationSources.js";

vi.mock("../api.js", () => ({
  api: {
    agentThread: vi.fn(), aiSettings: vi.fn(), agentDecide: vi.fn(),
    agentCancel: vi.fn(), agentThreads: vi.fn(), agentCreateThread: vi.fn(), agentUndoWrite: vi.fn(), listSkills: vi.fn(),
    getCase: vi.fn(), getPublicCase: vi.fn(), getMaterial: vi.fn(), search: vi.fn(), listSources: vi.fn(),
    caseHistory: vi.fn(),
  },
}));

const snapshot = {
  id: "thread-1",
  caseId: "case-1",
  messages: [{
    id: "message-1", role: "assistant", metadata: {},
    parts: [{ type: "text", text: "历史回答" }],
  }],
  artifacts: [],
  activeRun: null,
  latestRun: null,
};

function writeSnapshot(status = "written") {
  return {
    ...structuredClone(snapshot),
    messages: [{
      ...structuredClone(snapshot.messages[0]),
      parts: [{
        type: "tool-write_document", state: "output-available",
        input: { scope: "document", blocks: [{ type: "paragraph", text: "初稿" }] },
        output: { status: "written", id: "write-1" },
      }],
    }],
    writes: [{ id: "write-1", status, scope: "document" }],
  };
}

function activeWriteSnapshot() {
  const running = writeSnapshot();
  running.activeRun = { id: "run-1", status: "active" };
  running.latestRun = { id: "run-1", status: "active" };
  return running;
}

function versionSnapshot() {
  const result = structuredClone(snapshot);
  result.messages[0].parts = [{
    type: "tool-propose_document", state: "output-available",
    output: { status: "created", kind: "ai", versionId: "cv-ai-1" },
  }];
  return result;
}

function activeHydratedVersionSnapshot() {
  const result = versionSnapshot();
  result.messages[0].runId = "run-1";
  result.activeRun = { id: "run-1", status: "active" };
  result.latestRun = { id: "run-1", status: "active" };
  return result;
}

function activeHydratedTerminalSnapshot() {
  const result = activeHydratedVersionSnapshot();
  result.latestRun.status = "completed";
  return result;
}

function directWriteVersionSnapshot() {
  const result = structuredClone(snapshot);
  result.messages[0].parts = [{
    type: "tool-write_document", state: "output-available",
    output: { status: "written", versionStatus: "created", versionId: "cv-ai-2" },
  }];
  return result;
}

function completedSnapshot(value) {
  return { ...value, latestRun: { id: "run-1", status: "completed" } };
}

function streamResponse(chunks) {
  const encoder = new TextEncoder();
  return new Response(new ReadableStream({
    start(controller) {
      chunks.forEach((chunk) => controller.enqueue(encoder.encode(chunk)));
      controller.close();
    },
  }), {
    status: 200,
    headers: { "Content-Type": "text/event-stream", "x-vercel-ai-ui-message-stream": "v1" },
  });
}

function answerResponse() {
  return streamResponse([
    'data: {"type":"start","messageId":"message-2"}\n\n',
    'data: {"type":"start-step"}\n\n',
    'data: {"type":"text-start","id":"text-1"}\n\n',
    'data: {"type":"text-delta","id":"text-1","delta":"确定"}\n\n',
    'data: {"type":"text-delta","id":"text-1","delta":"回答"}\n\n',
    'data: {"type":"text-end","id":"text-1"}\n\n',
    'data: {"type":"finish-step"}\n\n',
    'data: {"type":"finish","finishReason":"stop"}\n\n',
    "data: [DONE]\n\n",
  ]);
}

function generatedVersionResponse() {
  return streamResponse([
    'data: {"type":"start","messageId":"message-live"}\n\n',
    'data: {"type":"start-step"}\n\n',
    'data: {"type":"tool-input-available","toolCallId":"version-1","toolName":"propose_document","input":{}}\n\n',
    'data: {"type":"tool-output-available","toolCallId":"version-1","output":{"status":"created","versionId":"cv-ai-new"}}\n\n',
    'data: {"type":"finish-step"}\n\n',
    'data: {"type":"finish","finishReason":"stop"}\n\n',
    "data: [DONE]\n\n",
  ]);
}

async function startGeneratedVersionRequest(wrapper) {
  await wrapper.get('[aria-label="向 AI 提问"]').setValue("生成全文");
  await wrapper.get('[aria-label="发送"]').trigger("click");
  await vi.waitFor(() => expect(fetch).toHaveBeenCalled());
  await flushPromises();
}

async function openOtherThread(wrapper) {
  await wrapper.get('[data-testid="agent-thread-list-open"]').trigger("click");
  await flushPromises();
  await wrapper.get('[data-testid="agent-thread-open"]').trigger("click");
}

function mountPanel(overrides = {}) {
  return mount(AgentChatPanel, {
    props: { caseRecord: { id: "case-1", revision: 1 }, ...overrides },
    global: {
      stubs: { RouterLink: true },
      provide: { [CONVERSATION_SOURCES_KEY]: conversationStore },
    },
  });
}

const settle = () => new Promise((resolve) => setTimeout(resolve, 60));
let conversationStore;

async function openSkillPopover(wrapper) {
  await wrapper.get('[data-testid="skill-picker-toggle"]').trigger("click");
  await settle();
  return document.querySelector(".skill-popover");
}

async function pickSourceInPopover(wrapper) {
  await wrapper.get('[data-testid="agent-source-picker-toggle"]').trigger("click");
  await settle();
  document.querySelector(".source-popover [data-testid=\"agent-source-option\"] input").click();
  await flushPromises();
}

afterEach(() => {
  document.body.innerHTML = "";
});

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  conversationStore = createConversationSources();
  session.csrfToken = "csrf";
  api.agentThread.mockResolvedValue(structuredClone(snapshot));
  api.aiSettings.mockResolvedValue({ configured: true, effectiveModel: "model-a" });
  api.listSources.mockResolvedValue({ entries: [] });
  api.caseHistory.mockResolvedValue({ versions: [] });
  api.listSkills.mockResolvedValue([
    { id: "skill-pub", versionId: "skillver-1", version: "v1", name: "思政案例生成", description: "按模板生成教学案例" },
  ]);
  api.getCase.mockImplementation((id) => Promise.resolve({ id }));
  api.getMaterial.mockImplementation((id) => Promise.resolve({ id }));
  api.search.mockResolvedValue({ items: [] });
});

it("hydrates an undone write from the server snapshot", async () => {
  api.agentThread.mockResolvedValue(writeSnapshot("undone"));
  const wrapper = mountPanel();
  await flushPromises();

  expect(wrapper.get('[data-testid="agent-write-undone"]').text()).toBe("已撤销写入");
  expect(wrapper.find('[data-testid="agent-undo-write"]').exists()).toBe(false);
});

it("does not reopen a completed AI version when the panel hydrates or remounts", async () => {
  api.agentThread.mockResolvedValue(completedSnapshot(versionSnapshot()));
  api.caseHistory.mockResolvedValue({ versions: [{ id: "cv-ai-1", sourceRunId: "run-1" }] });
  const wrapper = mountPanel();
  await flushPromises();

  expect(wrapper.emitted("versions-updated")).toBeUndefined();
  expect(wrapper.emitted("open-version")).toBeUndefined();
  wrapper.unmount();
  const remounted = mountPanel();
  await flushPromises();
  expect(remounted.emitted("open-version")).toBeUndefined();
});

it("does not reopen a hydrated direct-write AI version", async () => {
  api.agentThread.mockResolvedValue(completedSnapshot(directWriteVersionSnapshot()));
  api.caseHistory.mockResolvedValue({ versions: [{ id: "cv-ai-2" }] });
  const wrapper = mountPanel();
  await flushPromises();

  expect(wrapper.emitted("versions-updated")).toBeUndefined();
  expect(wrapper.emitted("open-version")).toBeUndefined();
});

it("opens a newly generated AI version once after hydration", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(generatedVersionResponse()));
  api.caseHistory.mockResolvedValue({ versions: [{ id: "cv-ai-new" }] });
  const wrapper = mountPanel();
  await flushPromises();

  await wrapper.get('[aria-label="向 AI 提问"]').setValue("生成全文");
  await wrapper.get('[aria-label="发送"]').trigger("click");
  await vi.waitFor(() => expect(wrapper.emitted("open-version")).toEqual([[{ id: "cv-ai-new" }]]));
  expect(wrapper.emitted("open-version")).toHaveLength(1);
});

it("drops a delayed generated-version open after the panel unmounts", async () => {
  const history = deferred();
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(generatedVersionResponse()));
  api.caseHistory.mockReturnValue(history.promise);
  const wrapper = mountPanel();
  await flushPromises();

  await wrapper.get('[aria-label="向 AI 提问"]').setValue("生成全文");
  await wrapper.get('[aria-label="发送"]').trigger("click");
  await vi.waitFor(() => expect(api.caseHistory).toHaveBeenCalled());
  wrapper.unmount();
  history.resolve({ versions: [{ id: "cv-ai-new" }] });
  await flushPromises();
  expect(wrapper.emitted("open-version")).toBeUndefined();
});

it("drops a delayed generated-version open when switching threads", async () => {
  const nextThread = deferred(), response = deferred();
  vi.stubGlobal("fetch", vi.fn().mockReturnValue(response.promise));
  api.agentThreads.mockResolvedValue([{ id: "thread-2", title: "第二对话" }]);
  api.agentThread.mockImplementation((_, id) => (
    id === "thread-2" ? nextThread.promise : Promise.resolve(structuredClone(snapshot))
  ));
  const wrapper = mountPanel();
  await flushPromises();
  await startGeneratedVersionRequest(wrapper);
  await openOtherThread(wrapper);
  response.resolve(generatedVersionResponse());
  await flushPromises();
  expect(api.caseHistory).not.toHaveBeenCalled();
  expect(wrapper.emitted("open-version")).toBeUndefined();
  nextThread.resolve(emptyThread("thread-2"));
  await flushPromises();
  expect(wrapper.emitted("open-version")).toBeUndefined();
});

it("drops a stale generated-version history response after switching threads", async () => {
  const history = deferred(), nextThread = deferred();
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(generatedVersionResponse()));
  api.caseHistory.mockReturnValue(history.promise);
  api.agentThreads.mockResolvedValue([{ id: "thread-2", title: "第二对话" }]);
  api.agentThread.mockImplementation((_, id) => (
    id === "thread-2" ? nextThread.promise : Promise.resolve(structuredClone(snapshot))
  ));
  const wrapper = mountPanel();
  await flushPromises();
  await startGeneratedVersionRequest(wrapper);
  await vi.waitFor(() => expect(api.caseHistory).toHaveBeenCalled());
  await openOtherThread(wrapper);
  history.resolve({ versions: [{ id: "cv-ai-new" }] });
  await flushPromises();
  expect(wrapper.emitted("open-version")).toBeUndefined();
  nextThread.resolve(emptyThread("thread-2"));
  await flushPromises();
});

it("drains a hydrated terminal version after a failed thread switch", async () => {
  const hydrated = activeHydratedTerminalSnapshot();
  const nextThread = deferred();
  api.agentThread.mockImplementation((_, id) => (
    id === "thread-2" ? nextThread.promise : Promise.resolve(hydrated)
  ));
  api.agentThreads.mockResolvedValue([{ id: "thread-2", title: "第二对话" }]);
  api.caseHistory.mockResolvedValue({ versions: [{ id: "cv-ai-1" }] });
  const wrapper = mountPanel();
  await flushPromises();
  await openOtherThread(wrapper);
  nextThread.reject(new Error("切换失败"));
  await flushPromises();
  expect(wrapper.emitted("open-version")).toEqual([[{ id: "cv-ai-1" }]]);
});

it("drains a hydrated terminal version after failed new-thread transition", async () => {
  const hydrated = activeHydratedTerminalSnapshot();
  api.agentThread.mockImplementation((_, id) => (
    id === "thread-new" ? Promise.reject(new Error("新线程加载失败")) : Promise.resolve(hydrated)
  ));
  api.agentCreateThread.mockResolvedValue({ id: "thread-new" });
  api.agentThreads.mockResolvedValue([]);
  api.caseHistory.mockResolvedValue({ versions: [{ id: "cv-ai-1" }] });
  const wrapper = mountPanel();
  await flushPromises();
  await wrapper.get('[data-testid="agent-thread-list-open"]').trigger("click");
  await flushPromises();
  await wrapper.get('[data-testid="agent-thread-create"]').trigger("click");
  await flushPromises();
  expect(wrapper.emitted("open-version")).toEqual([[{ id: "cv-ai-1" }]]);
});

it("resyncs a fresh old-thread version after a failed switch", async () => {
  const nextThread = deferred(), response = deferred();
  vi.stubGlobal("fetch", vi.fn().mockReturnValue(response.promise));
  api.agentThreads.mockResolvedValue([{ id: "thread-2", title: "第二对话" }]);
  api.agentThread.mockImplementation((_, id) => (
    id === "thread-2" ? nextThread.promise : Promise.resolve(structuredClone(snapshot))
  ));
  api.caseHistory.mockResolvedValue({ versions: [{ id: "cv-ai-new" }] });
  const wrapper = mountPanel(); await flushPromises();
  await startGeneratedVersionRequest(wrapper);
  await openOtherThread(wrapper);
  response.resolve(generatedVersionResponse());
  await flushPromises();
  expect(api.caseHistory).not.toHaveBeenCalled();
  nextThread.reject(new Error("切换失败"));
  await flushPromises();
  expect(wrapper.emitted("versions-updated")).toEqual([[]]);
  expect(wrapper.emitted("open-version")).toEqual([[{ id: "cv-ai-new" }]]);
});

it("refreshes the case after an in-flight write is hydrated", async () => {
  const completed = writeSnapshot();
  completed.latestRun = { id: "run-1", status: "completed" };
  api.agentThread.mockResolvedValueOnce(activeWriteSnapshot()).mockResolvedValueOnce(completed);
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(answerResponse()));
  const wrapper = mountPanel();
  await vi.waitFor(() => expect(api.getCase).toHaveBeenCalledWith("case-1"));

  expect(wrapper.emitted("case-revised")[0][0]).toEqual({ id: "case-1" });
});

it("refreshes the thread after undo so the write action is replaced", async () => {
  api.agentThread.mockResolvedValueOnce(writeSnapshot()).mockResolvedValueOnce(writeSnapshot("undone"));
  api.agentUndoWrite.mockResolvedValue({
    write: { id: "write-1", status: "undone" },
    case: { id: "case-1", revision: 3 },
  });
  const wrapper = mountPanel();
  await flushPromises();

  await wrapper.get('[data-testid="agent-undo-write"]').trigger("click");
  await flushPromises();

  expect(api.agentUndoWrite).toHaveBeenCalledWith("case-1", "thread-1", "write-1", "csrf");
  expect(wrapper.get('[data-testid="agent-write-undone"]').exists()).toBe(true);
  expect(wrapper.find('[data-testid="agent-undo-write"]').exists()).toBe(false);
  expect(wrapper.emitted("case-revised")[0][0]).toMatchObject({ id: "case-1", revision: 3 });
});

it("passes the reader version and readonly flag to the source picker", async () => {
  const wrapper = mountPanel({ versionId: "v-reader-1", readOnly: true });
  await flushPromises();
  const picker = wrapper.findComponent({ name: "AgentSourcePicker" });
  expect(picker.props("versionId")).toBe("v-reader-1");
  expect(picker.props("readOnly")).toBe(true);
  expect(wrapper.find('[data-testid="skill-picker-toggle"]').exists()).toBe(false);
});

const artifactSnapshot = () => ({
  ...structuredClone(snapshot),
  artifacts: [{
    id: "artifact-1", status: "pending",
    target: { from: 1, to: 4, quote: "原文" },
    replacement: "替换文本", reason: "理由", sources: [
      { kind: "case", id: "src-entry-9", sourceCaseId: "c-real-9", versionId: "v-9", version: "v1", title: "真实案例" },
      { kind: "case", id: "src-old", title: "旧格式来源", versionId: "v-old" },
      { kind: "case", id: "src-no-version", sourceCaseId: "c-real-9", title: "无固定版本来源" },
      { kind: "material", id: "mat-1", title: "素材来源" },
    ],
  }],
});

it("links artifact sources to the fixed public version of the real case", async () => {
  api.agentThread.mockResolvedValue(artifactSnapshot());
  api.getPublicCase.mockResolvedValue({ title: "真实案例", contentAvailable: true });
  const wrapper = mountPanel();
  await vi.waitFor(() => expect(wrapper.get('[data-source-ref="case:src-entry-9:v-9"]').attributes("href"))
    .toBe("#/cases/c-real-9?versionId=v-9"));
  expect(api.getPublicCase).toHaveBeenCalledWith("c-real-9", "v-9");
  expect(wrapper.get('[data-source-ref="case:src-old:v-old"]').element.tagName).toBe("P");
  expect(wrapper.get('[data-source-ref="case:src-no-version"]').element.tagName).toBe("P");
  expect(wrapper.text()).toContain("旧格式来源");
  expect(wrapper.text()).toContain("素材来源");
});

function sentRequest(fetch) {
  const [url, options] = fetch.mock.calls[0];
  return { url, headers: new Headers(options.headers), body: JSON.parse(options.body) };
}

it("restores the server thread and sends one turn through the SDK transport", async () => {
  const fetch = vi.fn().mockResolvedValue(answerResponse());
  vi.stubGlobal("fetch", fetch);
  const wrapper = mountPanel();
  await flushPromises();

  expect(wrapper.text()).toContain("历史回答");
  await wrapper.get('[aria-label="向 AI 提问"]').setValue("当前问题");
  await wrapper.get('[aria-label="发送"]').trigger("click");
  await flushPromises();

  const { url, headers, body } = sentRequest(fetch);
  expect(url).toBe("/api/cases/case-1/agent/thread/thread-1/stream");
  expect(headers.get("X-CSRF-Token")).toBe("csrf");
  expect(body.trigger).toBe("submit-message");
  expect(body.messages.at(-1).parts[0].text).toBe("当前问题");
  expect(body.messages.at(-1).parts).toEqual([{ type: "text", text: "当前问题" }]);
  expect(wrapper.text()).toContain("确定回答");
});

it("sends selected sources and the current writing selection as data parts", async () => {
  api.listSources.mockResolvedValue({ entries: [{ sourceType: "case", id: "src-1", title: "来源一" }] });
  const fetch = vi.fn().mockResolvedValue(answerResponse());
  vi.stubGlobal("fetch", fetch);
  const wrapper = mountPanel({ writingContext: {
    from: 1, to: 4, quote: "第二段", sameBlock: true,
  } });
  await flushPromises();
  await pickSourceInPopover(wrapper);
  await wrapper.get('[aria-label="向 AI 提问"]').setValue("结合来源");
  await wrapper.get('[aria-label="发送"]').trigger("click");
  await flushPromises();
  const body = JSON.parse(fetch.mock.calls[0][1].body);
  expect(body.messages.at(-1).parts.map((part) => part.type)).toEqual([
    "text", "data-source", "data-selection",
  ]);
});

it("asks the workbench to clear the writing context when the chip is removed", async () => {
  const wrapper = mountPanel({ writingContext: { from: 1, to: 4, quote: "第二段", sameBlock: true } });
  await flushPromises();
  expect(wrapper.get('[data-testid="composer-selection"]').exists()).toBe(true);
  await wrapper.get('[aria-label="移除正文选区"]').trigger("click");
  expect(wrapper.emitted("clear-writing-context")).toHaveLength(1);
});

it("keeps conversation context across panel remounts so tab switches never wipe it", async () => {
  conversationStore.toggle({ sourceType: "case", id: "src-1", title: "来源一" });
  const fetch = vi.fn().mockResolvedValue(answerResponse());
  vi.stubGlobal("fetch", fetch);
  const wrapper = mountPanel();
  await flushPromises();
  expect(conversationStore.sources.value.map((row) => row.id)).toEqual(["src-1"]);
  await wrapper.get('[aria-label="向 AI 提问"]').setValue("新案例提问");
  await wrapper.get('[aria-label="发送"]').trigger("click");
  await flushPromises();
  const parts = JSON.parse(fetch.mock.calls[0][1].body).messages.at(-1).parts;
  expect(parts.map((part) => part.type)).toEqual(["text", "data-source"]);
});

it("reader discussion binds its version and does not send an edit Skill", async () => {
  const fetch = vi.fn().mockResolvedValue(answerResponse());
  vi.stubGlobal("fetch", fetch);
  const wrapper = mountPanel({ versionId: "version-2", readOnly: true });
  await flushPromises();
  expect(api.agentThread).toHaveBeenCalledWith("case-1", null, "version-2", "");
  expect(wrapper.find('[data-testid="skill-picker-toggle"]').exists()).toBe(false);
  await wrapper.get('[aria-label="向 AI 提问"]').setValue("只读问题");
  await wrapper.get('[aria-label="发送"]').trigger("click");
  await flushPromises();
  const body = JSON.parse(fetch.mock.calls[0][1].body);
  expect(body.messages.at(-1).parts).toEqual([{ type: "text", text: "只读问题" }]);
});

it("review discussion allows Skill selection while preserving review mode and read-only composer", async () => {
  const wrapper = mountPanel({ review: true });
  await flushPromises();
  expect(api.agentThread).toHaveBeenCalledWith("case-1", null, "", "review");
  expect(wrapper.findComponent({ name: "AgentComposer" }).props("readOnly")).toBe(true);
  expect(wrapper.find('[data-testid="skill-picker-toggle"]').exists()).toBe(true);
  expect(api.listSkills).toHaveBeenCalled();
  expect(wrapper.findComponent({ name: "AgentComposer" }).props("review")).toBe(true);
});

it("inserts a published skill into the pending message and sends it once", async () => {
  const fetch = vi.fn().mockResolvedValue(answerResponse());
  vi.stubGlobal("fetch", fetch);
  const wrapper = mountPanel();
  await flushPromises();
  const panel = await openSkillPopover(wrapper);
  expect(panel.textContent).toContain("思政案例生成（v1）");
  panel.querySelector('[data-testid="skill-option"]').click();
  await flushPromises();
  expect(wrapper.get('[data-testid="composer-skill-block"]').text()).toContain("思政案例生成");
  await wrapper.get('[aria-label="向 AI 提问"]').setValue("生成一个案例");
  await wrapper.get('[aria-label="发送"]').trigger("click");
  await flushPromises();
  const body = JSON.parse(fetch.mock.calls[0][1].body);
  expect(body.messages.at(-1).parts[1]).toEqual({ type: "data-skill", data: { skillId: "skill-pub" } });
  expect(wrapper.find('[data-testid="composer-skill-block"]').exists()).toBe(false);
  expect(wrapper.get('[aria-label="向 AI 提问"]').element.value).toBe("");
});

function restoredSnapshot() {
  const restored = structuredClone(snapshot);
  restored.messages.unshift({
    id: "message-user", role: "user", metadata: {},
    parts: [
      { type: "text", text: "生成一个案例" },
      { type: "data-skill", data: { skillId: "skill-pub" } },
    ],
  });
  return restored;
}

it("renders mounted sources in message order using the current fixed-version entry", async () => {
  const restored = restoredSnapshot();
  restored.messages[0].parts.splice(1, 0, { type: "data-source", data: { sourceType: "case", id: "mounted-1" } });
  api.listSources.mockResolvedValue({ entries: [{ sourceType: "case", id: "mounted-1",
    title: "固定版本来源", contentAvailable: true, url: "#/cases/c-42?versionId=v-1" }] });
  api.agentThread.mockResolvedValue(restored);
  const wrapper = mountPanel();
  await vi.waitFor(() => expect(wrapper.get('[data-testid="message-source"] a').attributes("href"))
    .toBe("#/cases/c-42?versionId=v-1"));
  const text = wrapper.get(".ai-message.user").text();
  expect(text.indexOf("生成一个案例")).toBeLessThan(text.indexOf("固定版本来源"));
  expect(text.indexOf("固定版本来源")).toBeLessThan(text.indexOf("使用 Skill"));
  api.listSources.mockResolvedValue({ entries: [] });
  window.dispatchEvent(new Event("focus"));
  await vi.waitFor(() => expect(wrapper.find('[data-testid="message-source"] a').exists()).toBe(false));
  expect(api.getCase).not.toHaveBeenCalledWith("mounted-1");
});

it.each(["input-available", "output-error"])("does not label a %s Skill load as completed", async (state) => {
  const tracer = tracerPartsSnapshot();
  tracer.messages[1].parts[2].state = state;
  api.agentThread.mockResolvedValue(tracer);
  const wrapper = mountPanel();
  await flushPromises();
  const trace = wrapper.get('[data-testid="agent-skill-load"]');
  expect(trace.text()).not.toContain("已加载 Skill");
  expect(trace.text()).toContain(state === "output-error" ? "加载 Skill 失败" : "加载 Skill");
});

it("folds completed Skill resources with a user-expandable summary", async () => {
  api.agentThread.mockResolvedValue(structuredClone(tracerSnapshot()));
  const wrapper = mountPanel();
  await flushPromises();
  const resource = wrapper.get('[data-testid="agent-skill-resource"]');
  expect(resource.element.tagName).toBe("DETAILS");
  expect(resource.attributes("open")).toBeUndefined();
  expect(resource.get("summary").text()).toContain("已读取资源");
  expect(resource.get("pre").text()).toContain("选题原则");
});

it("shows the historical skill chip without preselecting the next message", async () => {
  api.agentThread.mockResolvedValue(restoredSnapshot());
  const wrapper = mountPanel();
  await flushPromises();

  expect(wrapper.get('[data-testid="message-skill"]').text()).toContain("使用 Skill：思政案例生成");
  expect(wrapper.find('[data-testid="composer-skill-block"]').exists()).toBe(false);
});

function deferred() {
  let resolve, reject;
  const promise = new Promise((done, fail) => { resolve = done; reject = fail; });
  return { promise, resolve, reject };
}

function emptyThread(id) {
  const result = structuredClone(snapshot);
  result.id = id;
  result.messages = [];
  return result;
}

async function switchThread(wrapper, index = 0) {
  await wrapper.get('[data-testid="agent-thread-list-open"]').trigger("click");
  await flushPromises();
  await wrapper.findAll('[data-testid="agent-thread-open"]')[index].trigger("click");
  await flushPromises();
}

it("keeps a delayed catalog alive while switching threads", async () => {
  const catalog = deferred();
  api.listSkills.mockReturnValue(catalog.promise);
  api.agentThreads.mockResolvedValue([{ id: "thread-2", title: "第二对话" }]);
  api.agentThread.mockImplementation((_, id) => Promise.resolve(
    id === "thread-2" ? emptyThread("thread-2") : structuredClone(snapshot),
  ));
  const wrapper = mountPanel();
  await flushPromises();
  await switchThread(wrapper);
  catalog.resolve([{ id: "skill-pub", version: "v1", name: "思政案例生成" }]);
  await flushPromises();
  await wrapper.get('[data-testid="skill-picker-toggle"]').trigger("click");
  await settle();
  expect(document.querySelector(".skill-popover").textContent).toContain("思政案例生成（v1）");
});

it("clears the pending skill block when switching threads", async () => {
  const fetch = vi.fn().mockResolvedValue(answerResponse());
  vi.stubGlobal("fetch", fetch);
  api.agentThreads.mockResolvedValue([{ id: "thread-empty", title: "空对话" }]);
  api.agentThread.mockImplementation((_, id) => Promise.resolve(
    id === "thread-empty" ? emptyThread("thread-empty") : restoredSnapshot(),
  ));
  const wrapper = mountPanel();
  await flushPromises();
  const panel = await openSkillPopover(wrapper);
  panel.querySelector('[data-testid="skill-option"]').click();
  await flushPromises();
  expect(wrapper.get('[data-testid="composer-skill-block"]').exists()).toBe(true);
  await switchThread(wrapper);
  expect(wrapper.find('[data-testid="composer-skill-block"]').exists()).toBe(false);
});

it("sends plain chat without the cleared skill after a thread switch", async () => {
  const fetch = vi.fn().mockResolvedValue(answerResponse());
  vi.stubGlobal("fetch", fetch);
  api.agentThreads.mockResolvedValue([{ id: "thread-empty", title: "空对话" }]);
  api.agentThread.mockImplementation((_, id) => Promise.resolve(emptyThread("thread-empty")));
  const wrapper = mountPanel();
  await flushPromises();
  await wrapper.get('[aria-label="向 AI 提问"]').setValue("当前问题");
  await wrapper.get('[aria-label="发送"]').trigger("click");
  await flushPromises();
  expect(sentRequest(fetch).body.messages.at(-1).parts).toEqual([{ type: "text", text: "当前问题" }]);
});

it("shows catalog errors with retry and falls back to the id for history", async () => {
  api.listSkills.mockRejectedValueOnce(new Error("目录服务不可用"));
  api.agentThread.mockResolvedValue(restoredSnapshot());
  const wrapper = mountPanel();
  await flushPromises();

  expect(wrapper.get('[data-testid="message-skill"]').text()).toContain("使用 Skill：skill-pub");
  await wrapper.get('[data-testid="skill-picker-toggle"]').trigger("click");
  await settle();
  expect(document.querySelector('[data-testid="skill-catalog-error"]').textContent).toContain("目录加载失败");
  await document.querySelector('[data-testid="skill-catalog-retry"]').click();
  await flushPromises();
  expect(document.querySelector(".skill-popover").textContent).toContain("思政案例生成（v1）");
  expect(wrapper.get('[data-testid="message-skill"]').text()).toContain("使用 Skill：思政案例生成");
});

it("shows an empty catalog state and still sends plain chat", async () => {
  api.listSkills.mockResolvedValue([]);
  const fetch = vi.fn().mockResolvedValue(answerResponse());
  vi.stubGlobal("fetch", fetch);
  const wrapper = mountPanel();
  await flushPromises();

  await wrapper.get('[data-testid="skill-picker-toggle"]').trigger("click");
  await settle();
  expect(document.querySelector('[data-testid="skill-catalog-empty"]').textContent).toContain("暂无已发布 Skill");
  await wrapper.get('[aria-label="向 AI 提问"]').setValue("当前问题");
  await wrapper.get('[aria-label="发送"]').trigger("click");
  await flushPromises();

  const body = JSON.parse(fetch.mock.calls[0][1].body);
  expect(body.messages.at(-1).parts).toEqual([{ type: "text", text: "当前问题" }]);
});

it("shows SDK request errors without a client stop or reconnect control", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(
    '{"detail":"运行任务无法创建"}',
    { status: 409, headers: { "Content-Type": "application/json" } },
  )));
  const wrapper = mountPanel();
  await flushPromises();
  await wrapper.get('[aria-label="向 AI 提问"]').setValue("重复发送");
  await wrapper.get('[aria-label="发送"]').trigger("click");
  await flushPromises();

  expect(wrapper.get('[role="alert"]').text()).toContain("运行任务无法创建");
  expect(wrapper.find('[title="停止生成"]').exists()).toBe(false);
});

function activeSnapshot() {
  const running = structuredClone(snapshot);
  running.activeRun = { id: "run-1", status: "active" };
  running.latestRun = { id: "run-1", status: "active" };
  return running;
}

function noContentResponse() {
  return new Response(null, { status: 204 });
}

it("stops the active run through the idempotent cancel command", async () => {
  api.agentThread
    .mockResolvedValueOnce(activeSnapshot())
    .mockResolvedValueOnce(activeSnapshot())
    .mockResolvedValue(structuredClone(snapshot));
  api.agentCancel.mockResolvedValue({ runId: "run-1", status: "cancelling" });
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(noContentResponse()));
  const wrapper = mountPanel();
  await flushPromises();

  expect(wrapper.find("[data-testid=\"agent-stop\"]").exists()).toBe(true);
  await wrapper.get("[data-testid=\"agent-stop\"]").trigger("click");
  await flushPromises();

  expect(api.agentCancel).toHaveBeenCalledWith("case-1", "thread-1", "csrf");
  expect(wrapper.find("[data-testid=\"agent-stop\"]").exists()).toBe(false);
});

function failedSnapshot() {
  const failed = structuredClone(snapshot);
  failed.messages = [{ id: "message-1", role: "user", metadata: {}, parts: [
    { type: "text", text: "失败的问题" },
  ] }];
  failed.latestRun = { id: "run-9", status: "failed", userMessageId: "message-1" };
  return failed;
}

function failedAnnotationSnapshot() {
  const failed = failedSnapshot();
  failed.messages[0].parts.push({ type: "data-annotation", data: { id: "an-1" } });
  return failed;
}

async function mountAndRetry(fetch) {
  api.agentThread.mockResolvedValue(failedSnapshot());
  vi.stubGlobal("fetch", fetch);
  const wrapper = mountPanel();
  await flushPromises();
  await wrapper.get("[data-testid=\"agent-retry\"]").trigger("click");
  await flushPromises();
  return wrapper;
}

it("retries a failed message as a regenerate that references the original", async () => {
  const fetch = vi.fn().mockResolvedValue(answerResponse());
  await mountAndRetry(fetch);
  const post = fetch.mock.calls.find(([, options]) => options.method === "POST");
  const body = JSON.parse(post[1].body);
  expect(body.trigger).toBe("regenerate-message");
  expect(body.messageId).toBe("message-1");
});

function tracerMessages() {
  return [{
    id: "message-user", role: "user", metadata: {},
    parts: [
      { type: "text", text: "请结合平台资料修订第2段" },
      { type: "data-skill", data: { skillId: "skill-pub" } },
    ],
  }, {
    id: "message-assistant", role: "assistant", metadata: {},
    parts: [
      { type: "tool-load_capability", toolCallId: "t1", state: "output-available", input: { id: "skill-pub" }, output: { instructions: "SKILL" } },
      { type: "tool-read_skill_resource_skill_pub", toolCallId: "t-resource", state: "output-available", input: { path: "references/模板规范.md" }, output: { path: "references/模板规范.md", content: "选题原则、结构模块" } },
      { type: "tool-search_corpus", toolCallId: "t2", state: "output-available", input: { query: "科学家精神" }, output: { sources: [{ kind: "case", id: "c-42", title: "科学家精神案例", snippet: "以科学家精神为例" }] } },
      { type: "tool-propose_revision", toolCallId: "t3", state: "output-available", input: {}, output: { artifactId: "artifact-9" } },
      { type: "text", text: "已生成单段修订候选" },
    ],
  }];
}

function tracerArtifacts(status) {
  return [{
    id: "artifact-9", caseId: "case-1", threadId: "thread-tracer", runId: "run-1",
    status, baseRevision: 1,
    target: { from: 9, to: 14, quote: "第二段原文" },
    replacement: "替换后的第二段", reason: "补充评价依据",
    sources: [{ kind: "case", id: "c-42", title: "科学家精神案例", snippet: "以科学家精神为例" }],
  }];
}

function tracerSnapshot() {
  return {
    id: "thread-tracer",
    caseId: "case-1",
    eventSeq: 7,
    messages: tracerMessages(),
    artifacts: tracerArtifacts("pending"),
    activeRun: null,
    latestRun: {
      id: "run-1", status: "completed", userMessageId: "message-user",
      assistantMessageId: "message-assistant",
    },
  };
}

it("renders the tracer skill load, sources and pending artifact card", async () => {
  api.agentThread.mockResolvedValue(structuredClone(tracerSnapshot()));
  const wrapper = mountPanel();
  await flushPromises();

  expect(wrapper.get('[data-testid="agent-skill-load"]').text()).toContain("已加载 Skill");
  expect(wrapper.get('[data-testid="agent-skill-resource"]').text()).toContain("选题原则");
  expect(wrapper.findAll('[data-testid="agent-skill-load"]')).toHaveLength(1);
  expect(wrapper.get('[data-testid="agent-source"]').text()).toContain("科学家精神案例");
  const artifact = wrapper.get('[data-testid="agent-artifact"]');
  expect(artifact.attributes("data-artifact-status")).toBe("pending");
  expect(artifact.text()).toContain("原文：第二段原文");
  expect(artifact.text()).toContain("替换为：替换后的第二段");
  expect(artifact.text()).toContain("依据：科学家精神案例");
  expect(wrapper.text()).toContain("已生成单段修订候选");
});

function tracerPartsSnapshot() {
  const tracer = tracerSnapshot();
  tracer.messages[1].parts = [
    { type: "reasoning", state: "streaming", text: "先查资料" },
    { type: "tool-search_corpus", toolCallId: "t2", state: "input-available", input: { query: "科学家精神" } },
    { type: "tool-load_capability", toolCallId: "t1", state: "output-available", input: { id: "skill-pub" }, output: {} },
    { type: "text", text: "结论" },
  ];
  return structuredClone(tracer);
}

it("renders assistant parts in structural order with running tools expanded", async () => {
  api.agentThread.mockResolvedValue(tracerPartsSnapshot());
  const wrapper = mountPanel();
  await flushPromises();

  const text = wrapper.get(".ai-message.assistant").text();
  expect(text.indexOf("思考中")).toBeGreaterThanOrEqual(0);
  expect(text.indexOf("思考中")).toBeLessThan(text.indexOf("检索案例 · 进行中"));
  expect(text.indexOf("检索案例 · 进行中")).toBeLessThan(text.indexOf("已加载 Skill"));
  expect(text.indexOf("已加载 Skill")).toBeLessThan(text.indexOf("结论"));
  const traces = wrapper.findAll(".agent-tool-trace");
  expect(traces[0].classes()).toContain("running");
  expect(traces[0].attributes("open")).toBeDefined();
  expect(traces[1].attributes("open")).toBeUndefined();
});

it("renders the artifact inline after its propose_revision tool call", async () => {
  api.agentThread.mockResolvedValue(structuredClone(tracerSnapshot()));
  const wrapper = mountPanel();
  await flushPromises();

  const inline = wrapper.get(".ai-message.assistant");
  expect(inline.find('[data-testid="agent-artifact"]').exists()).toBe(true);
  expect(wrapper.findAll('[data-testid="agent-artifact"]')).toHaveLength(1);
});

function searchPartWithSources() {
  return {
    type: "tool-search_corpus", toolCallId: "t2", state: "output-available", input: { query: "科学家精神" },
    output: { sources: [
      { kind: "case", id: "c-42", title: "科学家精神案例", snippet: "以科学家精神为例" },
      { kind: "material", id: "m-7", title: "配套阅读材料", snippet: "材料节选" },
    ] },
  };
}

function expectSourceCards(wrapper) {
  const cards = wrapper.findAll('[data-testid="agent-source"]');
  expect(cards).toHaveLength(2);
  const links = wrapper.findAll('[data-testid="agent-source"] a');
  expect(links).toHaveLength(2);
  expect(links[0].attributes("href")).toBe("#/cases/c-42");
  expect(links[0].attributes("title")).toContain("已按当前权限核验");
  expect(links[1].attributes("href")).toBe("#/materials/m-7");
  expect(cards[1].text()).toContain("配套阅读材料");
}

it("shows tool failures and keeps source cards on stable in-site ids", async () => {
  const tracer = tracerSnapshot();
  tracer.messages[1].parts = [
    searchPartWithSources(),
    { type: "tool-read_source", toolCallId: "t3", state: "output-error", input: { source_id: "x" }, errorText: "读取失败" },
  ];
  api.agentThread.mockResolvedValue(structuredClone(tracer));
  const wrapper = mountPanel();
  await flushPromises();

  await vi.waitFor(() => expectSourceCards(wrapper));
  const failed = wrapper.get('[data-testid="agent-source-read"]');
  expect(failed.text()).toContain("阅读来源 · 读取失败");
});

it("blocks an old source link when the current unified entry is restricted", async () => {
  const tracer = tracerSnapshot();
  tracer.messages[1].parts = [searchPartWithSources()];
  api.getCase.mockResolvedValue({ id: "c-42", title: "已撤回案例", contentAvailable: false });
  api.getMaterial.mockResolvedValue({
    id: "m-7", title: "配套阅读材料", contentAvailable: true, summary: "当前材料摘要",
  });
  api.agentThread.mockResolvedValue(structuredClone(tracer));
  const wrapper = mountPanel();
  await flushPromises();
  await flushPromises();

  expect(wrapper.find('[data-source-ref="case:c-42"] a').exists()).toBe(false);
  await vi.waitFor(() => expect(wrapper.find('[data-source-ref="case:c-42"]').text()).toContain("当前权限不可读取"));
  await vi.waitFor(() => expect(wrapper.find('[data-source-ref="material:m-7"] a').attributes("href")).toBe("#/materials/m-7"));
  expect(wrapper.find('[data-source-ref="case:c-42"]').text()).not.toContain("以科学家精神为例");
});

it("revalidates source permission when the window returns", async () => {
  let available = true;
  const tracer = tracerSnapshot();
  tracer.messages[1].parts = [searchPartWithSources()];
  api.getCase.mockImplementation(() => Promise.resolve({
    id: "c-42", title: "科学家精神案例", summary: "当前摘要", contentAvailable: available,
  }));
  api.getMaterial.mockResolvedValue({ id: "m-7", title: "配套阅读材料", contentAvailable: true });
  api.agentThread.mockResolvedValue(structuredClone(tracer));
  const wrapper = mountPanel();
  await flushPromises();
  available = false;
  window.dispatchEvent(new Event("focus"));
  await flushPromises();
  expect(wrapper.find('[data-source-ref="case:c-42"] a').exists()).toBe(false);
  expect(wrapper.find('[data-source-ref="case:c-42"]').text()).not.toContain("当前摘要");
});

it("revalidates source permission when the chat panel reopens", async () => {
  let available = true;
  const tracer = tracerSnapshot();
  tracer.messages[1].parts = [searchPartWithSources()];
  api.getCase.mockImplementation(() => Promise.resolve({ id: "c-42", contentAvailable: available }));
  api.getMaterial.mockResolvedValue({ id: "m-7", contentAvailable: true });
  api.agentThread.mockResolvedValue(structuredClone(tracer));
  const wrapper = mountPanel({ open: true });
  await flushPromises();
  available = false;
  await wrapper.setProps({ open: false });
  await wrapper.setProps({ open: true });
  await flushPromises();
  expect(wrapper.find('[data-source-ref="case:c-42"] a').exists()).toBe(false);
});

it("renders unknown tools by name without exposing raw arguments", async () => {
  const tracer = tracerSnapshot();
  tracer.messages[1].parts = [
    { type: "tool-future_tool", toolCallId: "t9", state: "output-available",
      input: { secretPrompt: "内部参数" }, output: { internal: "原始结果" } },
  ];
  api.agentThread.mockResolvedValue(structuredClone(tracer));
  const wrapper = mountPanel();
  await flushPromises();

  const trace = wrapper.get('[data-testid="agent-tool-trace"]');
  expect(trace.text()).toContain("future_tool · 已完成");
  expect(trace.text()).not.toContain("内部参数");
  expect(trace.find("pre").exists()).toBe(false);
});

it("hides tool duration for restored snapshots without live timing", async () => {
  api.agentThread.mockResolvedValue(structuredClone(tracerSnapshot()));
  const wrapper = mountPanel();
  await flushPromises();

  const summaries = wrapper.findAll(".agent-tool-trace summary span");
  for (const summary of summaries) expect(summary.text()).not.toMatch(/\d+(\.\d+)?s/);
});

function toolStreamChunks() {
  return [
    'data: {"type":"start","messageId":"message-live"}\n\n',
    'data: {"type":"start-step"}\n\n',
    'data: {"type":"tool-input-available","toolCallId":"t9","toolName":"search_corpus","input":{"query":"科学家精神"}}\n\n',
    'data: {"type":"tool-output-available","toolCallId":"t9","output":{"sources":[]}}\n\n',
    'data: {"type":"finish-step"}\n\n',
    'data: {"type":"finish","finishReason":"stop"}\n\n',
    "data: [DONE]\n\n",
  ];
}

it("does not invent tool duration from streamed UI events", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(streamResponse(toolStreamChunks())));
  const wrapper = mountPanel();
  await flushPromises();
  await wrapper.get('[aria-label="向 AI 提问"]').setValue("查资料");
  await wrapper.get('[aria-label="发送"]').trigger("click");
  await flushPromises();
  expect(wrapper.get('[data-testid="agent-tool-trace"]').text()).not.toMatch(/检索案例 · 已完成 · \d+(\.\d+)?s/);
});

it("renders persisted tool duration by tool call id", async () => {
  const tracer = tracerSnapshot();
  tracer.latestRun.toolTimings = {
    t2: { toolCallId: "t2", toolName: "search_corpus", startedAt: "2026-09-07T10:00:00Z", finishedAt: "2026-09-07T10:00:02.5Z" },
  };
  api.agentThread.mockResolvedValue(tracer);
  const wrapper = mountPanel();
  await flushPromises();
  const searchTrace = wrapper.findAll('[data-testid="agent-tool-trace"]')
    .find((trace) => trace.text().includes("检索案例"));
  expect(searchTrace.text()).toContain("检索案例 · 已完成 · 2.5s");
});

it("shows real finished-run duration from backend timestamps", async () => {
  const tracer = tracerSnapshot();
  tracer.latestRun = { id: "run-1", status: "completed", startedAt: "2026-09-07T10:00:00Z", finishedAt: "2026-09-07T10:00:03.5Z" };
  api.agentThread.mockResolvedValue(structuredClone(tracer));
  const wrapper = mountPanel();
  await flushPromises();

  expect(wrapper.get(".ai-status").text()).toContain("耗时 3.5s");
});

it("shows a cancelled run as an actionable error without fake completion", async () => {
  const cancelled = tracerSnapshot();
  cancelled.latestRun = {
    id: "run-1", status: "cancelled", userMessageId: "message-user",
    assistantMessageId: "message-assistant",
  };
  api.agentThread.mockResolvedValue(structuredClone(cancelled));
  const wrapper = mountPanel();
  await flushPromises();

  expect(wrapper.get('[role="alert"]').text()).toContain("运行已取消");
  expect(wrapper.get(".ai-status").text()).not.toContain("正在生成");
});

it("renders the retry action inside the failed user message", async () => {
  api.agentThread.mockResolvedValue(failedSnapshot());
  const wrapper = mountPanel();
  await flushPromises();

  expect(wrapper.get(".ai-message.user [data-testid='agent-retry']").text()).toContain("重试这条消息");
});

function failedTurnResponse(_url, options) {
  const latest = JSON.parse(options.body).messages.at(-1);
  const failed = failedSnapshot();
  failed.latestRun.clientRequestId = latest.id;
  failed.runs = [failed.latestRun];
  api.agentThread.mockResolvedValue(failed);
  return Promise.resolve(streamResponse([
    'data: {"type":"start","messageId":"failure-assistant"}\n\n',
    'data: {"type":"error","errorText":"AI 服务暂不可用"}\n\n',
    'data: {"type":"finish","finishReason":"error"}\n\n',
    "data: [DONE]\n\n",
  ]));
}

it("keeps retry on a newly failed turn with a server-assigned message id", async () => {
  api.agentThread.mockResolvedValue({ ...snapshot, messages: [] });
  vi.stubGlobal("fetch", vi.fn(failedTurnResponse));
  const wrapper = mountPanel();
  await flushPromises();
  await wrapper.get('[aria-label="向 AI 提问"]').setValue("失败的问题");
  await wrapper.get('[aria-label="发送"]').trigger("click");
  await flushPromises();
  expect(wrapper.get(".ai-message.user [data-testid='agent-retry']").text()).toContain("重试这条消息");
});

function selectionContext() {
  return { from: 9, to: 13, sameBlock: true, quote: "第二段原文", quoteHash: "quote-hash", revision: 3 };
}

it("hands annotation runs with their thread to the workbench so refresh survives panel switches", async () => {
  const fetch = vi.fn().mockResolvedValue(answerResponse());
  vi.stubGlobal("fetch", fetch);
  const context = { annotationId: "an-1", from: 9, to: 13, sameBlock: true, quote: "第二段原文", revision: 3 };
  const wrapper = mountPanel({ writingContext: context });
  await flushPromises();
  await wrapper.get('[aria-label="向 AI 提问"]').setValue("继续讨论");
  await wrapper.get('[aria-label="发送"]').trigger("click");
  await flushPromises();

  expect(wrapper.emitted("annotation-run")).toEqual([["thread-1"]]);
});

it("re-arms the annotation observation when a failed run is retried", async () => {
  const fetch = vi.fn().mockResolvedValue(answerResponse());
  api.agentThread.mockResolvedValue(failedAnnotationSnapshot());
  vi.stubGlobal("fetch", fetch);
  const wrapper = mountPanel();
  await flushPromises();
  await wrapper.get("[data-testid=\"agent-retry\"]").trigger("click");
  await flushPromises();

  expect(wrapper.emitted("annotation-run")).toEqual([["thread-1"]]);
});

it("sends the selected text as a structured selection part", async () => {
  const fetch = vi.fn().mockResolvedValue(answerResponse());
  vi.stubGlobal("fetch", fetch);
  const wrapper = mountPanel({ writingContext: selectionContext() });
  await flushPromises();

  expect(wrapper.get('[data-testid="composer-selection"]').text()).toContain("正文选区");
  await wrapper.get('[aria-label="向 AI 提问"]').setValue("改这段");
  await wrapper.get('[aria-label="发送"]').trigger("click");
  await flushPromises();
  const parts = JSON.parse(fetch.mock.calls[0][1].body).messages.at(-1).parts;
  expect(parts).toContainEqual({ type: "data-selection", data: { from: 9, to: 13 } });
});

it("keeps the pending card in place when a decision conflicts", async () => {
  api.agentThread.mockResolvedValueOnce(structuredClone(tracerSnapshot())).mockResolvedValue(
    structuredClone(tracerSnapshot()),
  );
  api.agentDecide.mockRejectedValue(Object.assign(new Error("案例已被修改，请刷新后重试"), { status: 409 }));
  const wrapper = mountPanel();
  await flushPromises();

  await wrapper.get('[data-testid="agent-accept"]').trigger("click");
  await flushPromises();
  expect(wrapper.get('[role="alert"]').text()).toContain("案例已被修改");
  expect(wrapper.get('[data-testid="agent-artifact"]').attributes("data-artifact-status")).toBe("pending");
  expect(wrapper.find('[data-testid="agent-accept"]').exists()).toBe(true);
});

it("renders failed resource reads from the UI tool protocol", async () => {
  const failed = tracerSnapshot();
  failed.messages[1].parts = [failed.messages[1].parts[0], {
    type: "tool-read_skill_resource_skill_pub", toolCallId: "t-error", state: "output-error",
    input: { path: "references/missing.md" }, errorText: "资源不存在：references/missing.md",
  }];
  api.agentThread.mockResolvedValue(failed);
  const wrapper = mountPanel();
  await flushPromises();
  expect(wrapper.get('[data-testid="agent-skill-resource-error"]').text()).toContain("资源不存在");
});
function resourceFeed() {
  let controller;
  const encoder = new TextEncoder();
  const response = new Response(new ReadableStream({ start(value) { controller = value; } }), {
    headers: { "Content-Type": "text/event-stream", "x-vercel-ai-ui-message-stream": "v1" },
  });
  return { response, send: (data) => controller.enqueue(encoder.encode(`data: ${JSON.stringify(data)}\n\n`)),
    close: () => controller.close() };
}

async function beginResourceRead(wrapper, feed) {
  await wrapper.get('[aria-label="向 AI 提问"]').setValue("读取资源");
  await wrapper.get('[aria-label="发送"]').trigger("click");
  feed.send({ type: "start", messageId: "resource-message" });
  feed.send({ type: "tool-input-start", toolCallId: "read-1", toolName: "read_skill_resource_skill_pub" });
  await flushPromises();
}

it("updates a mounted resource trace when the SDK receives its result", async () => {
  const feed = resourceFeed();
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(feed.response));
  const wrapper = mountPanel();
  await flushPromises();
  await beginResourceRead(wrapper, feed);
  expect(wrapper.get('[data-testid="agent-skill-resource"]').text()).toContain("正在读取资源");
  feed.send({ type: "tool-input-available", toolCallId: "read-1", toolName: "read_skill_resource_skill_pub", input: { path: "references/example.txt" } });
  feed.send({ type: "tool-output-available", toolCallId: "read-1", output: { path: "references/example.txt", content: "真实流资源正文" } });
  feed.send({ type: "finish", finishReason: "stop" });
  feed.close();
  await flushPromises();
  expect(wrapper.get('[data-testid="agent-skill-resource"]').text()).toContain("真实流资源正文");
});

it("renders the expired artifact status after the case revision moved on", async () => {
  api.agentThread.mockResolvedValue(
    structuredClone({ ...tracerSnapshot(), artifacts: tracerArtifacts("expired") }),
  );
  const wrapper = mountPanel();
  await flushPromises();

  const artifact = wrapper.get('[data-testid="agent-artifact"]');
  expect(artifact.attributes("data-artifact-status")).toBe("expired");
  expect(artifact.text()).toContain("状态：已过期");
  expect(wrapper.find('[data-testid="agent-accept"]').exists()).toBe(false);
  expect(wrapper.find('[data-testid="agent-reject"]').exists()).toBe(false);
});

function decideResult(decision) {
  return {
    artifact: { status: decision },
    ...(decision === "accepted" ? { versionId: "cv-ai-accepted" } : {}),
    case: decision === "accepted" ? { id: "case-1", revision: 2, document: { type: "doc", content: [] } } : null,
  };
}

function mountWithDecision(decision) {
  const snapshot = tracerSnapshot();
  api.agentThread.mockResolvedValueOnce(structuredClone(snapshot)).mockResolvedValue(
    structuredClone({ ...snapshot, artifacts: tracerArtifacts(decision) }),
  );
  api.agentDecide.mockResolvedValue(decideResult(decision));
  return mountPanel();
}

it("accepting the artifact calls the decision API, emits the revised case and reloads", async () => {
  const wrapper = mountWithDecision("accepted");
  api.caseHistory.mockResolvedValue({ versions: [{ id: "cv-ai-accepted", kind: "ai" }] });
  await flushPromises();

  await wrapper.get('[data-testid="agent-accept"]').trigger("click");
  await flushPromises();

  expect(api.agentDecide).toHaveBeenCalledWith("case-1", "thread-tracer", "artifact-9", "accepted", "csrf");
  expect(wrapper.emitted("case-revised")[0][0]).toMatchObject({ id: "case-1", revision: 2 });
  expect(wrapper.emitted("open-version")).toEqual([[{ id: "cv-ai-accepted", kind: "ai" }]]);
  expect(api.agentThread).toHaveBeenCalledTimes(2);
  expect(wrapper.get('[data-testid="agent-artifact"]').attributes("data-artifact-status")).toBe("accepted");
});

it("rejecting the artifact records the decision without touching the case", async () => {
  const wrapper = mountWithDecision("rejected");
  await flushPromises();

  await wrapper.get('[data-testid="agent-reject"]').trigger("click");
  await flushPromises();

  expect(api.agentDecide).toHaveBeenCalledWith("case-1", "thread-tracer", "artifact-9", "rejected", "csrf");
  expect(wrapper.emitted("case-revised")).toBeUndefined();
  expect(wrapper.get('[data-testid="agent-artifact"]').attributes("data-artifact-status")).toBe("rejected");
  expect(wrapper.find('[data-testid="agent-accept"]').exists()).toBe(false);
  expect(wrapper.find('[data-testid="agent-reject"]').exists()).toBe(false);
});

it("restores skill load, sources and decided artifact from a reloaded thread snapshot", async () => {
  api.getCase.mockResolvedValue({
    id: "c-42", title: "科学家精神案例", summary: "以科学家精神为例", contentAvailable: true,
  });
  api.agentThread.mockResolvedValue(
    structuredClone({ ...tracerSnapshot(), artifacts: tracerArtifacts("accepted") }),
  );
  const wrapper = mountPanel();
  await flushPromises();

  expect(wrapper.get('[data-testid="agent-skill-load"]').text()).toContain("已加载 Skill");
  await vi.waitFor(() => expect(wrapper.get('[data-testid="agent-source"]').text()).toContain("以科学家精神为例"));
  const artifact = wrapper.get('[data-testid="agent-artifact"]');
  expect(artifact.attributes("data-artifact-status")).toBe("accepted");
  expect(artifact.text()).toContain("状态：已接受");
  expect(wrapper.find('[data-testid="agent-accept"]').exists()).toBe(false);
  expect(wrapper.find('[data-testid="agent-reject"]').exists()).toBe(false);
});

it("renders assistant answers as markdown with scrollable tables", async () => {
  const answer = structuredClone(snapshot);
  answer.messages[0].parts = [{
    type: "text",
    text: "## 结论\n\n- **要点**一\n\n| 指标 | 数值 |\n| --- | --- |\n| 甲 | 12 |\n\n<script>alert(1)</script>",
  }];
  api.agentThread.mockResolvedValue(answer);
  const wrapper = mountPanel();
  await flushPromises();

  const answerBody = wrapper.get('[data-testid="agent-answer"]');
  expect(answerBody.get("h2").text()).toBe("结论");
  expect(answerBody.get("strong").text()).toBe("要点");
  expect(answerBody.get(".md-table-scroll table").exists()).toBe(true);
  expect(answerBody.element.innerHTML).not.toContain("<script");
  expect(answerBody.text()).toContain("<script>");
});

it("keeps user messages as plain preformatted text", async () => {
  const asked = structuredClone(snapshot);
  asked.messages = [
    { id: "message-1", role: "user", metadata: {}, parts: [{ type: "text", text: "# 生成案例\n带 换行" }] },
    { id: "message-2", role: "assistant", metadata: {}, parts: [{ type: "text", text: "确定回答" }] },
  ];
  api.agentThread.mockResolvedValue(asked);
  const wrapper = mountPanel();
  await flushPromises();

  const user = wrapper.get(".ai-message.user");
  expect(user.find("h1").exists()).toBe(false);
  expect(user.get("p").text()).toBe("# 生成案例\n带 换行");
  expect(wrapper.get('[data-testid="agent-answer"]').text()).toContain("确定回答");
});
