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
    aiSettings: vi.fn(),
  },
}));

function message(id, text) {
  return { id, role: "user", metadata: {}, parts: [{ type: "text", text }] };
}

function snapshotOf(id, title, messages = []) {
  return {
    id, caseId: "case-1", title, eventSeq: 4, messages,
    artifacts: [], activeRun: null, latestRun: null,
  };
}

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
