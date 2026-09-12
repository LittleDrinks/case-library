<script setup>
import { computed, ref } from "vue";
import { Check, MessageSquareText, Sparkles, X } from "@lucide/vue";
import { api } from "../api.js";

const props = defineProps({
  caseRecord: { type: Object, required: true },
  user: { type: Object, default: null },
  draft: { type: Object, default: null },
  thread: { type: Object, default: null },
});
const emit = defineEmits(["close", "saved", "resolved", "case-revised", "ask-ai"]);

const content = ref("");
const saving = ref(false);
const error = ref("");
const replyText = ref("");

const isDraft = computed(() => Boolean(props.draft));
const isAuthor = computed(() => props.user?.id === props.caseRecord.ownerId);
const canDiscuss = computed(() => Boolean(
  props.thread && props.user?.id === props.thread.createdBy
    && props.thread.status === "pending"
    && (props.thread.anchorState || "active") === "active",
));
const latestRevision = computed(() => (
  [...(props.thread?.revisions || [])].reverse()
    .find((revision) => revision.status === "pending") || null
));
const canAdopt = computed(() => Boolean(canDiscuss.value && latestRevision.value));

function close() {
  if (saving.value) return;
  content.value = "";
  error.value = "";
  emit("close");
}

function payload() {
  return {
    from: props.draft.from,
    to: props.draft.to,
    quote: props.draft.quote,
    quoteHash: props.draft.quoteHash,
    section: props.draft.section,
    revision: props.draft.revision,
    content: content.value.trim(),
    source: props.user?.role === "admin" ? "admin" : "manual",
  };
}

async function save() {
  if (!isAuthor.value || !content.value.trim() || saving.value) return;
  saving.value = true;
  error.value = "";
  try {
    const created = await api.createAnnotation(
      props.caseRecord.id, payload(), props.user.csrfToken,
    );
    content.value = "";
    emit("saved", created);
  } catch (caught) {
    error.value = caught.message || "批注保存失败";
  } finally {
    saving.value = false;
  }
}

// 询问AI=先落一条正式意见再请求修订；不保存意见则不发送任何AI请求。
async function saveAndAsk() {
  if (!isAuthor.value || !content.value.trim() || saving.value) return;
  saving.value = true;
  error.value = "";
  try {
    const created = await api.createAnnotation(
      props.caseRecord.id, payload(), props.user.csrfToken,
    );
    content.value = "";
    emit("saved", created);
    emit("ask-ai", created);
  } catch (caught) {
    error.value = caught.message || "批注保存失败";
  } finally {
    saving.value = false;
  }
}

async function resolve() {
  if (!isAuthor.value || saving.value) return;
  saving.value = true;
  error.value = "";
  try {
    const updated = await api.setAnnotationStatus(
      props.caseRecord.id, props.thread.id, "resolved", props.user.csrfToken,
    );
    emit("resolved", updated);
  } catch (caught) {
    error.value = caught.message || "状态更新失败";
  } finally {
    saving.value = false;
  }
}

async function adopt() {
  if (!canAdopt.value || saving.value) return;
  saving.value = true;
  error.value = "";
  try {
    const result = await api.mergeAnnotation(
      props.caseRecord.id, props.thread.id, props.user.csrfToken,
    );
    emit("case-revised", result.case);
    emit("resolved", result.annotation);
  } catch (caught) {
    error.value = caught.message || "合并修订失败";
  } finally {
    saving.value = false;
  }
}

async function reply() {
  const value = replyText.value.trim();
  if (!value || saving.value) return;
  saving.value = true;
  error.value = "";
  try {
    await api.replyAnnotation(
      props.caseRecord.id, props.thread.id, { content: value }, props.user.csrfToken,
    );
    replyText.value = "";
    emit("replied");
  } catch (caught) {
    error.value = caught.message || "回复失败";
  } finally {
    saving.value = false;
  }
}

function revisionStatus(status) {
  return ({
    pending: "待采用", accepted: "已合并", rejected: "已拒绝", expired: "已失效",
  })[status] || status;
}
</script>

<template>
  <aside class="annotation-float" role="dialog" aria-label="批注浮窗">
    <header>
      <MessageSquareText :size="16" aria-hidden="true" />
      <b>{{ isDraft ? "新增批注" : "批注与修订" }}</b>
      <button type="button" aria-label="关闭批注浮窗" :disabled="saving" @click="close"><X :size="16" /></button>
    </header>
    <blockquote v-if="draft?.quote || thread?.quote" class="float-quote">{{ draft?.quote || thread?.quote }}</blockquote>
    <p v-if="thread && thread.status !== 'resolved'" class="float-anchor-state">
      {{ thread.anchorState === "deleted" ? "原文已删除" : thread.anchorState === "changed" ? "原文已变动，旧修订不可合并" : "" }}
    </p>
    <div class="float-scroll">
      <p v-if="isDraft" class="float-hint">输入意见并发送后，这条批注才会保存。</p>
      <template v-else-if="thread">
        <article class="float-opinion"><b>意见</b><p>{{ thread.content }}</p></article>
        <article
          v-for="(revision, index) in thread.revisions || []"
          :key="revision.id"
          class="float-revision-card"
        >
          <header>
            <span>第 {{ index + 1 }} 轮 · {{ revisionStatus(revision.status) }}</span>
          </header>
          <p>替换为：{{ revision.replacement }}</p>
          <small v-if="revision.reason">理由：{{ revision.reason }}</small>
        </article>
        <ul v-if="thread.replies?.length" class="float-replies">
          <li v-for="item in thread.replies" :key="item.id">{{ item.content }}</li>
        </ul>
        <div class="float-reply-row">
          <input v-model="replyText" aria-label="回复批注" placeholder="回复" :disabled="saving" />
          <button type="button" :disabled="saving || !replyText.trim()" @click="reply">回复</button>
        </div>
      </template>
      <p v-if="error" class="float-error" role="alert">{{ error }}</p>
    </div>
    <footer>
      <div v-if="isDraft" class="float-compose">
        <textarea
          v-model="content"
          aria-label="批注内容"
          placeholder="写下你的意见…"
          :disabled="saving || !isAuthor"
        />
        <div class="float-compose-actions">
          <button type="button" :disabled="saving" @click="close">取消</button>
          <button
            v-if="isAuthor"
            type="button"
            class="float-primary"
            :disabled="saving || !content.trim()"
            @click="save"
          >保存意见</button>
          <button
            v-if="isAuthor"
            type="button"
            :disabled="saving || !content.trim()"
            @click="saveAndAsk"
          ><Sparkles :size="13" />询问AI</button>
        </div>
      </div>
      <div v-else-if="thread" class="float-thread-actions">
        <button
          v-if="isAuthor && thread.status === 'pending'"
          type="button"
          :disabled="saving"
          @click="resolve"
        ><Check :size="13" />解决批注</button>
        <button
          v-if="canAdopt"
          type="button"
          aria-label="采用并解决"
          class="float-primary"
          :disabled="saving"
          @click="adopt"
        ><Check :size="13" />采用并解决</button>
      </div>
    </footer>
  </aside>
</template>
