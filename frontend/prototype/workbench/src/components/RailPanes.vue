<script setup>
import { computed, ref } from "vue";
import { Sparkles } from "@lucide/vue";
import { store } from "../store.js";

// 右轨面板：会话历史 / 修改审阅 / 资料。AI 主面板在 AiPane。
defineProps({ tab: { type: String, required: true } });
const emit = defineEmits(["open-thread", "new-thread", "rename-thread", "preview", "accept", "reject"]);

const renaming = ref("");
const name = ref("");
function rename(t) {
  if (!name.value.trim()) return;
  t.title = name.value.trim(); t.manualRenamed = true; t.auto = false;
  renaming.value = "";
}
const pendingRevisions = computed(() => store.revisions.filter((a) => a.kind === "revision" && a.status === "pending"));
const handledRevisions = computed(() => store.revisions.filter((a) => a.kind === "revision" && a.status !== "pending"));
</script>

<template>
  <div class="rail-pane">
    <template v-if="tab === 'history'">
      <header class="rail-pane-head">
        <b>会话历史</b>
        <button type="button" @click="emit('new-thread')"><Sparkles :size="13" /> 新会话</button>
      </header>
      <ul class="thread-list">
        <li v-for="t in store.threads" :key="t.id" :class="{ current: t.id === store.activeThreadId }">
          <button type="button" class="thread-open" @click="emit('open-thread', t)">
            <b>{{ t.title }}</b>
            <small>{{ t.auto ? "AI 摘要标题" : "手动命名" }} · {{ t.messages.length }} 条消息</small>
          </button>
          <form v-if="renaming === t.id" class="rename-thread" @submit.prevent="rename(t)"><input v-model="name" aria-label="会话名称" @keydown.esc="renaming = ''" /><button type="submit">保存</button></form>
          <button type="button" class="thread-rename" title="重命名" @click="renaming = t.id; name = t.title">✎</button>
        </li>
      </ul>
    </template>
    <template v-else-if="tab === 'review'">
      <header class="rail-pane-head"><b>修改审阅</b><span>{{ pendingRevisions.length }} 待处理</span></header>
      <div v-if="!pendingRevisions.length && !handledRevisions.length" class="rail-empty">暂无修订建议</div>
      <ul class="review-list">
        <li v-for="rev in pendingRevisions" :key="rev.id">
          <p><s>{{ rev.original }}</s></p>
          <p class="rev-replacement">{{ rev.replacement }}</p>
          <small>{{ rev.reason }}</small>
          <span class="tag pending">待处理</span>
          <div class="rev-actions"><button @click="emit('preview', rev)">{{ store.ui.previewId === rev.id ? '关闭预览' : '预览' }}</button><button @click="emit('accept', rev)">采用</button><button @click="emit('reject', rev)">拒绝</button></div>
        </li>
        <li v-for="rev in handledRevisions" :key="rev.id">
          <p><s>{{ rev.original }}</s></p>
          <p class="rev-replacement">{{ rev.replacement }}</p>
          <span class="tag" :class="rev.status">{{ rev.status === "accepted" ? "已采用" : rev.status === "stale" ? "原文已变化" : "已拒绝" }}</span>
        </li>
      </ul>
    </template>

  </div>
</template>
