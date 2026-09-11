<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, provide, ref, watch } from "vue";
import { AlertTriangle, LoaderCircle, RefreshCw } from "@lucide/vue";
import { useRoute } from "vue-router";
import AssistantRail from "../components/AssistantRail.vue";
import AddSourceToCase from "../components/AddSourceToCase.vue";
import CanvasEditor from "../components/CanvasEditor.vue";
import CaseTagPicker from "../components/CaseTagPicker.vue";
import OutlinePanel from "../components/OutlinePanel.vue";
import OverwriteConfirmDialog from "../components/OverwriteConfirmDialog.vue";
import ReviewDecisionDialog from "../components/ReviewDecisionDialog.vue";
import SiteHeader from "../components/SiteHeader.vue";
import VersionTabs from "../components/VersionTabs.vue";
import WorkspaceHeader from "../components/WorkspaceHeader.vue";
import { api } from "../api.js";
import { createAutosave } from "../composables/useAutosave.js";
import { createCrashDraft } from "../composables/useCrashDraft.js";
import { CONVERSATION_SOURCES_KEY, createConversationSources } from "../composables/useConversationSources.js";
import { documentOutline, normalizeDocument } from "../lib/document.js";
import { citationSignature } from "../lib/citation.js";
import { session } from "../session.js";

const route = useRoute();
const readerMode = computed(() => route.name === "case-public");
const activeCaseId = String(route.params.id);
// 案例级「用于对话」上下文归 provider 所有：按读者版本清理，
// 切案例由 App 按 fullPath 重挂载换新实例兜底
const conversationSources = createConversationSources();
provide(CONVERSATION_SOURCES_KEY, conversationSources);
const caseRecord = ref(null);
const readerVersion = computed(() => readerMode.value ? caseRecord.value?.publishedVersionId || "" : "");
const title = ref("");
const titleInput = ref(null);
const document = ref(normalizeDocument());
const revision = ref(0);
const tagIds = ref([]);
const tagCatalog = ref([]);
const tagCatalogLoading = ref(false);
const tagCatalogError = ref("");
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
const focusedAnnotationId = ref("");
const annotationRefreshToken = ref(0);
let pendingSteps = [];
const sources = ref([]);
const canvasEditor = ref(null);
const decisionCommand = ref("");
const openVersionTabs = ref([]);
const activeTabId = ref("draft");
const overwriteTarget = ref(null);
const outlineCollapsed = ref(localStorage.getItem("canvas-outline-collapsed") === "1");

const activeVersion = computed(() => (
  openVersionTabs.value.find((tab) => tab.id === activeTabId.value) || null
));
const versionTabItems = computed(() => openVersionTabs.value.map((version) => ({
  id: version.id,
  label: `v${version.number} · ${version.title}`,
})));
const onDraftTab = computed(() => !activeVersion.value);
const activeDocument = computed(() => (
  onDraftTab.value ? document.value : activeVersion.value.document
));
const historicalVersion = computed(() => Boolean(activeVersion.value));
const assistantReadOnly = computed(() => readerMode.value || historicalVersion.value);
const outline = computed(() => documentOutline(activeDocument.value));
watch(readerVersion, () => conversationSources.clear());
const reviewMode = computed(() => route.name === "case-review");
const workflowStatus = computed(() => caseRecord.value?.workflowStatus);
const publicationStatus = computed(() => caseRecord.value?.publicationStatus);
const isOwner = computed(() => caseRecord.value?.ownerId === session.user?.id);
const historyAvailable = computed(() => Boolean(
  !readerMode.value && session.user && (isOwner.value || session.user.role === "admin"),
));
const publicCaseId = computed(() => (
  !readerMode.value && publicationStatus.value === "public"
    ? caseId() : ""
));
const versionTabsAvailable = computed(() => !readerMode.value && historyAvailable.value);
const overwriteAllowed = computed(() => isOwner.value && workflowStatus.value === "draft");
const editable = computed(() => (
  !readerMode.value && isOwner.value && workflowStatus.value === "draft" && !reviewMode.value
  && onDraftTab.value && !busyAction.value && !contentMutationBusy.value
));
const annotatable = computed(() => Boolean(
  !readerMode.value && session.user && onDraftTab.value && (
    (isOwner.value && workflowStatus.value === "draft" && !reviewMode.value)
    || (reviewMode.value && workflowStatus.value === "reviewing" && session.user.role === "admin")
  ),
));
const headerBusyAction = computed(() => busyAction.value || (contentMutationBusy.value ? "content" : ""));
const statusLabel = computed(() => {
  if (readerMode.value) return `发布版本 v${caseRecord.value?.versionNumber || 1} · 只读`;
  if (publicationStatus.value === "hidden") return "已隐藏";
  const base = ({ draft: "草稿", pending: "待审", reviewing: "审核中", published: "已发布" })[
    workflowStatus.value
  ] || "未知状态";
  if (publicationStatus.value === "public" && workflowStatus.value !== "published") {
    return `${base} · 旧版公开中`;
  }
  return base;
});
const lifecycleActions = computed(() => {
  if (readerMode.value) return [];
  const area = reviewMode.value ? "review" : "author";
  return (caseRecord.value?.availableActions || [])
    .filter((command) => LIFECYCLE_META[command]?.area === area
      || (command === "reopen" && reviewMode.value))
    .map((command) => ({
      command,
      ...LIFECYCLE_META[command],
      ...(command === "reopen" && reviewMode.value ? { label: "下线编辑" } : {}),
    }));
});
const lastReview = computed(() => (
  workflowStatus.value === "draft" ? caseRecord.value?.lastReview : null
));
const lastReviewLabel = computed(() => (
  lastReview.value?.action === "supplement" ? "要求补充" : "退回修改"
));
const LIFECYCLE_META = {
  submit: { label: "提交审核", primary: true, area: "author" },
  withdraw: { label: "撤回提交", primary: false, area: "author" },
  start: { label: "开始审核", primary: true, area: "review" },
  approve: { label: "通过发布", primary: true, area: "review" },
  reject: { label: "退回修改", primary: false, area: "review" },
  supplement: { label: "要求补充", primary: false, area: "review" },
  hide: { label: "暂时隐藏", primary: false, area: "review" },
  restore: { label: "恢复公开", primary: false, area: "review" },
  reopen: { label: "另开新稿", primary: true, area: "author" },
};
const submissionTodo = computed(() => {
  const missing = [];
  if (!title.value.trim()) missing.push("填写案例标题");
  if (!documentHasText(document.value)) missing.push("填写正文");
  tagCatalog.value
    .filter((group) => group.requiredForSubmission && group.enabled !== false)
    .filter((group) => !group.tags.some((tag) => tagIds.value.includes(tag.id)))
    .forEach((group) => missing.push(`选择${group.name}标签`));
  return missing;
});

function documentHasText(node) {
  return Boolean(node?.text?.trim() || node?.content?.some(documentHasText));
}

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
  const steps = pendingSteps.slice();
  return {
    ...contentSnapshot(),
    tagIds: tagIds.value,
    revision: revision.value,
    ...(steps.length ? { steps } : {}),
  };
}

function contentSnapshot() {
  const steps = pendingSteps.slice();
  return {
    title: title.value,
    document: document.value,
    ...(steps.length ? { steps } : {}),
  };
}

async function persist(payload) {
  const documentChanged = Boolean(payload.steps?.length);
  const saved = await api.saveCase(caseId(), payload, session.csrfToken);
  pendingSteps.splice(0, payload.steps?.length || 0);
  invalidateSelection();
  revision.value = saved.revision;
  caseRecord.value = { ...caseRecord.value, revision: saved.revision };
  crashDraft.saved(payload);
  if (documentChanged) await refreshAnnotations();
  await syncSourcesAfterSave(payload);
  return saved;
}

// 资料区编号以保存成功的正文为准；失败不刷新，也不另立第二真源。
async function syncSourcesAfterSave(payload) {
  const signature = citationSignature(payload.document);
  if (signature === sourcesSignature.value) return;
  sourcesSignature.value = signature;
  await loadSources();
}

function invalidateSelection() {
  annotationSelection.value = null;
}

function handleSaveConflict(error) {
  conflict.value = error;
  invalidateSelection();
}

function applyCase(value, invalidate = true) {
  if (invalidate) invalidateSelection();
  pendingSteps = [];
  caseRecord.value = value;
  title.value = value.title;
  document.value = normalizeDocument(value.document);
  revision.value = value.revision;
  tagIds.value = value.tagIds || [];
  conflict.value = null;
  if (editable.value) crashDraft.load(value);
  void nextTick(resizeTitle);
}

async function loadAnnotations() {
  if (!session.user || readerMode.value) {
    annotations.value = [];
    return;
  }
  try { annotations.value = await api.listAnnotations(caseId()); }
  catch { /* 保留当前批注标记，等待下一次刷新 */ }
}

async function refreshAnnotations() {
  await loadAnnotations();
  annotationRefreshToken.value += 1;
}

async function applyRevisedCase(value) {
  applyCase(value);
  await refreshAnnotations();
}

function refreshAnnotationsAfterAi() {
  void refreshAnnotations();
}

const sourcesLoading = ref(false);
const sourcesError = ref("");
const sourcesSignature = ref("");

async function loadSources() {
  sourcesLoading.value = true;
  sourcesError.value = "";
  try { sources.value = (await api.listSources(caseId(), readerVersion.value)).entries; }
  catch (error) { sources.value = []; sourcesError.value = error.message || "来源加载失败"; }
  finally { sourcesLoading.value = false; }
}

function applyAttachmentCase(value) {
  invalidateSelection();
  syncCaseRevision(value);
  void loadSources();
}

function syncCaseRevision(value) {
  caseRecord.value = value;
  revision.value = value.revision;
  conflict.value = null;
}

function recoverCrashDraft(value) {
  pendingSteps = value.steps?.slice() || [];
  title.value = value.title;
  document.value = normalizeDocument(value.document);
  autosave.markDirty();
  void nextTick(resizeTitle);
}

async function fetchCase() {
  const versionId = String(route.query?.versionId || "");
  return readerMode.value
    ? api.getPublicCase(caseId(), versionId || undefined) : api.getCase(caseId());
}

async function loadCase() {
  const initial = !caseRecord.value;
  loading.value = true;
  loadError.value = "";
  try {
    const current = await fetchCase();
    applyCase(current, !initial);
    await Promise.all([loadAnnotations(), loadSources()]);
    sourcesSignature.value = citationSignature(document.value);
  } catch (error) {
    loadError.value = error.message || "案例加载失败";
  } finally {
    loading.value = false;
  }
}

function changeTitle(event) {
  invalidateSelection();
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
  document.value = value.document;
  pendingSteps.push(...(value.steps || []));
  crashDraft.queue();
  autosave.markDirty();
}

const CITATION_NOTICES = {
  readonly: "只读工作台不能插入或修改引用",
  unpositioned: "请先在正文点击插入位置，或选中一段文字",
};

function insertSourceCitation(row) {
  const status = onDraftTab.value
    ? (canvasEditor.value?.insertCitation(row) ?? "unpositioned")
    : "readonly";
  actionNotice.value = CITATION_NOTICES[status] ?? (status === "linked"
    ? `已将选区关联引用〔${row.number}〕`
    : `已插入引用〔${row.number}〕`);
}

function changeTags(next) {
  tagIds.value = next;
  autosave.markDirty();
}

async function loadTagCatalog() {
  tagCatalogLoading.value = true;
  tagCatalogError.value = "";
  try { tagCatalog.value = await api.listTagGroups(); }
  catch { tagCatalogError.value = "标签目录加载失败"; }
  finally { tagCatalogLoading.value = false; }
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
  activeTool.value = readerMode.value && tool === "comments" ? "ai" : tool;
  drawerOpen.value = true;
}

async function prepareLifecycle(command) {
  if (command !== "submit") return true;
  if (await flushAutosave()) return true;
  actionNotice.value = "正文尚未保存，未执行提交。";
  return false;
}

async function flushAutosave() {
  await autosave.flush();
  return autosave.state.value === "saved";
}

async function prepareAnnotationMutation() {
  if (!await flushAutosave()) return false;
  await canvasEditor.value?.recaptureSelection();
  await nextTick();
  return true;
}

function openAnnotation(id) {
  selectTool("comments");
  focusedAnnotationId.value = "";
  void nextTick(() => { focusedAnnotationId.value = id; });
}

function askAnnotationAi(annotation) {
  if (!annotation || annotation.createdBy !== session.user?.id) return;
  writingContext.value = {
    annotationId: annotation.id,
    from: annotation.from,
    to: annotation.to,
    quote: annotation.quote,
    section: annotation.section,
    quoteHash: annotation.quoteHash,
    revision: revision.value,
    sameBlock: annotation.anchorState !== "changed" && annotation.anchorState !== "deleted",
  };
  selectTool("ai");
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
    if (error.status === 409) await refreshLifecycleState();
    return false;
  } finally {
    busyAction.value = "";
  }
}

async function refreshLifecycleState() {
  if (autosave.state.value !== "saved") return;
  try {
    applyCase(await api.getCase(caseId()));
  } catch { /* 保留错误提示，用户可手动重试 */ }
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
  if (!await flushAutosave()) {
    throw new Error("正文尚未保存，未执行当前操作。");
  }
  return revision.value;
}

function openVersionTab(version) {
  if (!openVersionTabs.value.some((tab) => tab.id === version.id)) {
    openVersionTabs.value = [...openVersionTabs.value, version];
  }
  activeTabId.value = version.id;
}

function closeVersionTab(id) {
  openVersionTabs.value = openVersionTabs.value.filter((tab) => tab.id !== id);
  if (activeTabId.value === id) activeTabId.value = "draft";
}

function selectTab(id) {
  activeTabId.value = id;
}

function requestOverwrite() {
  if (headerBusyAction.value || !activeVersion.value) return;
  actionNotice.value = "";
  overwriteTarget.value = activeVersion.value;
}

function cancelOverwrite() {
  overwriteTarget.value = null;
}

async function overwriteBaseline() {
  if (await flushAutosave()) return revision.value;
  actionNotice.value = "正文尚未保存，未执行覆盖。";
  return null;
}

async function overwriteSucceeded(result) {
  applyCase(result.case);
  activeTabId.value = "draft";
  overwriteTarget.value = null;
  crashDraft.load(result.case);
  await refreshAnnotations();
}

function overwriteFailed(error) {
  overwriteTarget.value = null;
  actionNotice.value = error.message || "覆盖失败";
  if (error.status === 409) void refreshLifecycleState();
}

async function performOverwrite() {
  const target = overwriteTarget.value;
  if (!target || headerBusyAction.value) return;
  busyAction.value = "overwrite";
  try {
    if (await overwriteBaseline() === null) return;
    const body = lifecycleBody("overwrite", { targetId: target.id });
    await overwriteSucceeded(await api.lifecycleCase(caseId(), body, session.csrfToken));
  } catch (error) {
    overwriteFailed(error);
  } finally {
    busyAction.value = "";
  }
}

function startDownload() {
  const link = window.document.createElement("a");
  const area = readerMode.value ? "/public" : "";
  const version = readerMode.value && readerVersion.value
    ? `?versionId=${encodeURIComponent(readerVersion.value)}` : "";
  link.href = `/api/cases/${encodeURIComponent(caseId())}${area}/export.docx${version}`;
  link.click();
}

async function exportCase() {
  if (readerMode.value) { startDownload(); return; }
  actionNotice.value = "";
  if (!await flushAutosave()) {
    actionNotice.value = "正文尚未保存，未生成导出文件。";
    return;
  }
  startDownload();
}

watch(autosave.revision, (value) => {
  if (value != null) revision.value = value;
});
watch(readerMode, (value) => {
  if (value && activeTool.value === "comments") activeTool.value = "ai";
});
onMounted(() => {
  loadCase();
  if (!readerMode.value) loadTagCatalog();
});
onBeforeUnmount(() => {
  if (!readerMode.value) crashDraft.flush();
  crashDraft.destroy();
  if (!readerMode.value) void autosave.flush();
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
        :read-only="readerMode"
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
      <OverwriteConfirmDialog
        :open="Boolean(overwriteTarget)"
        :version-label="overwriteTarget ? `v${overwriteTarget.number} · ${overwriteTarget.title}` : ''"
        :busy="busyAction === 'overwrite'"
        :error="overwriteTarget && busyAction === 'overwrite' ? actionNotice : ''"
        @cancel="cancelOverwrite"
        @confirm="performOverwrite"
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
          <AddSourceToCase
            v-if="readerMode && session.user && readerVersion"
            :source-case-id="caseId()"
            :version-id="readerVersion"
            :source-title="title"
          />
          <VersionTabs
            v-else-if="versionTabsAvailable"
            :tabs="versionTabItems"
            :active="activeTabId"
            :disabled="Boolean(headerBusyAction)"
            :overwritable="overwriteAllowed"
            @select="selectTab"
            @close="closeVersionTab"
            @overwrite="requestOverwrite"
          />
          <template v-if="onDraftTab">
            <div v-if="editable && submissionTodo.length" class="submission-todo" role="status">
              <b>投稿待办</b><ul><li v-for="item in submissionTodo" :key="item">{{ item }}</li></ul>
            </div>
            <div v-if="lastReview" class="conflict-banner review-return-banner" role="status">
              <AlertTriangle :size="17" aria-hidden="true" />
              <span>
                {{ lastReviewLabel }}（v{{ lastReview.versionNumber }}）：{{ lastReview.reasonType }}<template v-if="lastReview.summary"> — {{ lastReview.summary }}</template>
              </span>
            </div>
            <article class="document-paper">
              <textarea ref="titleInput" class="document-title" :value="title" :readonly="!editable" rows="1" aria-label="案例标题" @input="changeTitle" />
              <div class="document-byline"><span>{{ caseRecord.course || "课程未设置" }}</span><span>{{ caseRecord.typeName || "教学案例" }}</span></div>
              <CaseTagPicker
                :tag-ids="tagIds"
                :groups="tagCatalog"
                :editable="editable"
                :loading="tagCatalogLoading"
                :error="tagCatalogError"
                @update:tag-ids="changeTags"
                @retry="loadTagCatalog"
              />
              <CanvasEditor
                ref="canvasEditor"
                :document="document"
                :revision="revision"
                :editable="editable"
                :annotatable="annotatable"
                :annotations="annotations"
                :sources="sources"
                @change="changeDocument"
                @selection="annotationSelection = $event"
                @writing-context="writingContext = $event"
                @annotate="selectTool('comments')"
                @annotation-click="openAnnotation"
              />
            </article>
          </template>
          <article v-else-if="activeVersion" class="document-paper version-paper">
            <header class="version-paper-head">
              <h2>{{ activeVersion.title }}</h2>
              <p>提交版本 v{{ activeVersion.number }} · 只读 · 可复制，覆盖后可在当前教师稿继续编辑</p>
            </header>
            <CanvasEditor
              :key="activeVersion.id"
              :document="activeVersion.document"
              :editable="false"
              :annotatable="false"
              :annotations="[]"
              :sources="[]"
            />
          </article>
        </main>
        <AssistantRail
          :active="activeTool"
          :review="reviewMode"
          :version-id="readerVersion"
          :sources="sources"
          :sources-loading="sourcesLoading"
          :sources-error="sourcesError"
          :open="drawerOpen"
          :case-record="caseRecord"
          :user="session.user ? { ...session.user, csrfToken: session.csrfToken } : null"
          :historical="historicalVersion"
          :read-only="assistantReadOnly"
          :editable="editable"
          :selection="annotationSelection"
          :writing-context="writingContext"
          :before-attachment-mutation="prepareContentMutation"
          :before-annotation-mutation="prepareAnnotationMutation"
          :focus-annotation-id="focusedAnnotationId"
          :annotation-refresh-token="annotationRefreshToken"
          @select="selectTool"
          @toggle="drawerOpen = !drawerOpen"
          @case-refreshed="applyAttachmentCase"
          @case-restored="applyCase"
          @case-revised="applyRevisedCase"
          @mutation-state="contentMutationBusy = $event"
          @annotations="annotations = $event"
          @annotations-refresh="refreshAnnotationsAfterAi"
          @ask-ai="askAnnotationAi"
          @sources-retry="loadSources"
          @clear-writing-context="writingContext = null"
          @insert-citation="insertSourceCitation"
          @open-version="openVersionTab"
        />
      </div>
    </template>
  </div>
</template>
