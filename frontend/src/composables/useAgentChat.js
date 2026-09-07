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

function isCatalogCurrent(state, generation) {
  return !state.disposed && state.catalogGeneration === generation;
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

function isSelectedSkillValid(state) {
  const skillId = state.selectedSkillId.value;
  if (skillId === CASE_EDIT_SKILL_ID) return true;
  return state.catalog.value === "ready"
    && state.skills.value.some((skill) => skill.id === skillId);
}

function dropUnknownSkill(state) {
  const skillId = state.selectedSkillId.value;
  const known = skillId === CASE_EDIT_SKILL_ID
    || state.skills.value.some((skill) => skill.id === skillId);
  if (!known) state.selectedSkillId.value = CASE_EDIT_SKILL_ID;
}

function restoreSkill(state, snapshot) {
  const message = [...(snapshot.messages || [])].reverse().find((item) => item.role === "user");
  const skillId = message?.parts?.find((part) => part.type === "data-skill")?.data?.skillId;
  state.selectedSkillId.value = skillId || CASE_EDIT_SKILL_ID;
  if (state.catalog.value === "ready") dropUnknownSkill(state);
}

async function loadCatalog(state, generation) {
  state.catalog.value = "loading";
  try {
    const catalog = await api.listSkills();
    if (!isCatalogCurrent(state, generation)) return;
    state.skills.value = catalog || [];
    state.catalog.value = "ready";
    dropUnknownSkill(state);
  } catch {
    if (isCatalogCurrent(state, generation)) state.catalog.value = "error";
  }
}

function chatIdle(chat) {
  return !chat || ["ready", "error"].includes(chat.status);
}

function detachChat(state) {
  const chat = state.chat.value;
  if (!chat || chatIdle(chat)) return;
  void chat.stop().catch(() => {});
}

function replaceChat(state, chat) {
  detachChat(state);
  state.chat.value = chat;
}

async function refreshSnapshot(caseId, state, generation, threadId = state.threadId.value) {
  const snapshot = await api.agentThread(caseId, threadId);
  if (isCurrent(state, generation) && state.threadId.value === threadId) {
    state.snapshot.value = snapshot;
  }
  return snapshot;
}

async function rebuild(caseId, state, generation, threadId, force = false) {
  const snapshot = await refreshSnapshot(caseId, state, generation, threadId);
  if (isCurrent(state, generation) && (force || chatIdle(state.chat.value))) {
    replaceChat(state, buildChat(caseId, snapshot, state));
  }
  return snapshot;
}

async function resume(caseId, state, generation) {
  const chat = state.chat.value;
  const threadId = state.threadId.value;
  if (!chat || !state.snapshot.value?.activeRun || !chatIdle(chat)) return;
  await chat.resumeStream();
  if (isCurrent(state, generation)) await refreshSnapshot(caseId, state, generation, threadId);
}

function kickResume(caseId, state, generation) {
  void resume(caseId, state, generation).catch(() => {});
}

async function settle(caseId, state, generation, threadId, { fresh = false } = {}) {
  const snapshot = await (fresh
    ? rebuild(caseId, state, generation, threadId)
    : refreshSnapshot(caseId, state, generation, threadId));
  if (!isCurrent(state, generation) || !snapshot?.activeRun || !chatIdle(state.chat.value)) return;
  await resume(caseId, state, generation);
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
    restoreSkill(state, threadResult.value);
    replaceChat(state, buildChat(caseId, threadResult.value, state));
  } else state.error.value = threadResult.reason.message || "对话加载失败";
  if (settingsResult.status === "fulfilled") state.settings.value = settingsResult.value;
  else if (!state.error.value) state.error.value = settingsResult.reason.message || "AI 配置加载失败";
  state.loading.value = false;
  kickResume(caseId, state, generation);
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
    restoreSkill(state, snapshot);
    replaceChat(state, buildChat(caseId, snapshot, state));
    writePreference(caseId, snapshot.id);
  } catch (requestError) {
    if (isCurrent(state, generation)) state.error.value = requestError.message || "对话加载失败";
  } finally {
    if (isCurrent(state, generation)) state.loading.value = false;
  }
  kickResume(caseId, state, generation);
}

function messageParts(state, text, contextParts) {
  const parts = [{ type: "text", text }, ...contextParts];
  const skillId = state.selectedSkillId.value;
  if (skillId) parts.push({ type: "data-skill", data: { skillId } });
  return parts;
}

async function sendChat(caseId, state, text, generation, contextParts = []) {
  const threadId = state.threadId.value;
  if (!isCurrent(state, generation) || !state.chat.value) return;
  try {
    await state.chat.value.sendMessage({ parts: messageParts(state, text, contextParts) });
  } finally {
    if (isCurrent(state, generation)) await settle(caseId, state, generation, threadId);
  }
}

function stopRequested(state) {
  const chat = state.chat.value;
  const chatStreaming = chat != null && ["streaming", "submitted"].includes(chat.status);
  return chatStreaming || Boolean(state.snapshot.value?.activeRun);
}

async function stopChat(caseId, state, generation) {
  const thread = state.threadId.value || state.chat.value?.id || state.snapshot.value?.id;
  if (!isCurrent(state, generation) || !thread || !stopRequested(state)) return;
  state.stopping.value = true;
  try {
    await api.agentCancel(caseId, thread, session.csrfToken);
    if (isCurrent(state, generation)) {
      detachChat(state);
      const snapshot = await rebuild(caseId, state, generation, thread, true);
      // 取消 ACK 不是终态：快照仍 active 时必须接回恢复流等待收敛，
      // 否则唯一 reader 已断开，界面停留生成中
      if (isCurrent(state, generation) && snapshot?.activeRun) {
        await resume(caseId, state, generation);
      }
    }
  } finally {
    state.stopping.value = false;
  }
}

async function retryChat(caseId, state, generation, messageId) {
  const threadId = state.threadId.value;
  if (!isCurrent(state, generation) || !state.chat.value) return;
  await rebuild(caseId, state, generation, threadId);
  if (!isCurrent(state, generation) || !state.chat.value) return;
  try {
    await state.chat.value.regenerate({ messageId });
  } finally {
    if (isCurrent(state, generation)) await settle(caseId, state, generation, threadId);
  }
}

async function decideArtifact(caseId, state, generation, artifactId, decision) {
  const threadId = state.threadId.value;
  const result = await api.agentDecide(caseId, threadId, artifactId, decision, session.csrfToken);
  if (isCurrent(state, generation) && state.threadId.value === threadId) {
    await refreshSnapshot(caseId, state, generation, threadId);
  }
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
    threadId: ref(null), loading: ref(true), error: ref(""), stopping: ref(false),
    skills: ref([]), selectedSkillId: ref(CASE_EDIT_SKILL_ID), catalog: ref("loading"),
    generation: 0, catalogGeneration: 0, disposed: false,
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
    threadId: computed(() => state.threadId.value),
    status: computed(() => {
      const chatStatus = state.chat.value?.status;
      return chatStatus && chatStatus !== "ready" ? chatStatus : snapshotStatus(state.snapshot.value);
    }),
    chatError: computed(() => snapshotError(state.snapshot.value) || state.chat.value?.error?.message || ""),
    threadState: computed(() => state.snapshot.value),
    stopping: computed(() => Boolean(state.stopping.value)),
    retryableMessageId: computed(() => retryMessageId(state)),
    skillReady: computed(() => isSelectedSkillValid(state)),
  };
}

function reload(caseId, state) {
  state.generation += 1;
  return loadChat(caseId, state, state.generation);
}

function reloadCatalog(state) {
  state.catalogGeneration += 1;
  return loadCatalog(state, state.catalogGeneration);
}

function bindLifecycle(state, recover) {
  window.addEventListener("online", recover);
  onBeforeUnmount(() => {
    window.removeEventListener("online", recover);
    state.disposed = true;
    state.generation += 1;
    state.catalogGeneration += 1;
    detachChat(state);
  });
}

function exposedApi(caseId, state, at) {
  return {
    ...computedState(state), ...threadActions(actions.caseId, state),
    loading: state.loading, error: state.error, settings: state.settings,
    skills: state.skills, selectedSkillId: state.selectedSkillId,
    catalog: state.catalog, reloadCatalog: () => reloadCatalog(state),
    textParts,
    send: (text, contextParts = []) => sendChat(caseId, state, text, at(), contextParts),
    stop: () => stopChat(caseId, state, at()),
    retry: (messageId) => retryChat(caseId, state, at(), messageId),
    decide: (id, decision) => decideArtifact(caseId, state, at(), id, decision),
    reload: () => reload(caseId, state),
  };
}

export function useAgentChat(caseId) {
  const state = createState();
  const at = () => state.generation;
  const recover = () => {
    if (state.snapshot.value?.activeRun) kickResume(caseId, state, at());
  };
  bindLifecycle(state, recover);
  void reload(caseId, state);
  void reloadCatalog(state);
  return exposedApi(caseId, state, at);
}
