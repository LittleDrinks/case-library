<script setup>
import { BookOpen, Check, ChevronRight, CircleAlert, Database, LoaderCircle, Search } from "@lucide/vue";

defineProps({ status: { type: String, required: true } });
const results = [
  { icon: BookOpen, type: "案例", title: "人工智能赋能教育的伦理边界" },
  { icon: Database, type: "知识", title: "课堂教学设计规范" },
  { icon: BookOpen, type: "案例", title: "生成式 AI 与学术诚信" },
];
</script>

<template>
  <li class="activity-event tool-event" :class="`is-${status}`">
    <span class="activity-marker"><LoaderCircle v-if="status === 'running'" class="spin" :size="13" /><CircleAlert v-else-if="status === 'error'" :size="13" /><Search v-else :size="13" /></span>
    <details :open="status === 'running' || status === 'done' || status === 'error'">
      <summary>
        <span>
          <b :class="{ 'activity-shimmer-text': status === 'running' }">{{ status === "done" ? "检索了 3 条平台资料" : status === "running" ? "正在检索平台资料" : status === "error" ? "平台资料检索失败" : "等待检索" }}</b>
          <small><code>search_corpus</code>{{ status === "done" ? " · 842 ms" : status === "queued" ? " · 等待分析" : "" }}</small>
        </span>
        <em v-if="status === 'done'"><Check :size="10" />完成</em>
        <ChevronRight class="activity-chevron" :size="13" />
      </summary>
      <div v-if="status !== 'queued'" class="tool-query"><Search :size="11" /><span>课堂治理 学术诚信 教学目标</span></div>
      <div v-if="status === 'running'" class="tool-searching"><i></i><span>正在匹配相关案例与知识条目</span></div>
      <div v-if="status === 'done'" class="tool-sources">
        <button v-for="result in results" :key="result.title" type="button"><component :is="result.icon" :size="13" /><span><b>{{ result.title }}</b><small>{{ result.type }} · 平台资料</small></span></button>
      </div>
      <div v-if="status === 'error'" class="tool-error-result"><CircleAlert :size="14" /><span><b>检索服务暂时不可用</b><small>没有资料进入模型上下文。</small></span></div>
    </details>
  </li>
</template>
