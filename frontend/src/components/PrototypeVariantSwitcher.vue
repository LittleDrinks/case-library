<script setup>
import { ChevronLeft, ChevronRight } from "@lucide/vue";
import { onBeforeUnmount, onMounted } from "vue";

const props = defineProps({ variant: { type: String, required: true } });
const emit = defineEmits(["change"]);
const variants = [
  ["A", "选区候选栏"],
  ["B", "内联修订"],
  ["C", "专注画布"],
];

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
  <nav class="prototype-switcher" aria-label="原型方案切换">
    <button type="button" aria-label="上一个方案" @click="cycle(-1)"><ChevronLeft :size="17" /></button>
    <span><b>{{ variant }}</b> {{ variants.find(([key]) => key === variant)?.[1] }}</span>
    <button type="button" aria-label="下一个方案" @click="cycle(1)"><ChevronRight :size="17" /></button>
  </nav>
</template>
