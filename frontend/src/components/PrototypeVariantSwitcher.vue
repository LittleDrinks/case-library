<script setup>
import { ChevronLeft, ChevronRight } from "@lucide/vue";
import { onBeforeUnmount, onMounted } from "vue";

const props = defineProps({
  scenario: { type: String, required: true },
  variant: { type: String, required: true },
});
const emit = defineEmits(["change", "scenario"]);
const variants = [["A", "对话为主"], ["B", "任务时间线"], ["C", "会话分栏"]];
const scenarios = [["complete", "完成"], ["running", "运行中"], ["error", "失败"]];

function cycle(direction) {
  const index = variants.findIndex(([key]) => key === props.variant);
  emit("change", variants[(index + direction + variants.length) % variants.length][0]);
}

function onKeydown(event) {
  if (["INPUT", "TEXTAREA"].includes(event.target?.tagName) || event.target?.isContentEditable) return;
  if (event.key === "ArrowLeft") cycle(-1);
  if (event.key === "ArrowRight") cycle(1);
}

onMounted(() => window.addEventListener("keydown", onKeydown));
onBeforeUnmount(() => window.removeEventListener("keydown", onKeydown));
</script>

<template>
  <nav class="agent-prototype-switcher" aria-label="原型方案切换">
    <div class="variant-cycle"><button type="button" aria-label="上一个方案" @click="cycle(-1)"><ChevronLeft :size="17" /></button><span><b>{{ variant }}</b> {{ variants.find(([key]) => key === variant)?.[1] }}</span><button type="button" aria-label="下一个方案" @click="cycle(1)"><ChevronRight :size="17" /></button></div>
    <div class="scenario-control" aria-label="运行状态"><button v-for="item in scenarios" :key="item[0]" type="button" :class="{ active: scenario === item[0] }" @click="emit('scenario', item[0])">{{ item[1] }}</button></div>
  </nav>
</template>
