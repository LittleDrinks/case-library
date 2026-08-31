import { Chat } from "@ai-sdk/vue";
import { DefaultChatTransport } from "ai";
import { computed, onBeforeUnmount, ref, shallowRef } from "vue";
import { api } from "../api.js";
import { session } from "../session.js";

function textParts(message) {
  return (message?.parts || [])
    .filter((part) => part.type === "text")
    .map((part) => part.text)
    .join("");
}

function protocolMessages(messages) {
  return messages.map(({ id, role, metadata, parts }) => ({ id, role, metadata, parts }));
}

function agentPath(caseId, threadId) {
  return `/api/cases/${encodeURIComponent(caseId)}/agent/thread/${encodeURIComponent(threadId)}/stream`;
}

function transport(caseId, threadId) {
  return new DefaultChatTransport({
    api: agentPath(caseId, threadId),
    credentials: "same-origin",
    headers: () => ({ "X-CSRF-Token": session.csrfToken }),
    prepareSendMessagesRequest: ({ id, messages, body, trigger, messageId }) => ({
      body: { ...body, id, messages: protocolMessages(messages), trigger, messageId },
    }),
  });
}

function chatMessages(snapshot) {
  return (snapshot.messages || []).map(({ id, role, metadata, parts }) => ({
    id, role, metadata, parts,
  }));
}

function buildChat(caseId, snapshot) {
  return new Chat({
    id: snapshot.id,
    messages: chatMessages(snapshot),
    transport: transport(caseId, snapshot.id),
  });
}

function snapshotStatus(snapshot) {
  if (snapshot?.activeRun) return "streaming";
  return ["failed", "cancelled"].includes(snapshot?.latestRun?.status) ? "error" : "ready";
}

function snapshotError(snapshot) {
  const run = snapshot?.latestRun;
  if (!run || !["failed", "cancelled"].includes(run.status)) return "";
  return run.error || (run.status === "cancelled" ? "运行已取消" : "AI 服务暂不可用");
}

function isCurrent(state, generation) {
  return !state.disposed && state.generation === generation;
}

async function refreshSnapshot(caseId, state, generation) {
  const snapshot = await api.agentThread(caseId);
  if (isCurrent(state, generation)) state.snapshot.value = snapshot;
}

async function loadChat(caseId, state, generation) {
  state.loading.value = true;
  state.error.value = "";
  const results = await Promise.allSettled([api.agentThread(caseId), api.aiSettings()]);
  if (!isCurrent(state, generation)) return;
  const [threadResult, settingsResult] = results;
  if (threadResult.status === "fulfilled") {
    state.snapshot.value = threadResult.value;
    state.chat.value = buildChat(caseId, threadResult.value);
  } else state.error.value = threadResult.reason.message || "对话加载失败";
  if (settingsResult.status === "fulfilled") state.settings.value = settingsResult.value;
  else if (!state.error.value) state.error.value = settingsResult.reason.message || "AI 配置加载失败";
  state.loading.value = false;
}

async function sendChat(caseId, state, text, generation) {
  if (!isCurrent(state, generation) || !state.chat.value) return;
  await state.chat.value.sendMessage({ text });
  if (isCurrent(state, generation)) await refreshSnapshot(caseId, state, generation);
}

function createState() {
  return {
    snapshot: ref(null), settings: ref(null), chat: shallowRef(null),
    loading: ref(true), error: ref(""), generation: 0, disposed: false,
  };
}

function computedState(state) {
  return {
    messages: computed(() => state.chat.value?.messages || state.snapshot.value?.messages || []),
    status: computed(() => {
      const chatStatus = state.chat.value?.status;
      return chatStatus && chatStatus !== "ready" ? chatStatus : snapshotStatus(state.snapshot.value);
    }),
    chatError: computed(() => state.chat.value?.error?.message || snapshotError(state.snapshot.value)),
  };
}

export function useAgentChat(caseId) {
  const state = createState();
  const load = () => {
    state.generation += 1;
    return loadChat(caseId, state, state.generation);
  };
  const send = (text) => sendChat(caseId, state, text, state.generation);
  onBeforeUnmount(() => {
    state.disposed = true;
    state.generation += 1;
  });
  void load();
  return {
    ...computedState(state),
    loading: state.loading, error: state.error, settings: state.settings,
    textParts, send, reload: load,
  };
}
