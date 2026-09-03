import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, expect, it, vi } from "vitest";
import AgentChatPanel from "./AgentChatPanel.vue";
import { api } from "../api.js";
import { session } from "../session.js";

vi.mock("../api.js", () => ({
  api: { agentThread: vi.fn(), aiSettings: vi.fn(), agentDecide: vi.fn() },
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
  session.csrfToken = "csrf";
  api.agentThread.mockResolvedValue(structuredClone(snapshot));
  api.aiSettings.mockResolvedValue({ configured: true, effectiveModel: "model-a" });
});

it("restores the server thread and sends one turn through the SDK transport", async () => {
  const fetch = vi.fn().mockResolvedValue(answerResponse());
  vi.stubGlobal("fetch", fetch);
  const wrapper = mountPanel();
  await flushPromises();

  expect(wrapper.text()).toContain("历史回答");
  await wrapper.get('[aria-label="向 AI 提问"]').setValue("当前问题");
  await wrapper.get('[aria-label="发送"]').trigger("click");
  await flushPromises();

  const [url, options] = fetch.mock.calls[0];
  const body = JSON.parse(options.body);
  expect(url).toBe("/api/cases/case-1/agent/thread/thread-1/stream");
  expect(new Headers(options.headers).get("X-CSRF-Token")).toBe("csrf");
  expect(body.trigger).toBe("submit-message");
  expect(body.messages.at(-1).parts[0].text).toBe("当前问题");
  expect(wrapper.text()).toContain("确定回答");
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

function tracerMessages() {
  return [{
    id: "message-user", role: "user", metadata: {},
    parts: [
      { type: "text", text: "请结合平台资料修订第2段" },
      { type: "data-skill", data: { skillId: "case-edit-skill" } },
    ],
  }, {
    id: "message-assistant", role: "assistant", metadata: {},
    parts: [
      { type: "tool-load_capability", toolCallId: "t1", state: "output-available", input: { id: "case-edit-skill" }, output: { instructions: "SKILL" } },
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
