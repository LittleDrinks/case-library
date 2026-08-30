<script setup>
import { Brain, Check, ChevronRight, LoaderCircle } from "@lucide/vue";

defineProps({ status: { type: String, required: true } });
</script>

<template>
  <li class="activity-event thinking-event" :class="`is-${status}`">
    <span class="activity-marker"><LoaderCircle v-if="status === 'running'" class="spin" :size="13" /><Brain v-else :size="13" /></span>
    <details :open="status === 'running'">
      <summary>
        <span>
          <b :class="{ 'activity-shimmer-text': status === 'running' }">{{ status === "queued" ? "等待分析" : status === "running" ? "正在分析选区" : "分析了 6 秒" }}</b>
          <small v-if="status === 'queued'">等待 Skill 就绪</small>
        </span>
        <em v-if="status === 'done'"><Check :size="10" />完成</em>
        <span v-if="status === 'running'" class="thinking-pulse" aria-hidden="true"></span>
        <ChevronRight class="activity-chevron" :size="13" />
      </summary>
      <ol v-if="status === 'running'" class="thinking-stages">
        <li>识别不可观察的目标表述</li>
        <li>核对任务动作与证据范围</li>
      </ol>
      <p v-else-if="status === 'done'" class="thinking-summary">“形成判断”难以观察，需要改成学生可执行、教师可评价的动作，同时保留原有责任维度。</p>
    </details>
  </li>
</template>
