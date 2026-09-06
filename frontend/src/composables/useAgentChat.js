import { Chat } from "@ai-sdk/vue";
import { DefaultChatTransport } from "ai";
import { computed, onBeforeUnmount, ref, shallowRef } from "vue";
import { api } from "../api.js";
import { session } from "../session.js";

export const CASE_EDIT_SKILL_ID = "case-edit-skill";

function textParts(message) {
  return (message?.parts || [])
    .filter((part) => part.type === "text")
    .map((part) => part.text)
    .join("");
}

function projectMessages(messages = []) {
  return messages.map(({ id, role, metadata, parts }) => ({ id, role, metadata, parts }));
}

function agentPath(caseId, threadId) {
  return `/api/cases/${encodeURIComponent(caseId)}/agent/thread/${encodeURIComponent(threadId)}/stream`;
}

function eventsPath(caseId, threadId, afterSeq) {
  return `/api/cases/${encodeURIComponent(caseId)}/agent/thread/`
    + `${encodeURIComponent(threadId)}/events?afterSeq=${afterSeq}`;
}

function transport(caseId, threadId, state) {
  return new DefaultChatTransport({
    api: agentPath(caseId, threadId),
    credentials: "same-origin",
    headers: () => ({ "X-CSRF-Token": session.csrfToken }),
    prepareSendMessagesRequest: ({ id, messages, body, trigger, messageId }) => ({
      body: { ...body, id, messages: projectMessages(messages), trigger, messageId },
    }),
    prepareReconnectToStreamRequest: () => ({
      api: eventsPath(caseId, threadId, state.snapshot.value?.eventSeq ?? 0),
    }),
  });
}

function buildChat(caseId, snapshot, state) {
  return new Chat({
    id: snapshot.id,
    messages: projectMessages(snapshot.messages),
    transport: transport(caseId, snapshot.id, state),
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

function chatIdle(chat) {
  return !chat || ["ready", "error"].includes(chat.status);
}

async function refreshSnapshot(caseId, state, generation) {
  const snapshot = await api.agentThread(caseId);
  if (isCurrent(state, generation)) state.snapshot.value = snapshot;
  return snapshot;
}

async function rebuild(caseId, state, generation, force = false) {
  const snapshot = await refreshSnapshot(caseId, state, generation);
  if (isCurrent(state, generation) && (force || chatIdle(state.chat.value))) {
    state.chat.value = buildChat(caseId, snapshot, state);
  }
  return snapshot;
}

async function resume(caseId, state, generation) {
  const chat = state.chat.value;
  if (!chat || !state.snapshot.value?.activeRun || !chatIdle(chat)) return;
  await chat.resumeStream();
  if (isCurrent(state, generation)) await refreshSnapshot(caseId, state, generation);
}

async function settle(caseId, state, generation, { fresh = false } = {}) {
  const snapshot = await (fresh
    ? rebuild(caseId, state, generation)
    : refreshSnapshot(caseId, state, generation));
  if (!isCurrent(state, generation) || !snapshot?.activeRun || !chatIdle(state.chat.value)) return;
  await resume(caseId, state, generation);
}

async function loadChat(caseId, state, generation) {
  state.loading.value = true;
  state.error.value = "";
  const results = await Promise.allSettled([api.agentThread(caseId), api.aiSettings()]);
  if (!isCurrent(state, generation)) return;
  const [threadResult, settingsResult] = results;
  if (threadResult.status === "fulfilled") {
    state.snapshot.value = threadResult.value;
    state.chat.value = buildChat(caseId, threadResult.value, state);
  } else state.error.value = threadResult.reason.message || "对话加载失败";
  if (settingsResult.status === "fulfilled") state.settings.value = settingsResult.value;
  else if (!state.error.value) state.error.value = settingsResult.reason.message || "AI 配置加载失败";
  state.loading.value = false;
  await resume(caseId, state, generation);
}

async function sendChat(caseId, state, text, generation) {
  if (!isCurrent(state, generation) || !state.chat.value) return;
  try {
    await state.chat.value.sendMessage({
      parts: [
        { type: "text", text },
        { type: "data-skill", data: { skillId: CASE_EDIT_SKILL_ID } },
      ],
    });
  } finally {
    if (isCurrent(state, generation)) await settle(caseId, state, generation);
  }
}

function stopRequested(state) {
  const chat = state.chat.value;
  const chatStreaming = chat != null && ["streaming", "submitted"].includes(chat.status);
  return chatStreaming || Boolean(state.snapshot.value?.activeRun);
}

async function stopChat(caseId, state, generation) {
  const thread = state.chat.value?.id || state.snapshot.value?.id;
  if (!isCurrent(state, generation) || !thread || !stopRequested(state)) return;
  state.stopping.value = true;
  try {
    await api.agentCancel(caseId, thread, session.csrfToken);
    await rebuild(caseId, state, generation, true);
  } finally {
    state.stopping.value = false;
  }
}

async function retryChat(caseId, state, generation, messageId) {
  if (!isCurrent(state, generation) || !state.chat.value) return;
  await rebuild(caseId, state, generation);
  if (!isCurrent(state, generation) || !state.chat.value) return;
  try {
    await state.chat.value.regenerate({ messageId });
  } finally {
    if (isCurrent(state, generation)) await settle(caseId, state, generation);
  }
}

async function decideArtifact(caseId, state, generation, artifactId, decision) {
  const result = await api.agentDecide(caseId, artifactId, decision, session.csrfToken);
  if (isCurrent(state, generation)) await refreshSnapshot(caseId, state, generation);
  return result;
}

function createState() {
  return {
    snapshot: ref(null), settings: ref(null), chat: shallowRef(null),
    loading: ref(true), error: ref(""), stopping: ref(false),
    generation: 0, disposed: false,
  };
}

function retryMessageId(state) {
  const snapshot = state.snapshot.value;
  const run = snapshot?.latestRun;
  const messages = snapshot?.messages || [];
  const last = messages.at(-1);
  if (run?.status !== "failed" || last?.role !== "user") return "";
  return last.id;
}

function computedState(state) {
  return {
    messages: computed(() => state.chat.value?.messages || state.snapshot.value?.messages || []),
    artifacts: computed(() => state.snapshot.value?.artifacts || []),
    status: computed(() => {
      const chatStatus = state.chat.value?.status;
      return chatStatus && chatStatus !== "ready" ? chatStatus : snapshotStatus(state.snapshot.value);
    }),
    chatError: computed(() => snapshotError(state.snapshot.value) || state.chat.value?.error?.message || ""),
    threadState: computed(() => state.snapshot.value),
    stopping: computed(() => Boolean(state.stopping.value)),
    retryableMessageId: computed(() => retryMessageId(state)),
  };
}

function reload(caseId, state) {
  state.generation += 1;
  return loadChat(caseId, state, state.generation);
}

function bindLifecycle(state, recover) {
  window.addEventListener("online", recover);
  onBeforeUnmount(() => {
    window.removeEventListener("online", recover);
    state.disposed = true;
    state.generation += 1;
  });
}

export function useAgentChat(caseId) {
  const state = createState();
  const at = () => state.generation;
  const send = (text) => sendChat(caseId, state, text, at());
  const stop = () => stopChat(caseId, state, at());
  const retry = (messageId) => retryChat(caseId, state, at(), messageId);
  const decide = (artifactId, decision) => decideArtifact(caseId, state, at(), artifactId, decision);
  const recover = () => {
    if (!state.snapshot.value?.activeRun) return;
    return resume(caseId, state, at());
  };
  bindLifecycle(state, recover);
  void reload(caseId, state);
  return {
    ...computedState(state), loading: state.loading, error: state.error,
    settings: state.settings, textParts, send, stop, retry, decide, reload: () => reload(caseId, state),
  };
}
