<script setup>
import { computed, ref } from "vue";
import { Check, MessageSquareText, Sparkles, X } from "@lucide/vue";
import { api } from "../api.js";

const props = defineProps({
  caseRecord: { type: Object, required: true },
  user: { type: Object, default: null },
  draft: { type: Object, default: null },
  thread: { type: Object, default: null },
  // 保存前门禁：先 flush autosave，再由 Workbench 校验 Decoration 映射锚点；拒绝时返回 falsy。
  beforeSave: { type: Function, default: async () => true },
});
const emit = defineEmits(["close", "saved", "resolved", "case-revised", "ask-ai", "replied"]);

const content = ref("");
const saving = ref(false);
const error = ref("");

const isDraft = computed(() => Boolean(props.draft));
// 与 CommentPanel.canCompose 同一判定：作者草稿或审核中管理员，不放开他人草稿。
const canCompose = computed(() => Boolean(
  props.user && (
    (props.user.id === props.caseRecord.ownerId && props.caseRecord.workflowStatus === "draft")
    || (props.user.role === "admin" && props.caseRecord.workflowStatus === "reviewing")
  ),
));
const canAskDraftAi = computed(() => Boolean(
  canCompose.value && props.user?.id === props.caseRecord.ownerId
    && props.caseRecord.workflowStatus === "draft",
));
const canResolve = computed(() => Boolean(
  props.thread && props.user?.id === props.caseRecord.ownerId
    && props.thread.status === "pending",
));
// 与服务端 _require_reply_actor 对齐：审核批注（绑定版本）作者与管理员均可讨论；
// 私人批注仅批注作者可回复。讨论还需批注未解决且锚点有效。
const canDiscuss = computed(() => {
  if (!props.thread || props.thread.status !== "pending") return false;
  if ((props.thread.anchorState || "active") !== "active") return false;
  if (props.thread.versionId != null) {
    return Boolean(props.user) && (
      props.user.id === props.caseRecord.ownerId || props.user.role === "admin"
    );
  }
  return props.user?.id === props.thread.createdBy;
});
const canAskAi = computed(() => Boolean(
  canDiscuss.value && props.user?.id === props.thread?.createdBy
    && props.user?.id === props.caseRecord.ownerId
    && props.caseRecord.workflowStatus === "draft",
));
const latestRevision = computed(() => (
  [...(props.thread?.revisions || [])].reverse()
    .find((revision) => revision.status === "pending") || null
));
// 服务端仅批注作者可合并修订；管理员讨论但不拥有采用权。
const canAdopt = computed(() => Boolean(
  props.user?.id === props.thread?.createdBy
    && props.user?.id === props.caseRecord.ownerId
    && props.caseRecord.workflowStatus === "draft"
    && props.thread.status === "pending"
    && (props.thread.anchorState || "active") === "active"
    && latestRevision.value,
));

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
    source: props.caseRecord.workflowStatus === "reviewing" ? "admin" : "manual",
  };
}

// 统一事务壳：占位 saving、捕获错误；body 返回 null 表示被门禁拦截。
async function runMutation(action) {
  saving.value = true;
  error.value = "";
  try {
    await action();
  } catch (caught) {
    error.value = caught.message || "批注保存失败";
  } finally {
    saving.value = false;
  }
}

// 草稿：落正式批注（先过 beforeSave 门禁）。询问AI=保存后再请求修订；不保存则不发任何AI请求。
async function saveDraft({ askAi = false } = {}) {
  if (!canCompose.value || !content.value.trim() || saving.value) return;
  await runMutation(async () => {
    if (await props.beforeSave() === false) {
      error.value = "正文尚未保存，批注未提交。";
      return;
    }
    const created = await api.createAnnotation(
      props.caseRecord.id, payload(), props.user.csrfToken,
    );
    content.value = "";
    emit("saved", created);
    if (askAi) emit("ask-ai", created);
  });
}

// 既有线程：追加意见走回复接口，返回完整线程即时回流浮窗；询问AI=意见保存成功后再请求。
async function saveThreadOpinion({ askAi = false } = {}) {
  const value = content.value.trim();
  if (!canDiscuss.value || !value || saving.value) return;
  await runMutation(async () => {
    const updated = await api.replyAnnotation(
      props.caseRecord.id, props.thread.id, { content: value }, props.user.csrfToken,
    );
    content.value = "";
    emit("replied", updated);
    if (askAi) emit("ask-ai", updated);
  });
}

function save(options) {
  return isDraft.value ? saveDraft(options) : saveThreadOpinion(options);
}

async function resolve() {
  if (!canResolve.value || saving.value) return;
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
      </template>
      <p v-if="error" class="float-error" role="alert">{{ error }}</p>
    </div>
    <footer>
      <div v-if="isDraft" class="float-compose">
        <textarea
          v-model="content"
          aria-label="批注内容"
          placeholder="写下你的意见…"
          :disabled="saving || !canCompose"
        />
        <div class="float-compose-actions">
          <button type="button" :disabled="saving" @click="close">取消</button>
          <button
            v-if="canCompose"
            type="button"
            class="float-primary"
            :disabled="saving || !content.trim()"
            @click="save()"
          >保存意见</button>
          <button
            v-if="canAskDraftAi"
            type="button"
            :disabled="saving || !content.trim()"
            @click="save({ askAi: true })"
          ><Sparkles :size="13" />询问AI</button>
        </div>
      </div>
      <div v-else-if="thread" class="float-compose">
        <textarea
          v-model="content"
          aria-label="批注内容"
          placeholder="补充意见…"
          :disabled="saving || !canDiscuss"
        />
        <div class="float-compose-actions">
          <button
            v-if="canResolve"
            type="button"
            :disabled="saving"
            @click="resolve"
          ><Check :size="13" />解决批注</button>
          <button
            v-if="canDiscuss"
            type="button"
            :disabled="saving || !content.trim()"
            @click="save()"
          >保存意见</button>
          <button
            v-if="canAskAi"
            type="button"
            :disabled="saving || !content.trim()"
            @click="save({ askAi: true })"
          ><Sparkles :size="13" />询问AI</button>
          <button
            v-if="canAdopt"
            type="button"
            aria-label="采用并解决"
            class="float-primary"
            :disabled="saving"
            @click="adopt"
          ><Check :size="13" />采用并解决</button>
        </div>
      </div>
    </footer>
  </aside>
</template>
