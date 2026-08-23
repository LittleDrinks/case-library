<script setup>
import { computed, reactive, ref, watch } from "vue";
import { Check, CornerUpLeft, MessageSquareText, RotateCcw } from "@lucide/vue";
import { api } from "../api.js";

const props = defineProps({
  caseRecord: { type: Object, required: true },
  user: { type: Object, default: null },
  selection: { type: Object, default: null },
});
const annotations = ref([]);
const content = ref("");
const error = ref("");
const loading = ref(true);
const saving = ref(false);
const replies = reactive({});
const canCreate = computed(() => Boolean(
  props.user?.role === "admin" && props.caseRecord.workflowStatus === "reviewing"
  && props.selection?.quote && props.selection?.section,
));

function replaceAnnotation(updated) {
  const index = annotations.value.findIndex((row) => row.id === updated.id);
  if (index >= 0) annotations.value[index] = updated;
}

async function loadAnnotations() {
  loading.value = true;
  error.value = "";
  try {
    annotations.value = props.user ? await api.listAnnotations(props.caseRecord.id) : [];
  } catch (caught) {
    error.value = caught.message || "批注加载失败";
  } finally {
    loading.value = false;
  }
}

async function addAnnotation() {
  if (!canCreate.value || !content.value.trim() || saving.value) return;
  saving.value = true;
  error.value = "";
  try {
    const created = await api.createAnnotation(props.caseRecord.id, {
      ...props.selection, content: content.value.trim(), source: "admin",
    }, props.user.csrfToken);
    annotations.value.push(created);
    content.value = "";
  } catch (caught) {
    error.value = caught.message || "批注添加失败";
  } finally {
    saving.value = false;
  }
}

async function reply(annotation) {
  const value = replies[annotation.id]?.trim();
  if (!value || saving.value) return;
  saving.value = true;
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

watch(() => props.caseRecord.id, loadAnnotations, { immediate: true });
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
        <li v-for="annotation in annotations" :key="annotation.id" class="comment-card">
          <header>
            <span>{{ annotation.section }}</span>
            <b :class="annotation.status">{{ annotation.status === "resolved" ? "已解决" : "待处理" }}</b>
          </header>
          <blockquote>{{ annotation.quote }}</blockquote>
          <p>{{ annotation.content }}</p>
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
            v-else-if="annotation.status === 'resolved' && user?.role === 'admin'"
            class="comment-status-action"
            type="button"
            :disabled="saving"
            @click="setStatus(annotation, 'pending')"
          ><RotateCcw :size="14" />重新打开</button>
        </li>
      </ol>
    </div>
    <div v-if="user?.role === 'admin' && caseRecord.workflowStatus === 'reviewing'" class="comment-composer">
      <blockquote v-if="selection?.quote">{{ selection.quote }}</blockquote>
      <textarea v-model="content" aria-label="批注内容" :disabled="!canCreate || saving" placeholder="选择正文后添加批注" />
      <button type="button" :disabled="!canCreate || !content.trim() || saving" @click="addAnnotation">添加批注</button>
    </div>
    <div v-if="error && annotations.length" class="comment-inline-error" role="alert">{{ error }}</div>
  </section>
</template>
