<script setup>
import { computed } from "vue";
import { Sparkles } from "@lucide/vue";
import { mockResources, store } from "../store.js";

// 右轨面板：会话历史 / 修改审阅 / 资料。AI 主面板在 AiPane。
defineProps({ tab: { type: String, required: true } });
const emit = defineEmits(["open-thread", "new-thread", "rename-thread"]);

const pendingRevisions = computed(() => store.annotations.filter((a) => a.kind === "revision" && a.status === "pending"));
const handledRevisions = computed(() => store.annotations.filter((a) => a.kind === "revision" && a.status !== "pending"));
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
          <button type="button" class="thread-rename" title="重命名" @click="emit('rename-thread', t)">✎</button>
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
        </li>
        <li v-for="rev in handledRevisions" :key="rev.id">
          <p><s>{{ rev.original }}</s></p>
          <p class="rev-replacement">{{ rev.replacement }}</p>
          <span class="tag" :class="rev.status">{{ rev.status === "accepted" ? "已采用" : "已拒绝" }}</span>
        </li>
      </ul>
    </template>
    <template v-else-if="tab === 'resources'">
      <header class="rail-pane-head"><b>资料</b><span>已挂载 3</span></header>
      <ul class="resource-list">
        <li v-for="r in mockResources" :key="r.id">
          <b>{{ r.name }}</b>
          <small>{{ r.meta }}</small>
        </li>
      </ul>
    </template>
  </div>
</template>
