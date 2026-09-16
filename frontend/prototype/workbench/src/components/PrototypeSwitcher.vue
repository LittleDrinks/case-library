<script setup>
import { onBeforeUnmount, onMounted } from "vue";
import { ChevronLeft, ChevronRight } from "@lucide/vue";
const props = defineProps({ current: String, count: Number, expanded: String, resolved: Number });
const emit = defineEmits(["change"]);
const variants = [{ id: "A", label: "讨论卡片" }, { id: "B", label: "极简边注" }, { id: "C", label: "批注清单" }];
function select(id) {
  const url = new URL(location.href);
  url.searchParams.set("variant", id);
  history.replaceState(null, "", url);
  emit("change", id);
}
function cycle(step) {
  select(variants[(variants.findIndex(v => v.id === props.current) + step + 3) % 3].id);
}
function onKey(event) {
  if (event.target.closest('input, textarea, select, [contenteditable="true"], [role="textbox"]')) return;
  if (!["ArrowLeft", "ArrowRight"].includes(event.key)) return;
  event.preventDefault();
  cycle(event.key === "ArrowLeft" ? -1 : 1);
}
function restore() {
  const id = new URLSearchParams(location.search).get("variant");
  emit("change", variants.some(v => v.id === id) ? id : "A");
}
onMounted(() => { window.addEventListener("keydown", onKey); window.addEventListener("popstate", restore); });
onBeforeUnmount(() => { window.removeEventListener("keydown", onKey); window.removeEventListener("popstate", restore); });
</script>
<template>
  <aside class="prototype-switcher" aria-label="批注视觉原型切换">
    <div class="prototype-switcher-controls">
      <span class="prototype-switcher-label">批注视觉原型</span>
      <button aria-label="上一版" @click="cycle(-1)"><ChevronLeft :size="16" /></button>
      <button v-for="variant in variants" :key="variant.id" :aria-pressed="current === variant.id" @click="select(variant.id)">{{ variant.id }} · {{ variant.label }}</button>
      <button aria-label="下一版" @click="cycle(1)"><ChevronRight :size="16" /></button>
    </div>
    <output>{{ count }} 条批注 · {{ resolved }} 条已解决 · {{ expanded ? '已展开 ' + expanded : '全部收起' }} · 仅内存，切换保留内容</output>
  </aside>
</template>
