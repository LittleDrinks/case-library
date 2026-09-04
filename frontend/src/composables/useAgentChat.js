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

function transport(caseId, threadId) {
  return new DefaultChatTransport({
    api: agentPath(caseId, threadId),
    credentials: "same-origin",
    headers: () => ({ "X-CSRF-Token": session.csrfToken }),
    prepareSendMessagesRequest: ({ id, messages, body, trigger, messageId }) => ({
      body: { ...body, id, messages: projectMessages(messages), trigger, messageId },
    }),
  });
}

function buildChat(caseId, snapshot) {
  return new Chat({
    id: snapshot.id,
    messages: projectMessages(snapshot.messages),
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

function readPreference(caseId) {
  try {
    return localStorage.getItem(`agent-thread:${caseId}`) || null;
  } catch {
    return null;
  }
}

function writePreference(caseId, threadId) {
  try {
    localStorage.setItem(`agent-thread:${caseId}`, threadId);
  } catch {
    // 选择偏好只是本地记录，写入失败不影响对话
  }
}

async function resolveSnapshot(caseId) {
  const preferred = readPreference(caseId);
  if (!preferred) return api.agentThread(caseId);
  try {
    return await api.agentThread(caseId, preferred);
  } catch (error) {
    if (error.status !== 404) throw error;
    return api.agentThread(caseId);
  }
}

async function refreshSnapshot(caseId, state, generation) {
  const snapshot = await api.agentThread(caseId, state.threadId.value);
  if (isCurrent(state, generation)) state.snapshot.value = snapshot;
}

async function loadChat(caseId, state, generation) {
  state.loading.value = true;
  state.error.value = "";
  const results = await Promise.allSettled([resolveSnapshot(caseId), api.aiSettings()]);
  if (!isCurrent(state, generation)) return;
  const [threadResult, settingsResult] = results;
  if (threadResult.status === "fulfilled") {
    state.snapshot.value = threadResult.value;
    state.threadId.value = threadResult.value.id;
    state.chat.value = buildChat(caseId, threadResult.value);
  } else state.error.value = threadResult.reason.message || "对话加载失败";
  if (settingsResult.status === "fulfilled") state.settings.value = settingsResult.value;
  else if (!state.error.value) state.error.value = settingsResult.reason.message || "AI 配置加载失败";
  state.loading.value = false;
}

async function selectThread(caseId, state, threadId) {
  const generation = (state.generation += 1);
  state.loading.value = true;
  state.error.value = "";
  try {
    const snapshot = await api.agentThread(caseId, threadId);
    if (!isCurrent(state, generation)) return;
    state.snapshot.value = snapshot;
    state.threadId.value = snapshot.id;
    state.chat.value = buildChat(caseId, snapshot);
    writePreference(caseId, snapshot.id);
  } catch (requestError) {
    if (isCurrent(state, generation)) state.error.value = requestError.message || "对话加载失败";
  } finally {
    if (isCurrent(state, generation)) state.loading.value = false;
  }
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
    if (isCurrent(state, generation)) await refreshSnapshot(caseId, state, generation);
  }
}

async function decideArtifact(caseId, state, generation, artifactId, decision) {
  const result = await api.agentDecide(caseId, artifactId, decision, session.csrfToken);
  if (isCurrent(state, generation)) await refreshSnapshot(caseId, state, generation);
  return result;
}

async function renameThread(caseId, state, threadId, title) {
  const summary = await api.agentRenameThread(caseId, threadId, title, session.csrfToken);
  if (state.threadId.value === threadId && state.snapshot.value) {
    state.snapshot.value = { ...state.snapshot.value, title: summary.title };
  }
  return summary;
}

async function createThread(caseId, state) {
  const created = await api.agentCreateThread(caseId, null, session.csrfToken);
  await selectThread(caseId, state, created.id);
}

function threadActions(caseId, state) {
  return {
    listThreads: () => api.agentThreads(caseId),
    selectThread: (threadId) => selectThread(caseId, state, threadId),
    createThread: () => createThread(caseId, state),
    renameThread: (threadId, title) => renameThread(caseId, state, threadId, title),
  };
}

function createState() {
  return {
    snapshot: ref(null), settings: ref(null), chat: shallowRef(null),
    threadId: ref(null), loading: ref(true), error: ref(""), generation: 0, disposed: false,
  };
}

function computedState(state) {
  return {
    messages: computed(() => state.chat.value?.messages || state.snapshot.value?.messages || []),
    artifacts: computed(() => state.snapshot.value?.artifacts || []),
    threadId: computed(() => state.threadId.value),
    status: computed(() => {
      const chatStatus = state.chat.value?.status;
      return chatStatus && chatStatus !== "ready" ? chatStatus : snapshotStatus(state.snapshot.value);
    }),
    chatError: computed(() => snapshotError(state.snapshot.value) || state.chat.value?.error?.message || ""),
    threadState: computed(() => state.snapshot.value),
  };
}

export function useAgentChat(caseId) {
  const state = createState();
  const load = () => {
    state.generation += 1;
    return loadChat(caseId, state, state.generation);
  };
  const send = (text) => sendChat(caseId, state, text, state.generation);
  const decide = (artifactId, decision) => decideArtifact(caseId, state, state.generation, artifactId, decision);
  onBeforeUnmount(() => {
    state.disposed = true;
    state.generation += 1;
  });
  void load();
  return {
    ...computedState(state), ...threadActions(caseId, state),
    loading: state.loading, error: state.error, settings: state.settings,
    textParts, send, decide, reload: load,
  };
}
