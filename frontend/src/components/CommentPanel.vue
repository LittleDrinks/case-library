<script setup>
import { computed, nextTick, reactive, ref, watch } from "vue";
import {
  Check, CornerUpLeft, MessageSquareText, Pencil, RotateCcw, Sparkles, Trash2, X,
} from "@lucide/vue";
import { api } from "../api.js";

const props = defineProps({
  caseRecord: { type: Object, required: true },
  user: { type: Object, default: null },
  selection: { type: Object, default: null },
  focusAnnotationId: { type: String, default: "" },
  annotationRefreshToken: { type: Number, default: 0 },
  beforeAnnotationMutation: { type: Function, default: async () => true },
});
const emit = defineEmits(["annotations", "ask-ai", "case-revised"]);
const annotations = ref([]);
const content = ref("");
const error = ref("");
const loading = ref(true);
const saving = ref(false);
const editingId = ref("");
const editingContent = ref("");
const replies = reactive({});
const cardRefs = new Map();
let loadGeneration = 0;

const canCompose = computed(() => Boolean(
  props.user && (
    (props.user.id === props.caseRecord.ownerId && props.caseRecord.workflowStatus === "draft")
    || (props.user.role === "admin" && props.caseRecord.workflowStatus === "reviewing")
  ),
));
const canCreate = computed(() => Boolean(
  canCompose.value && props.selection?.quote && props.selection?.section
  && props.selection?.quoteHash && props.selection?.from < props.selection?.to
  && props.selection?.revision === props.caseRecord.revision,
));
const creationSource = computed(() => props.user?.role === "admin" ? "admin" : "manual");

function announce() {
  emit("annotations", annotations.value);
}

function replaceAnnotation(updated) {
  const index = annotations.value.findIndex((row) => row.id === updated.id);
  if (index >= 0) annotations.value[index] = updated;
  announce();
}

async function loadAnnotations() {
  const generation = ++loadGeneration;
  loading.value = true;
  error.value = "";
  try {
    const next = props.user ? await api.listAnnotations(props.caseRecord.id) : [];
    if (generation !== loadGeneration) return;
    annotations.value = next;
    announce();
    void focusAnnotation(props.focusAnnotationId);
  } catch (caught) {
    if (generation === loadGeneration) error.value = caught.message || "批注加载失败";
  } finally {
    if (generation === loadGeneration) loading.value = false;
  }
}

function createPayload() {
  const fields = ["from", "to", "quote", "quoteHash", "section", "revision"];
  return {
    ...Object.fromEntries(fields.map((field) => [field, props.selection[field]])),
    content: content.value.trim(),
    source: creationSource.value,
  };
}

function showCreated(annotation) {
  annotations.value = [...annotations.value.filter((row) => row.id !== annotation.id), annotation];
  content.value = "";
  announce();
}

async function addAnnotation() {
  if (!canCreate.value || !content.value.trim() || saving.value) return;
  const caseId = props.caseRecord.id;
  saving.value = true;
  error.value = "";
  try {
    if (await props.beforeAnnotationMutation() === false) return;
    if (!canCreate.value) return;
    const payload = createPayload();
    const created = await api.createAnnotation(caseId, payload, props.user.csrfToken);
    if (caseId !== props.caseRecord.id) return;
    showCreated(created);
    await loadAnnotations();
  } catch (caught) {
    if (caseId === props.caseRecord.id) error.value = caught.message || "批注添加失败";
  } finally {
    saving.value = false;
  }
}

function setCardRef(id, element) {
  if (element) cardRefs.set(id, element);
  else cardRefs.delete(id);
}

async function focusAnnotation(id) {
  if (!id) return;
  await nextTick();
  cardRefs.get(id)?.scrollIntoView?.({ behavior: "smooth", block: "nearest" });
}

function canEdit(annotation) {
  return annotation.createdBy === props.user?.id && annotation.status === "pending";
}

function canDiscuss(annotation) {
  return annotation.createdBy === props.user?.id
    && annotation.status === "pending"
    && (annotation.anchorState || "active") === "active";
}

function latestPendingRevision(annotation) {
  return [...(annotation.revisions || [])].reverse()
    .find((revision) => revision.status === "pending");
}

function canMerge(annotation) {
  return Boolean(canDiscuss(annotation) && latestPendingRevision(annotation));
}

function revisionStatus(status) {
  return ({
    pending: "待决定", accepted: "已合并", rejected: "已拒绝", expired: "已失效",
  })[status] || status;
}

function askAi(annotation) {
  if (canDiscuss(annotation)) emit("ask-ai", annotation);
}

function beginEdit(annotation) {
  editingId.value = annotation.id;
  editingContent.value = annotation.content;
  error.value = "";
}

function cancelEdit() {
  editingId.value = "";
  editingContent.value = "";
}

async function saveEdit(annotation) {
  const value = editingContent.value.trim();
  if (!value || saving.value) return;
  saving.value = true;
  error.value = "";
  try {
    replaceAnnotation(await api.updateAnnotation(
      props.caseRecord.id, annotation.id, { content: value }, props.user.csrfToken,
    ));
    cancelEdit();
  } catch (caught) {
    error.value = caught.message || "批注保存失败";
  } finally {
    saving.value = false;
  }
}

async function removeAnnotation(annotation) {
  if (!canEdit(annotation) || saving.value) return;
  saving.value = true;
  error.value = "";
  try {
    await api.deleteAnnotation(props.caseRecord.id, annotation.id, props.user.csrfToken);
    annotations.value = annotations.value.filter((row) => row.id !== annotation.id);
    announce();
  } catch (caught) {
    error.value = caught.message || "批注删除失败";
  } finally {
    saving.value = false;
  }
}

async function reply(annotation) {
  const value = replies[annotation.id]?.trim();
  if (!value || saving.value) return;
  saving.value = true;
  error.value = "";
  try {
    replaceAnnotation(await api.replyAnnotation(
      props.caseRecord.id, annotation.id, { content: value }, props.user.csrfToken,
    ));
    replies[annotation.id] = "";
  } catch (caught) {
    error.value = caught.message || "回复失败";
  } finally {
    saving.value = false;
  }
}

async function setStatus(annotation, status) {
  if (saving.value) return;
  saving.value = true;
  error.value = "";
  try {
    replaceAnnotation(await api.setAnnotationStatus(
      props.caseRecord.id, annotation.id, status, props.user.csrfToken,
    ));
  } catch (caught) {
    error.value = caught.message || "状态更新失败";
  } finally {
    saving.value = false;
  }
}

async function merge(annotation) {
  if (!canMerge(annotation) || saving.value) return;
  saving.value = true;
  error.value = "";
  try {
    const result = await api.mergeAnnotation(
      props.caseRecord.id, annotation.id, props.user.csrfToken,
    );
    replaceAnnotation(result.annotation);
    emit("case-revised", result.case);
  } catch (caught) {
    error.value = caught.message || "合并修订失败";
  } finally {
    saving.value = false;
  }
}

watch(() => props.caseRecord.id, loadAnnotations, { immediate: true });
watch(() => props.annotationRefreshToken, loadAnnotations);
watch(() => props.focusAnnotationId, (id) => { void focusAnnotation(id); });
</script>

<template>
  <section class="assistant-panel comment-panel">
    <div class="panel-head"><b>批注</b><span>{{ annotations.length }}</span></div>
    <div class="panel-scroll">
      <div v-if="loading" class="panel-empty">正在加载批注</div>
      <div v-else-if="error && !annotations.length" class="attachment-error" role="alert">{{ error }}</div>
      <div v-else-if="!annotations.length" class="panel-empty">
        <MessageSquareText :size="24" /><span>暂无批注</span>
      </div>
      <ol v-else class="comment-list">
        <li
          v-for="annotation in annotations"
          :key="annotation.id"
          :ref="(element) => setCardRef(annotation.id, element)"
          class="comment-card"
          :data-annotation-id="annotation.id"
          tabindex="-1"
        >
          <header>
            <span>{{ annotation.section }}</span>
            <b :class="annotation.status">{{ annotation.status === "resolved" ? "已解决" : "待处理" }}</b>
          </header>
          <blockquote>{{ annotation.quote }}</blockquote>
          <p v-if="annotation.anchorState === 'deleted'" class="comment-anchor-state">原文已删除</p>
          <p v-else-if="annotation.anchorState === 'changed'" class="comment-anchor-state">原文已变动，旧修订不可合并</p>
          <textarea
            v-if="editingId === annotation.id"
            v-model="editingContent"
            class="comment-edit-input"
            aria-label="编辑批注"
            :disabled="saving"
          />
          <p v-else>{{ annotation.content }}</p>
          <div v-if="annotation.revisions?.length" class="comment-revisions">
            <b>AI 修订历史</b>
            <ol>
              <li v-for="(revision, index) in annotation.revisions" :key="revision.id">
                <header>
                  <span>第 {{ index + 1 }} 轮 · {{ revisionStatus(revision.status) }}</span>
                </header>
                <p>替换为：{{ revision.replacement }}</p>
                <small v-if="revision.reason">理由：{{ revision.reason }}</small>
              </li>
            </ol>
          </div>
          <div v-if="editingId === annotation.id" class="comment-owner-actions">
            <button type="button" :disabled="saving || !editingContent.trim()" @click="saveEdit(annotation)"><Check :size="14" />保存批注</button>
            <button type="button" :disabled="saving" @click="cancelEdit"><X :size="14" />取消</button>
          </div>
          <div v-else-if="canEdit(annotation)" class="comment-owner-actions">
            <button type="button" aria-label="编辑批注" :disabled="saving" @click="beginEdit(annotation)"><Pencil :size="14" />编辑</button>
            <button type="button" aria-label="删除批注" :disabled="saving" @click="removeAnnotation(annotation)"><Trash2 :size="14" />删除</button>
          </div>
          <ul v-if="annotation.replies.length" class="comment-replies">
            <li v-for="item in annotation.replies" :key="item.id">
              <CornerUpLeft :size="13" /><span>{{ item.content }}</span>
            </li>
          </ul>
          <div class="comment-thread-actions">
            <input v-model="replies[annotation.id]" aria-label="回复批注" placeholder="回复" />
            <button type="button" :disabled="saving || !replies[annotation.id]?.trim()" @click="reply(annotation)">回复</button>
          </div>
          <button
            v-if="annotation.status === 'pending' && user?.id === caseRecord.ownerId"
            class="comment-status-action"
            type="button"
            :disabled="saving"
            @click="setStatus(annotation, 'resolved')"
          ><Check :size="14" />标记解决</button>
          <button
            v-if="canDiscuss(annotation)"
            class="comment-status-action"
            type="button"
            :disabled="saving"
            @click="askAi(annotation)"
          ><Sparkles :size="14" />让 AI 修订</button>
          <button
            v-if="canMerge(annotation)"
            class="comment-status-action comment-merge-action"
            type="button"
            :disabled="saving"
            @click="merge(annotation)"
          ><Check :size="14" />合并并关闭</button>
          <button
            v-else-if="annotation.status === 'resolved' && user?.role === 'admin'"
            class="comment-status-action"
            type="button"
            :disabled="saving"
            @click="setStatus(annotation, 'pending')"
          ><RotateCcw :size="14" />重新打开</button>
        </li>
      </ol>
    </div>
    <div v-if="canCompose" class="comment-composer">
      <blockquote v-if="selection?.quote">{{ selection.quote }}</blockquote>
      <p v-if="!canCreate" class="comment-selection-hint" role="status">请先在正文中选择一段文字</p>
      <textarea v-model="content" aria-label="批注内容" :disabled="!canCreate || saving" placeholder="选择正文后添加批注" />
      <button type="button" :disabled="!canCreate || !content.trim() || saving" @click="addAnnotation">添加批注</button>
    </div>
    <div v-if="error && annotations.length" class="comment-inline-error" role="alert">{{ error }}</div>
  </section>
</template>
