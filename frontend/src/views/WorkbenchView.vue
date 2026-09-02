<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, toRaw, watch } from "vue";
import { AlertTriangle, LoaderCircle, RefreshCw } from "@lucide/vue";
import { useRoute } from "vue-router";
import AssistantRail from "../components/AssistantRail.vue";
import CanvasEditor from "../components/CanvasEditor.vue";
import OutlinePanel from "../components/OutlinePanel.vue";
import ReviewDecisionDialog from "../components/ReviewDecisionDialog.vue";
import SiteHeader from "../components/SiteHeader.vue";
import WorkspaceHeader from "../components/WorkspaceHeader.vue";
import { api } from "../api.js";
import { createAutosave } from "../composables/useAutosave.js";
import { createCrashDraft } from "../composables/useCrashDraft.js";
import { documentOutline, normalizeDocument } from "../lib/document.js";
import { session } from "../session.js";

const route = useRoute();
const activeCaseId = String(route.params.id);
const caseRecord = ref(null);
const title = ref("");
const titleInput = ref(null);
const canvasEditor = ref(null);
const document = ref(normalizeDocument());
const revision = ref(0);
const loading = ref(true);
const loadError = ref("");
const conflict = ref(null);
const activeTool = ref("ai");
const drawerOpen = ref(false);
const actionNotice = ref("");
const busyAction = ref("");
const contentMutationBusy = ref(false);
const annotationSelection = ref(null);
const writingContext = ref(null);
const annotations = ref([]);
const candidatePreviews = ref([]);
const candidateInvalidation = ref(0);
const candidateBatchSnapshotId = ref("");
const candidateBatchLastRevision = ref(0);
const applyingCandidate = ref(false);
const candidateRecoveryBlocked = ref(false);
const decisionCommand = ref("");
const outlineCollapsed = ref(localStorage.getItem("canvas-outline-collapsed") === "1");

const outline = computed(() => documentOutline(document.value));
const reviewMode = computed(() => route.name === "case-review");
const workflowStatus = computed(() => caseRecord.value?.workflowStatus);
const publicationStatus = computed(() => caseRecord.value?.publicationStatus);
const isOwner = computed(() => caseRecord.value?.ownerId === session.user?.id);
const historyAvailable = computed(() => Boolean(
  session.user && (isOwner.value || session.user.role === "admin"),
));
const publicCaseId = computed(() => (
  workflowStatus.value === "published" && publicationStatus.value === "public"
    ? caseId() : ""
));
const editable = computed(() => (
  isOwner.value && workflowStatus.value === "draft" && !reviewMode.value
  && !busyAction.value && !contentMutationBusy.value
));
const annotatable = computed(() => Boolean(
  session.user && (
    (isOwner.value && workflowStatus.value === "draft" && !reviewMode.value)
    || (reviewMode.value && workflowStatus.value === "reviewing" && session.user.role === "admin")
  ),
));
const headerBusyAction = computed(() => busyAction.value || (contentMutationBusy.value ? "content" : ""));
const statusLabel = computed(() => {
  if (publicationStatus.value === "hidden") return "已隐藏";
  return ({ draft: "草稿", pending: "待审", reviewing: "审核中", published: "已发布" })[
    workflowStatus.value
  ] || "草稿";
});
const lifecycleActions = computed(() => availableActions());

const autosave = createAutosave({
  save: persist,
  getSnapshot: snapshot,
  onConflict: handleSaveConflict,
});
const crashDraft = createCrashDraft({
  userId: session.user?.id || "anonymous",
  caseId: caseId(),
  getRevision: () => revision.value,
  getSnapshot: contentSnapshot,
  onRecover: recoverCrashDraft,
});

function caseId() {
  return activeCaseId;
}

function snapshot() {
  return { ...contentSnapshot(), revision: revision.value };
}

function contentSnapshot() {
  return { title: title.value, document: document.value };
}

function cloneContentSnapshot() {
  return { title: title.value, document: structuredClone(toRaw(document.value)) };
}

async function persist(payload) {
  const saved = await api.saveCase(caseId(), payload, session.csrfToken);
  invalidateSelection();
  revision.value = saved.revision;
  caseRecord.value = { ...caseRecord.value, revision: saved.revision };
  crashDraft.saved(payload);
  return saved;
}

function expireCandidates() {
  invalidateSelection();
  candidateInvalidation.value += 1;
  candidateBatchSnapshotId.value = "";
  candidateBatchLastRevision.value = 0;
}

function invalidateSelection() {
  annotationSelection.value = null;
}

function handleSaveConflict(error) {
  conflict.value = error;
  expireCandidates();
}

function applyCase(value, invalidate = true) {
  if (invalidate) expireCandidates();
  caseRecord.value = value;
  title.value = value.title;
  document.value = normalizeDocument(value.document);
  revision.value = value.revision;
  conflict.value = null;
  if (editable.value) crashDraft.load(value);
  void nextTick(resizeTitle);
}

async function loadAnnotations() {
  if (!session.user) {
    annotations.value = [];
    return;
  }
  try { annotations.value = await api.listAnnotations(caseId()); }
  catch { annotations.value = []; }
}

function applyAttachmentCase(value) {
  expireCandidates();
  syncCaseRevision(value);
}

function syncCaseRevision(value) {
  caseRecord.value = value;
  revision.value = value.revision;
  conflict.value = null;
}

function recoverCrashDraft(value) {
  title.value = value.title;
  document.value = normalizeDocument(value.document);
  autosave.markDirty();
  void nextTick(resizeTitle);
}

async function loadCase() {
  const initial = !caseRecord.value;
  loading.value = true;
  loadError.value = "";
  try {
    const current = await api.getCase(caseId());
    if (candidateRecoveryBlocked.value) {
      candidateRecoveryBlocked.value = false;
      contentMutationBusy.value = false;
      autosave.reconcile(current.revision);
    }
    applyCase(current, !initial);
    await loadAnnotations();
  } catch (error) {
    loadError.value = error.message || "案例加载失败";
  } finally {
    loading.value = false;
  }
}

function changeTitle(event) {
  expireCandidates();
  title.value = event.target.value;
  resizeTitle();
  crashDraft.queue();
  autosave.markDirty();
}

function resizeTitle() {
  if (!titleInput.value) return;
  titleInput.value.style.height = "auto";
  titleInput.value.style.height = `${titleInput.value.scrollHeight}px`;
}

function changeDocument(value) {
  invalidateSelection();
  if (!applyingCandidate.value) expireCandidates();
  document.value = value;
  crashDraft.queue();
  autosave.markDirty();
}

function toggleOutline() {
  outlineCollapsed.value = !outlineCollapsed.value;
  localStorage.setItem("canvas-outline-collapsed", outlineCollapsed.value ? "1" : "0");
}

function locateHeading(order) {
  window.document.querySelectorAll(".canvas-editor h1, .canvas-editor h2")[order]
    ?.scrollIntoView({ behavior: "smooth", block: "center" });
}

function selectTool(tool) {
  activeTool.value = tool;
  drawerOpen.value = true;
}

function reviewActions() {
  if (workflowStatus.value === "pending") {
    return [{ command: "start", label: "开始审核", primary: true }];
  }
  if (workflowStatus.value === "reviewing") {
    return [
      { command: "reject", label: "退回修改", primary: false },
      { command: "supplement", label: "要求补充", primary: false },
      { command: "approve", label: "通过发布", primary: true },
    ];
  }
  return null;
}

function publicationActions() {
  if (!reviewMode.value || workflowStatus.value !== "published") return null;
  if (publicationStatus.value === "public") {
    return [{ command: "hide", label: "暂时隐藏", primary: false }];
  }
  return [
    { command: "restore", label: "恢复公开", primary: false },
    { command: "reopen", label: "下线编辑", primary: true },
  ];
}

function availableActions() {
  const review = reviewMode.value && reviewActions();
  if (review) return review;
  const publication = publicationActions();
  if (publication) return publication;
  if (isOwner.value && workflowStatus.value === "draft") {
    return [{ command: "submit", label: "提交审核", primary: true }];
  }
  if (isOwner.value && workflowStatus.value === "pending") {
    return [{ command: "withdraw", label: "撤回提交", primary: false }];
  }
  return [];
}

async function prepareLifecycle(command) {
  if (command !== "submit") return true;
  await autosave.flush();
  if (autosave.state.value === "saved") return true;
  actionNotice.value = "正文尚未保存，未执行提交。";
  return false;
}

function requestLifecycle(command) {
  if (headerBusyAction.value) return;
  if (!["reject", "supplement"].includes(command)) {
    void performLifecycle(command);
    return;
  }
  actionNotice.value = "";
  decisionCommand.value = command;
}

function lifecycleBody(command, details) {
  return {
    command, revision: revision.value, ...details,
    submittedVersionId: caseRecord.value.submittedVersionId || undefined,
  };
}

async function performLifecycle(command, details = {}) {
  if (headerBusyAction.value) return false;
  actionNotice.value = "";
  busyAction.value = command;
  try {
    if (!await prepareLifecycle(command)) return false;
    const body = lifecycleBody(command, details);
    const result = await api.lifecycleCase(caseId(), body, session.csrfToken);
    applyCase(result.case);
    return true;
  } catch (error) {
    actionNotice.value = error.message || "操作失败";
    return false;
  } finally {
    busyAction.value = "";
  }
}

async function confirmDecision(details) {
  const command = decisionCommand.value;
  if (await performLifecycle(command, details)) decisionCommand.value = "";
}

function cancelDecision() {
  actionNotice.value = "";
  decisionCommand.value = "";
}

async function prepareContentMutation() {
  await autosave.flush();
  if (autosave.state.value !== "saved") {
    throw new Error("正文尚未保存，未执行当前操作。");
  }
  return revision.value;
}

async function createCandidateSnapshot() {
  const current = await prepareContentMutation();
  const result = await api.lifecycleCase(caseId(), {
    command: "snapshot", revision: current,
  }, session.csrfToken);
  syncCaseRevision(result.case);
  return result.snapshot.id;
}

function restoreCandidateBackup(backup) {
  title.value = backup.title;
  document.value = normalizeDocument(backup.document);
  crashDraft.queue();
  crashDraft.flush();
}

function candidateMatches(caseValue, applied) {
  return caseValue.title === applied.title
    && JSON.stringify(caseValue.document) === JSON.stringify(applied.document);
}

function reconcileCandidateSave(caseValue) {
  syncCaseRevision(caseValue);
  autosave.reconcile(caseValue.revision);
}

async function recoverCandidateSave(backup, applied) {
  restoreCandidateBackup(backup);
  const current = await api.getCase(caseId());
  reconcileCandidateSave(current);
  if (candidateMatches(current, applied)) {
    document.value = normalizeDocument(current.document);
    crashDraft.saved(applied);
    return;
  }
  if (!candidateMatches(current, backup)) {
    candidateRecoveryBlocked.value = true;
    throw new Error("案例已在其他页面更新，请重新载入后再生成修订。");
  }
  crashDraft.saved(backup);
  crashDraft.flush();
  throw new Error("修订保存失败，正文已恢复。");
}

async function coordinateCandidateRecovery(backup, applied) {
  try {
    await recoverCandidateSave(backup, applied);
  } catch (error) {
    if (candidateRecoveryBlocked.value || autosave.state.value === "error") {
      candidateRecoveryBlocked.value = true;
      conflict.value = error;
    }
    throw error;
  }
}

async function saveCandidateChange(candidate) {
  const backup = cloneContentSnapshot();
  applyingCandidate.value = true;
  try {
    changeDocument(canvasEditor.value.applyCandidate(candidate));
    const applied = cloneContentSnapshot();
    await autosave.flush();
    if (autosave.state.value === "saved") return;
    await coordinateCandidateRecovery(backup, applied);
  } catch (error) {
    restoreCandidateBackup(backup);
    throw error;
  } finally { applyingCandidate.value = false; }
}

async function applyWritingCandidate(candidate) {
  if (contentMutationBusy.value) throw new Error("正在处理其他正文操作。");
  contentMutationBusy.value = true;
  try {
    const snapshotId = candidateBatchSnapshotId.value || await createCandidateSnapshot();
    candidateBatchSnapshotId.value = snapshotId;
    await saveCandidateChange(candidate);
    candidateBatchLastRevision.value = revision.value;
    return { snapshotId, acceptedRevision: revision.value };
  } finally {
    if (!candidateRecoveryBlocked.value) contentMutationBusy.value = false;
  }
}

function assertCandidateBatch(snapshotId) {
  const current = revision.value;
  if (snapshotId !== candidateBatchSnapshotId.value
    || current !== candidateBatchLastRevision.value) {
    throw new Error("本批修订后正文或资料已变化，不能再回滚。");
  }
}

async function rollbackCandidateBatch(snapshotId) {
  if (!window.confirm("回滚本批 AI 修订？当前内容会自动保存为回滚前快照。")) return false;
  assertCandidateBatch(snapshotId);
  contentMutationBusy.value = true;
  try {
    const current = await prepareContentMutation();
    const result = await api.lifecycleCase(caseId(), {
      command: "rollback", revision: current, targetId: snapshotId,
    }, session.csrfToken);
    applyCase(result.case);
    return true;
  } finally { contentMutationBusy.value = false; }
}

function startDownload() {
  const link = window.document.createElement("a");
  link.href = `/api/cases/${encodeURIComponent(caseId())}/export.docx`;
  link.click();
}

async function exportCase() {
  actionNotice.value = "";
  await autosave.flush();
  if (autosave.state.value !== "saved") {
    actionNotice.value = "正文尚未保存，未生成导出文件。";
    return;
  }
  startDownload();
}

watch(autosave.revision, (value) => {
  if (value != null) revision.value = value;
});
onMounted(loadCase);
onBeforeUnmount(() => {
  crashDraft.flush();
  crashDraft.destroy();
  void autosave.flush();
  autosave.destroy();
});
</script>

<template>
  <div class="workbench-page">
    <SiteHeader />
    <div v-if="loading" class="page-state"><LoaderCircle class="spin" :size="22" /><span>正在加载案例</span></div>
    <div v-else-if="loadError" class="page-state error-state"><AlertTriangle :size="22" /><span>{{ loadError }}</span><button type="button" @click="loadCase"><RefreshCw :size="15" />重试</button></div>
    <template v-else>
      <WorkspaceHeader
        :title="title"
        :status="statusLabel"
        :save-state="autosave.state.value"
        :editable="editable"
        :review-mode="reviewMode"
        :actions="lifecycleActions"
        :busy-action="headerBusyAction"
        :history-available="historyAvailable"
        :public-case-id="publicCaseId"
        @tool="selectTool"
        @export="exportCase"
        @lifecycle="requestLifecycle"
      />
      <ReviewDecisionDialog
        :command="decisionCommand"
        :busy="busyAction === decisionCommand"
        :error="decisionCommand ? actionNotice : ''"
        @cancel="cancelDecision"
        @confirm="confirmDecision"
      />
      <div v-if="conflict" class="conflict-banner" role="alert">
        <AlertTriangle :size="17" aria-hidden="true" />
        <span>案例已在其他页面更新，本页内容尚未保存。</span>
        <button type="button" @click="loadCase">重新载入</button>
      </div>
      <div v-else-if="actionNotice" class="conflict-banner" role="alert"><AlertTriangle :size="17" />{{ actionNotice }}</div>
      <div v-else-if="autosave.state.value === 'error'" class="conflict-banner" role="alert">
        <AlertTriangle :size="17" />自动保存失败，正在重试。
      </div>
      <div class="canvas-workspace" :class="{ 'outline-collapsed': outlineCollapsed }">
        <OutlinePanel :items="outline" :collapsed="outlineCollapsed" @collapse="toggleOutline" @locate="locateHeading" />
        <main id="main-content" class="canvas-column">
          <article class="document-paper">
            <textarea ref="titleInput" class="document-title" :value="title" :readonly="!editable" rows="1" aria-label="案例标题" @input="changeTitle" />
            <div class="document-byline"><span>{{ caseRecord.course || "课程未设置" }}</span><span>{{ caseRecord.typeName || "教学案例" }}</span></div>
            <CanvasEditor
              ref="canvasEditor"
              :document="document"
              :revision="revision"
              :editable="editable"
              :annotatable="annotatable"
              :candidate-previews="candidatePreviews"
              :annotations="annotations"
              @change="changeDocument"
              @selection="annotationSelection = $event"
              @writing-context="writingContext = $event"
              @annotate="selectTool('comments')"
            />
          </article>
        </main>
        <AssistantRail
          :active="activeTool"
          :open="drawerOpen"
          :case-record="caseRecord"
          :case-title="title"
          :case-document="document"
          :user="session.user ? { ...session.user, csrfToken: session.csrfToken } : null"
          :editable="editable"
          :selection="annotationSelection"
          :writing-context="writingContext"
          :apply-candidate="applyWritingCandidate"
          :rollback-candidate-batch="rollbackCandidateBatch"
          :candidate-invalidation="candidateInvalidation"
          :before-attachment-mutation="prepareContentMutation"
          :before-version-mutation="prepareContentMutation"
          @select="selectTool"
          @toggle="drawerOpen = !drawerOpen"
          @case-refreshed="applyAttachmentCase"
          @case-restored="applyCase"
          @mutation-state="contentMutationBusy = $event"
          @candidate-previews="candidatePreviews = $event"
          @annotations="annotations = $event"
        />
      </div>
    </template>
  </div>
</template>
