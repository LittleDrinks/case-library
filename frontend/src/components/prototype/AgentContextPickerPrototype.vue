<script setup>
import { Check, FileText, FolderSearch, Search, X } from "@lucide/vue";
import { computed, nextTick, onMounted, ref } from "vue";

const props = defineProps({
  insertedIds: { type: Array, required: true },
  items: { type: Array, required: true },
});
const emit = defineEmits(["close", "insert"]);
const query = ref("");
const searchRef = ref(null);
const rows = computed(() => props.items.filter((item) => (
  `${item.label}${item.excerpt}`.toLowerCase().includes(query.value.trim().toLowerCase())
)));

function insert(item) {
  emit("insert", item);
}

onMounted(() => nextTick(() => searchRef.value?.focus()));
</script>

<template>
  <section class="context-picker-popover" role="dialog" aria-label="添加对话引用" @keydown.esc="emit('close')">
    <header><span><b>添加到对话</b><small>选择后插入光标位置</small></span><button type="button" aria-label="关闭" @click="emit('close')"><X :size="14" /></button></header>
    <label><Search :size="14" /><input ref="searchRef" v-model="query" type="search" placeholder="搜索选区或案例资料" aria-label="搜索选区或案例资料" /></label>
    <div class="context-picker-list">
      <button v-for="item in rows" :key="item.id" type="button" @click="insert(item)">
        <FileText v-if="item.kind === 'selection'" :size="14" /><FolderSearch v-else :size="14" />
        <span><b>{{ item.label }}</b><small>{{ item.kind === "selection" ? "正文选区" : item.excerpt }}</small></span>
        <em v-if="insertedIds.includes(item.id)"><Check :size="11" />已插入</em>
      </button>
      <p v-if="!rows.length">没有匹配的资料</p>
    </div>
  </section>
</template>
