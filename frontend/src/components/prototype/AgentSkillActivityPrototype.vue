<script setup>
import { Check, LoaderCircle, WandSparkles } from "@lucide/vue";

defineProps({ status: { type: String, required: true } });
</script>

<template>
  <li class="activity-event skill-event" :class="`is-${status}`">
    <span class="activity-marker"><LoaderCircle v-if="status === 'running'" class="spin" :size="13" /><WandSparkles v-else :size="13" /></span>
    <div class="activity-event-body">
      <div class="activity-event-title">
        <b :class="{ 'activity-shimmer-text': status === 'running' }">{{ status === "running" ? "正在载入 Skill" : "使用了思政案例生成 v2.1" }}</b>
        <em v-if="status === 'done'"><Check :size="10" />完成</em>
      </div>
      <small>{{ status === "running" ? "读取受控指令与任务模板" : "版本与内容哈希已固定" }}</small>
    </div>
  </li>
</template>
