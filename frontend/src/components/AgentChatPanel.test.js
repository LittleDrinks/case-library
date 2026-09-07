import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, expect, it, vi } from "vitest";
import AgentChatPanel from "./AgentChatPanel.vue";
import { api } from "../api.js";
import { session } from "../session.js";

vi.mock("../api.js", () => ({
  api: {
    agentThread: vi.fn(), aiSettings: vi.fn(), agentDecide: vi.fn(),
    agentCancel: vi.fn(), agentThreads: vi.fn(), listSkills: vi.fn(),
    getCase: vi.fn(), getMaterial: vi.fn(), search: vi.fn(),
  },
}));

const snapshot = {
  id: "thread-1",
  caseId: "case-1",
  messages: [{
    id: "message-1", role: "assistant", metadata: {},
    parts: [{ type: "text", text: "历史回答" }],
  }],
  activeRun: null,
  latestRun: null,
};

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

function mountPanel(overrides = {}) {
  return mount(AgentChatPanel, {
    props: { caseRecord: { id: "case-1" }, ...overrides },
    global: { stubs: { RouterLink: true } },
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  session.csrfToken = "csrf";
  api.agentThread.mockResolvedValue(structuredClone(snapshot));
  api.aiSettings.mockResolvedValue({ configured: true, effectiveModel: "model-a" });
  api.listSkills.mockResolvedValue([
    { id: "skill-pub", versionId: "skillver-1", version: "v1", name: "思政案例生成", description: "按模板生成教学案例" },
  ]);
  api.getCase.mockImplementation((id) => Promise.resolve({ id }));
  api.getMaterial.mockImplementation((id) => Promise.resolve({ id }));
  api.search.mockResolvedValue({ items: [] });
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
  expect(body.messages.at(-1).parts).toHaveLength(1);
  expect(wrapper.text()).toContain("确定回答");
});

it("reader discussion binds its version and does not send an edit Skill", async () => {
  const fetch = vi.fn().mockResolvedValue(answerResponse());
  vi.stubGlobal("fetch", fetch);
  const wrapper = mountPanel({ versionId: "version-2", readOnly: true });
  await flushPromises();
  expect(api.agentThread).toHaveBeenCalledWith("case-1", null, "version-2");
  expect(wrapper.find('[data-testid="skill-select"]').exists()).toBe(false);
  await wrapper.get('[aria-label="向 AI 提问"]').setValue("只读问题");
  await wrapper.get('[aria-label="发送"]').trigger("click");
  await flushPromises();
  const body = JSON.parse(fetch.mock.calls[0][1].body);
  expect(body.messages.at(-1).parts).toEqual([{ type: "text", text: "只读问题" }]);
});

it("carries the selected published skill id and shows the catalog options", async () => {
  const fetch = vi.fn().mockResolvedValue(answerResponse());
  vi.stubGlobal("fetch", fetch);
  const wrapper = mountPanel();
  await flushPromises();

  const select = wrapper.get('[data-testid="skill-select"]');
  expect(select.findAll("option").at(0).text()).toBe("不使用 Skill");
  expect(select.findAll("option").at(1).text()).toContain("思政案例生成（v1）");
  await select.setValue("skill-pub");
  await wrapper.get('[aria-label="向 AI 提问"]').setValue("生成一个案例");
  await wrapper.get('[aria-label="发送"]').trigger("click");
  await flushPromises();

  const body = JSON.parse(fetch.mock.calls[0][1].body);
  expect(body.messages.at(-1).parts[1]).toEqual({ type: "data-skill", data: { skillId: "skill-pub" } });
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

it("restores the selected skill from the thread snapshot after reload", async () => {
  api.agentThread.mockResolvedValue(restoredSnapshot());
  const wrapper = mountPanel();
  await flushPromises();

  expect(wrapper.get('[data-testid="skill-select"]').element.value).toBe("skill-pub");
  expect(wrapper.get('[data-testid="message-skill"]').text()).toContain("使用 Skill：思政案例生成");
});

function pendingThread() {
  let resolve;
  const promise = new Promise((done) => { resolve = done; });
  api.agentThread.mockReturnValue(promise);
  return resolve;
}

function deferred() {
  let resolve;
  const promise = new Promise((done) => { resolve = done; });
  return { promise, resolve };
}

function emptyThread(id) {
  const result = structuredClone(snapshot);
  result.id = id;
  result.messages = [];
  return result;
}

function threadWithSkill(id, skillId) {
  const result = emptyThread(id);
  result.messages = [{ id: `${id}-message`, role: "user", metadata: {}, parts: [
    { type: "data-skill", data: { skillId } },
  ] }];
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
  expect(wrapper.find('[data-testid="skill-catalog-loading"]').exists()).toBe(false);
  expect(wrapper.get('[data-testid="skill-select"] option:nth-child(2)').text()).toContain("思政案例生成");
});

it("resets to plain chat for a thread without skill history", async () => {
  api.agentThreads.mockResolvedValue([{ id: "thread-empty", title: "空对话" }]);
  api.agentThread.mockImplementation((_, id) => Promise.resolve(
    id === "thread-empty" ? emptyThread("thread-empty") : restoredSnapshot(),
  ));
  const wrapper = mountPanel();
  await flushPromises();
  expect(wrapper.get('[data-testid="skill-select"]').element.value).toBe("skill-pub");
  await switchThread(wrapper);
  expect(wrapper.get('[data-testid="skill-select"]').element.value).toBe("");
});

it("restores the target skill when switching between published skills", async () => {
  api.agentThreads.mockResolvedValue([{ id: "thread-two", title: "第二 Skill" }]);
  api.agentThread.mockImplementation((_, id) => Promise.resolve(
    id === "thread-two" ? threadWithSkill("thread-two", "skill-two") : restoredSnapshot(),
  ));
  api.listSkills.mockResolvedValue([
    { id: "skill-pub", version: "v1", name: "思政案例生成" },
    { id: "skill-two", version: "v2", name: "第二 Skill" },
  ]);
  const wrapper = mountPanel();
  await flushPromises();
  await switchThread(wrapper);
  expect(wrapper.get('[data-testid="skill-select"]').element.value).toBe("skill-two");
});

it("reconciles a withdrawn skill when the catalog arrives before the thread", async () => {
  const resolve = pendingThread();
  api.listSkills.mockResolvedValue([]);
  const fetch = vi.fn().mockResolvedValue(answerResponse());
  vi.stubGlobal("fetch", fetch);
  const wrapper = mountPanel();
  await flushPromises();
  expect(wrapper.find('[data-testid="skill-catalog-empty"]').exists()).toBe(true);
  resolve(restoredSnapshot());
  await flushPromises();
  expect(wrapper.get('[data-testid="skill-select"]').element.value).toBe("");
  await wrapper.get('[aria-label="向 AI 提问"]').setValue("当前问题");
  expect(wrapper.get('[aria-label="发送"]').attributes("disabled")).toBeUndefined();
  await wrapper.get('[aria-label="发送"]').trigger("click");
  await flushPromises();
  expect(sentRequest(fetch).body.messages.at(-1).parts).toHaveLength(1);
});

it("keeps the server skill through a failed catalog and restores it on retry", async () => {
  api.listSkills.mockRejectedValueOnce(new Error("目录服务不可用"));
  api.agentThread.mockResolvedValue(restoredSnapshot());
  const wrapper = mountPanel();
  await flushPromises();

  expect(wrapper.get('[data-testid="skill-catalog-error"]').text()).toContain("目录加载失败");
  expect(wrapper.get('[data-testid="message-skill"]').text()).toContain("使用 Skill：skill-pub");
  await wrapper.get('[aria-label="向 AI 提问"]').setValue("生成一个案例");
  expect(wrapper.get('[aria-label="发送"]').attributes("disabled")).toBeDefined();

  await wrapper.get('[data-testid="skill-catalog-retry"]').trigger("click");
  await flushPromises();

  expect(wrapper.find('[data-testid="skill-catalog-error"]').exists()).toBe(false);
  expect(wrapper.get('[data-testid="skill-select"]').element.value).toBe("skill-pub");
  expect(wrapper.get('[aria-label="发送"]').attributes("disabled")).toBeUndefined();
});

it("shows an empty catalog state and still sends plain chat", async () => {
  api.listSkills.mockResolvedValue([]);
  const fetch = vi.fn().mockResolvedValue(answerResponse());
  vi.stubGlobal("fetch", fetch);
  const wrapper = mountPanel();
  await flushPromises();

  expect(wrapper.get('[data-testid="skill-catalog-empty"]').text()).toContain("暂无已发布 Skill");
  await wrapper.get('[aria-label="向 AI 提问"]').setValue("当前问题");
  await wrapper.get('[aria-label="发送"]').trigger("click");
  await flushPromises();

  const body = JSON.parse(fetch.mock.calls[0][1].body);
  expect(body.messages.at(-1).parts).toHaveLength(1);
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
  const traces = wrapper.findAll('[data-testid="agent-skill-load"]');
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

  expectSourceCards(wrapper);
  const failed = wrapper.findAll('[data-testid="agent-skill-load"]')[1];
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
  expect(wrapper.find('[data-source-ref="case:c-42"]').text()).toContain("当前权限不可读取");
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

  const trace = wrapper.get('[data-testid="agent-skill-load"]');
  expect(trace.text()).toContain("future_tool · 已完成");
  expect(trace.text()).not.toContain("内部参数");
  expect(trace.find("pre").exists()).toBe(false);
});

it("hides tool duration for restored snapshots without live timing", async () => {
  api.agentThread.mockResolvedValue(structuredClone(tracerSnapshot()));
  const wrapper = mountPanel();
  await flushPromises();

  const summaries = wrapper.findAll('[data-testid="agent-skill-load"] summary span');
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
  expect(wrapper.get('[data-testid="agent-skill-load"]').text()).not.toMatch(/检索案例 · 已完成 · \d+(\.\d+)?s/);
});

it("renders persisted tool duration by tool call id", async () => {
  const tracer = tracerSnapshot();
  tracer.latestRun.toolTimings = {
    t2: { toolCallId: "t2", toolName: "search_corpus", startedAt: "2026-09-07T10:00:00Z", finishedAt: "2026-09-07T10:00:02.5Z" },
  };
  api.agentThread.mockResolvedValue(tracer);
  const wrapper = mountPanel();
  await flushPromises();
  const searchTrace = wrapper.findAll('[data-testid="agent-skill-load"]')
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

function selectionContext() {
  return { from: 9, to: 13, sameBlock: true, quote: "第二段原文", quoteHash: "quote-hash", revision: 3 };
}

it("sends the selected text as a structured selection part", async () => {
  const fetch = vi.fn().mockResolvedValue(answerResponse());
  vi.stubGlobal("fetch", fetch);
  const wrapper = mount(AgentChatPanel, { props: { caseRecord: { id: "case-1" }, writingContext: selectionContext() }, global: { stubs: { RouterLink: true } } });
  await flushPromises();

  expect(wrapper.get('[data-testid="composer-selection"]').text()).toContain("正文上下文");
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
  await flushPromises();

  await wrapper.get('[data-testid="agent-accept"]').trigger("click");
  await flushPromises();

  expect(api.agentDecide).toHaveBeenCalledWith("case-1", "thread-tracer", "artifact-9", "accepted", "csrf");
  expect(wrapper.emitted("case-revised")[0][0]).toMatchObject({ id: "case-1", revision: 2 });
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
  expect(wrapper.get('[data-testid="agent-source"]').text()).toContain("以科学家精神为例");
  const artifact = wrapper.get('[data-testid="agent-artifact"]');
  expect(artifact.attributes("data-artifact-status")).toBe("accepted");
  expect(artifact.text()).toContain("状态：已接受");
  expect(wrapper.find('[data-testid="agent-accept"]').exists()).toBe(false);
  expect(wrapper.find('[data-testid="agent-reject"]').exists()).toBe(false);
});
