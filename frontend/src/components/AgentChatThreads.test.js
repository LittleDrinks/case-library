import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, expect, it, vi } from "vitest";
import AgentChatPanel from "./AgentChatPanel.vue";
import { api } from "../api.js";
import { session } from "../session.js";

vi.mock("../api.js", () => ({
  api: {
    agentThread: vi.fn(),
    agentThreads: vi.fn(),
    agentCreateThread: vi.fn(),
    agentRenameThread: vi.fn(),
    agentDecide: vi.fn(),
    agentCancel: vi.fn(),
    aiSettings: vi.fn(),
  },
}));

function message(id, text) {
  return { id, role: "user", metadata: {}, parts: [{ type: "text", text }] };
}

function snapshotOf(id, title, messages = [], artifacts = []) {
  return {
    id, caseId: "case-1", title, eventSeq: 4, messages,
    artifacts, activeRun: null, latestRun: null,
  };
}

const pendingArtifact = {
  id: "artifact-1", caseId: "case-1", threadId: "thread-1", runId: "run-1",
  status: "pending", baseRevision: 1,
  target: { paragraphIndex: 1, quote: "第二段原文" },
  replacement: "替换后的第二段", reason: "补充评价依据", sources: [],
};

const snapshots = {
  "thread-1": snapshotOf("thread-1", "默认对话", [message("m-1", "默认消息")]),
  "thread-2": snapshotOf("thread-2", "资料梳理", [message("m-2", "第二对话消息")]),
};

const threadRows = [
  { id: "thread-1", title: "默认对话", isDefault: true, running: false, createdAt: "2026-09-01T08:00:00Z", updatedAt: "2026-09-01T09:00:00Z" },
  { id: "thread-2", title: "资料梳理", isDefault: false, running: true, createdAt: "2026-09-01T10:00:00Z", updatedAt: "2026-09-01T11:00:00Z" },
];

function mountPanel() {
  return mount(AgentChatPanel, {
    props: { caseRecord: { id: "case-1" } },
    global: { stubs: { RouterLink: true } },
  });
}

async function openList(wrapper) {
  await wrapper.get('[data-testid="agent-thread-list-open"]').trigger("click");
  await flushPromises();
}

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  session.csrfToken = "csrf";
  api.agentThread.mockImplementation((caseId, threadId) => Promise.resolve(
    structuredClone(snapshots[threadId || "thread-1"]),
  ));
  api.agentThreads.mockResolvedValue(structuredClone(threadRows));
  api.aiSettings.mockResolvedValue({ configured: true, effectiveModel: "model-a" });
});

it("opens the thread list with rows, status, back and create entries", async () => {
  const wrapper = mountPanel();
  await flushPromises();

  await openList(wrapper);

  expect(api.agentThreads).toHaveBeenCalledWith("case-1");
  const list = wrapper.get('[data-testid="agent-thread-list"]');
  expect(list.text()).toContain("返回当前对话");
  expect(list.text()).toContain("新建对话");
  const rows = wrapper.findAll('[data-testid="agent-thread-open"]');
  expect(rows).toHaveLength(2);
  expect(rows[1].text()).toContain("资料梳理");
  expect(rows[1].text()).toContain("生成中");
  expect(wrapper.find('[aria-label="向 AI 提问"]').exists()).toBe(false);
});

it("switches to another thread and shows only its messages", async () => {
  const wrapper = mountPanel();
  await flushPromises();
  expect(wrapper.text()).toContain("默认消息");

  await openList(wrapper);
  await wrapper.findAll('[data-testid="agent-thread-open"]')[1].trigger("click");
  await flushPromises();

  expect(api.agentThread).toHaveBeenCalledWith("case-1", "thread-2");
  expect(wrapper.text()).toContain("第二对话消息");
  expect(wrapper.text()).not.toContain("默认消息");
  expect(localStorage.getItem("agent-thread:case-1")).toBe("thread-2");
  expect(wrapper.get(".agent-thread-current").text()).toContain("资料梳理");
});

it("creates a new thread into an empty chat with a fixed composer", async () => {
  api.agentCreateThread.mockResolvedValue({ id: "thread-3" });
  snapshots["thread-3"] = snapshotOf("thread-3", null);
  const wrapper = mountPanel();
  await flushPromises();

  await openList(wrapper);
  await wrapper.get('[data-testid="agent-thread-create"]').trigger("click");
  await flushPromises();

  expect(api.agentCreateThread).toHaveBeenCalledWith("case-1", null, "csrf");
  expect(wrapper.findAll(".ai-message")).toHaveLength(0);
  expect(wrapper.get('[aria-label="向 AI 提问"]').exists()).toBe(true);
  expect(wrapper.get(".agent-thread-current").text()).toContain("未命名对话");
});

it("renames the current thread from the list", async () => {
  api.agentRenameThread.mockResolvedValue({ id: "thread-1", title: "新标题" });
  const wrapper = mountPanel();
  await flushPromises();

  await openList(wrapper);
  await wrapper.findAll('[data-testid="agent-thread-rename"]')[0].trigger("click");
  await wrapper.get('[data-testid="agent-thread-rename-input"]').setValue("新标题");
  await wrapper.get('[data-testid="agent-thread-rename-confirm"]').trigger("click");
  await flushPromises();

  expect(api.agentRenameThread).toHaveBeenCalledWith("case-1", "thread-1", "新标题", "csrf");
  await wrapper.get('[data-testid="agent-thread-back"]').trigger("click");
  await flushPromises();
  expect(wrapper.get(".agent-thread-current").text()).toContain("新标题");
});

it("restores the locally preferred thread on reload", async () => {
  localStorage.setItem("agent-thread:case-1", "thread-2");

  const wrapper = mountPanel();
  await flushPromises();

  expect(api.agentThread).toHaveBeenCalledWith("case-1", "thread-2");
  expect(wrapper.text()).toContain("第二对话消息");
  expect(wrapper.text()).not.toContain("默认消息");
});

it("falls back to the default thread when the preference is stale", async () => {
  localStorage.setItem("agent-thread:case-1", "thread-gone");
  const notFound = Object.assign(new Error("对话不存在"), { status: 404 });
  api.agentThread.mockImplementation((caseId, threadId) => (
    threadId ? Promise.reject(notFound) : Promise.resolve(structuredClone(snapshots["thread-1"]))
  ));

  const wrapper = mountPanel();
  await flushPromises();

  expect(api.agentThread).toHaveBeenCalledWith("case-1", "thread-gone");
  expect(api.agentThread).toHaveBeenLastCalledWith("case-1");
  expect(wrapper.text()).toContain("默认消息");
});

it("keeps a pending artifact scoped to its thread and decidable after switching back", async () => {
  snapshots["thread-1"] = snapshotOf("thread-1", "默认对话", [message("m-1", "默认消息")], [pendingArtifact]);
  api.agentDecide.mockResolvedValue({ artifact: { status: "rejected" }, case: null });
  const wrapper = mountPanel();
  await flushPromises();
  expect(wrapper.get('[data-testid="agent-artifact"]').text()).toContain("待确认");
  await openList(wrapper);
  await wrapper.findAll('[data-testid="agent-thread-open"]')[1].trigger("click");
  await flushPromises();
  expect(wrapper.find('[data-testid="agent-artifact"]').exists()).toBe(false);
  await openList(wrapper);
  await wrapper.findAll('[data-testid="agent-thread-open"]')[0].trigger("click");
  await flushPromises();
  expect(wrapper.get('[data-testid="agent-artifact"]').attributes("data-artifact-status")).toBe("pending");
  await wrapper.get('[data-testid="agent-reject"]').trigger("click");
  await flushPromises();
  expect(api.agentDecide).toHaveBeenCalledWith("case-1", "thread-1", "artifact-1", "rejected", "csrf");
});

it("restores the saved scroll position when switching back", async () => {
  const wrapper = mountPanel();
  await flushPromises();
  wrapper.get(".panel-scroll").element.scrollTop = 120;

  await openList(wrapper);
  await wrapper.findAll('[data-testid="agent-thread-open"]')[1].trigger("click");
  await flushPromises();
  expect(wrapper.get(".panel-scroll").element.scrollTop).toBe(0);

  await openList(wrapper);
  await wrapper.findAll('[data-testid="agent-thread-open"]')[0].trigger("click");
  await flushPromises();

  expect(wrapper.get(".panel-scroll").element.scrollTop).toBe(120);
});

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

function resumeChunks() {
  return [
    'data: {"type":"start","messageId":"message-resumed"}\n\n',
    'data: {"type":"start-step"}\n\n',
    'data: {"type":"text-start","id":"text-resumed"}\n\n',
    'data: {"type":"text-delta","id":"text-resumed","delta":"恢复回答"}\n\n',
    'data: {"type":"text-end","id":"text-resumed"}\n\n',
    'data: {"type":"finish-step"}\n\n',
    'data: {"type":"finish","finishReason":"stop"}\n\n',
    "data: [DONE]\n\n",
  ];
}

function resumeResponse() {
  return streamResponse(resumeChunks());
}

function runningThread() {
  return {
    ...snapshotOf("thread-1", "默认对话", [message("m-1", "生成中的问题")]),
    eventSeq: 2,
    activeRun: { id: "run-1", status: "active" },
    latestRun: { id: "run-1", status: "active" },
  };
}

function mountRunning(fetch) {
  api.agentThread.mockImplementation((caseId, threadId) => Promise.resolve(
    structuredClone(threadId === "thread-2" ? snapshots["thread-2"] : runningThread()),
  ));
  vi.stubGlobal("fetch", fetch);
  return mountPanel();
}

async function switchTo(wrapper, index) {
  await openList(wrapper);
  await wrapper.findAll('[data-testid="agent-thread-open"]')[index].trigger("click");
  await new Promise((resolve) => setTimeout(resolve, 0));
  await flushPromises();
}

function eventCalls(fetch) {
  return fetch.mock.calls.map(([url]) => url).filter((url) => url.includes("/events"));
}

it("reconnects the running thread's event stream after switching away and back", async () => {
  const fetch = vi.fn().mockImplementation(() => Promise.resolve(resumeResponse()));
  const wrapper = mountRunning(fetch);
  await flushPromises();
  await switchTo(wrapper, 1);
  expect(wrapper.text()).toContain("第二对话消息");
  await switchTo(wrapper, 0);
  expect(wrapper.text()).toContain("恢复回答");
  expect(eventCalls(fetch)).toEqual([
    "/api/cases/case-1/agent/thread/thread-1/events?afterSeq=2",
    "/api/cases/case-1/agent/thread/thread-1/events?afterSeq=2",
  ]);
  expect(fetch.mock.calls.filter(([url]) => url.includes("/stream"))).toHaveLength(0);
  expect(localStorage.getItem("agent-thread:case-1")).toBe("thread-1");
});

it("binds the cancel command to the thread selected at click time", async () => {
  const fetch = vi.fn().mockImplementation(() => Promise.resolve(resumeResponse()));
  api.agentCancel.mockResolvedValue({ runId: "run-1", status: "cancelling" });
  const wrapper = mountRunning(fetch);
  await flushPromises();
  expect(wrapper.find('[data-testid="agent-stop"]').exists()).toBe(true);
  await switchTo(wrapper, 1);
  expect(wrapper.find('[data-testid="agent-stop"]').exists()).toBe(false);
  await switchTo(wrapper, 0);
  await wrapper.get('[data-testid="agent-stop"]').trigger("click");
  await flushPromises();
  expect(api.agentCancel).toHaveBeenCalledWith("case-1", "thread-1", "csrf");
});

function cancelledThread() {
  return { ...runningThread(), activeRun: null, latestRun: { id: "run-1", status: "cancelled" } };
}

function deliverCancelled(streams, encoder) {
  streams[1].controller.enqueue(
    encoder.encode('data: {"type":"abort","reason":"运行已取消"}\n\n'),
  );
  streams[1].controller.enqueue(encoder.encode("data: [DONE]\n\n"));
  streams[1].controller.close();
}

async function stopWhileActive() {
  const streams = [];
  const fetch = heldFetch(streams);
  let snap = runningThread();
  api.agentThread.mockImplementation(() => Promise.resolve(structuredClone(snap)));
  api.agentCancel.mockResolvedValue({ runId: "run-1", status: "cancelling" });
  vi.stubGlobal("fetch", fetch);
  const wrapper = mountPanel();
  await flushPromises();
  expect(streams).toHaveLength(1);
  await wrapper.get('[data-testid="agent-stop"]').trigger("click");
  await flushPromises();
  return { wrapper, fetch, streams, setSnap: (value) => { snap = value; } };
}

it("settles a still-active run through the resumed stream after cancel ACK", async () => {
  const { wrapper, fetch, streams, setSnap } = await stopWhileActive();
  expect(api.agentCancel).toHaveBeenCalledWith("case-1", "thread-1", "csrf");
  expect(eventCalls(fetch)).toHaveLength(2);
  expect(fetch.mock.calls.filter(([url]) => url.includes("/stream"))).toHaveLength(0);
  expect(wrapper.get(".agent-chat-panel").attributes("data-run-status")).toBe("active");
  expect(wrapper.get('[data-testid="agent-stop"]').exists()).toBe(true);
  setSnap(cancelledThread());
  deliverCancelled(streams, new TextEncoder());
  await flushPromises();
  expect(wrapper.find('[data-testid="agent-stop"]').exists()).toBe(false);
  expect(wrapper.get('textarea[aria-label="向 AI 提问"]').attributes("disabled")).toBeUndefined();
  expect(wrapper.get('[role="alert"]').text()).toContain("运行已取消");
  expect(wrapper.get(".agent-chat-panel").attributes("data-run-status")).toBe("cancelled");
  expect(wrapper.findAll(".ai-message.user")).toHaveLength(1);
  expect(wrapper.findAll(".ai-message.assistant")).toHaveLength(0);
});

function heldFetch(streams) {
  return vi.fn().mockImplementation(() => {
    const held = {};
    held.stream = new ReadableStream({ start(controller) { held.controller = controller; } });
    streams.push(held);
    return Promise.resolve(new Response(held.stream, {
      status: 200,
      headers: { "Content-Type": "text/event-stream", "x-vercel-ai-ui-message-stream": "v1" },
    }));
  });
}

it("shows conversation and stop before the resumed stream terminates", async () => {
  const streams = [];
  const wrapper = mountRunning(heldFetch(streams));
  await flushPromises();
  expect(wrapper.get('[data-testid="agent-stop"]').exists()).toBe(true);
  await switchTo(wrapper, 1);
  await switchTo(wrapper, 0);
  expect(wrapper.find('[data-testid="agent-thread-list"]').exists()).toBe(false);
  expect(wrapper.text()).toContain("生成中的问题");
  expect(wrapper.get('[data-testid="agent-stop"]').exists()).toBe(true);
  expect(streams).toHaveLength(2);
});

it("disconnects the superseded stream reader on switch without a server cancel", async () => {
  const fetch = heldFetch([]);
  const wrapper = mountRunning(fetch);
  await flushPromises();
  const resumed = fetch.mock.calls.find(([url]) => url.includes("/events"));
  await switchTo(wrapper, 1);
  expect(resumed[1].signal.aborted).toBe(true);
  expect(api.agentCancel).not.toHaveBeenCalled();
  await switchTo(wrapper, 0);
  expect(api.agentCancel).not.toHaveBeenCalled();
});

it("disconnects the stream reader on unmount without a server cancel", async () => {
  const fetch = heldFetch([]);
  const wrapper = mountRunning(fetch);
  await flushPromises();
  const resumed = fetch.mock.calls.find(([url]) => url.includes("/events"));
  wrapper.unmount();
  expect(resumed[1].signal.aborted).toBe(true);
  expect(api.agentCancel).not.toHaveBeenCalled();
});

it("keeps the current stream connected while the thread list is open", async () => {
  const fetch = heldFetch([]);
  const wrapper = mountRunning(fetch);
  await flushPromises();
  const resumed = fetch.mock.calls.find(([url]) => url.includes("/events"));
  await openList(wrapper);
  expect(resumed[1].signal.aborted).toBe(false);
  expect(wrapper.get('[data-testid="agent-thread-list"]').text()).toContain("生成中");
});

it("ignores the old thread's late stream completion after switching away", async () => {
  const streams = [];
  const encoder = new TextEncoder();
  const wrapper = mountRunning(heldFetch(streams));
  await flushPromises();
  await switchTo(wrapper, 1);
  try {
    streams[0].controller.enqueue(encoder.encode('data: {"type":"finish","finishReason":"stop"}\n\n'));
    streams[0].controller.close();
  } catch { /* 旧读取端已断开 */ }
  await flushPromises();
  expect(wrapper.text()).toContain("第二对话消息");
  expect(wrapper.text()).not.toContain("生成中的问题");
  expect(localStorage.getItem("agent-thread:case-1")).toBe("thread-2");
});

it("resumes a held stream to completion without duplicating messages", async () => {
  const streams = [];
  const encoder = new TextEncoder();
  const wrapper = mountRunning(heldFetch(streams));
  await flushPromises();
  resumeChunks().forEach((chunk) => streams[0].controller.enqueue(encoder.encode(chunk)));
  streams[0].controller.close();
  await flushPromises();
  expect(wrapper.text()).toContain("恢复回答");
  expect(wrapper.findAll(".ai-message.user")).toHaveLength(1);
  expect(wrapper.findAll(".ai-message.assistant")).toHaveLength(1);
  expect(wrapper.get(".agent-chat-panel").attributes("data-run-id")).toBe("run-1");
});

it("cannot let a late artifact decision overwrite the newly selected thread", async () => {
  snapshots["thread-1"] = snapshotOf("thread-1", "默认对话", [message("m-1", "默认消息")], [pendingArtifact]);
  let release;
  api.agentDecide.mockImplementation(() => new Promise((resolve) => { release = resolve; }));
  const wrapper = mountPanel();
  await flushPromises();
  await wrapper.get('[data-testid="agent-reject"]').trigger("click");
  await switchTo(wrapper, 1);
  release({ artifact: { status: "rejected" }, case: null });
  await flushPromises();
  expect(api.agentDecide).toHaveBeenCalledWith("case-1", "thread-1", "artifact-1", "rejected", "csrf");
  expect(wrapper.text()).toContain("第二对话消息");
  expect(wrapper.find('[data-testid="agent-artifact"]').exists()).toBe(false);
});

it("keeps refreshing run state while the thread list stays open", async () => {
  vi.useFakeTimers();
  try {
    const wrapper = mountPanel();
    await vi.advanceTimersByTimeAsync(1);
    await wrapper.get('[data-testid="agent-thread-list-open"]').trigger("click");
    await vi.advanceTimersByTimeAsync(1);
    expect(wrapper.text()).toContain("生成中");
    api.agentThreads.mockResolvedValue(threadRows.map((row) => ({ ...row, running: false })));
    await vi.advanceTimersByTimeAsync(2000);
    expect(wrapper.text()).not.toContain("生成中");
    wrapper.unmount();
  } finally {
    vi.useRealTimers();
  }
});
