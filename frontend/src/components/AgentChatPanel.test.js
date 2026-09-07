import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, expect, it, vi } from "vitest";
import AgentChatPanel from "./AgentChatPanel.vue";
import { api } from "../api.js";
import { session } from "../session.js";

vi.mock("../api.js", () => ({
  api: {
    agentThread: vi.fn(), aiSettings: vi.fn(), agentDecide: vi.fn(),
    agentCancel: vi.fn(), agentThreads: vi.fn(), listSkills: vi.fn(),
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

function mountPanel() {
  return mount(AgentChatPanel, {
    props: { caseRecord: { id: "case-1" } },
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
    target: { paragraphIndex: 1, quote: "第二段原文" },
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
    latestRun: { id: "run-1", status: "completed" },
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
  expect(wrapper.text()).toContain("已生成单段修订候选");
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
