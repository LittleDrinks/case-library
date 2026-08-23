<script setup>
import { ChevronsLeft } from "@lucide/vue";

defineProps({
  items: { type: Array, required: true },
  collapsed: { type: Boolean, required: true },
});
const emit = defineEmits(["collapse", "locate"]);
</script>

<template>
  <aside class="outline-wrap">
    <nav class="outline-panel" aria-label="正文目录">
      <template v-if="!collapsed">
        <button v-for="(item, order) in items" :key="item.index" type="button" :class="`level-${item.level}`" @click="emit('locate', order)">
          {{ item.text }}
        </button>
        <p v-if="!items.length" class="outline-empty">正文还没有小标题</p>
      </template>
      <button
        class="outline-collapse"
        type="button"
        :title="collapsed ? '展开目录' : '收起目录'"
        :aria-label="collapsed ? '展开目录' : '收起目录'"
        @click="emit('collapse')"
      >
        <ChevronsLeft :size="16" aria-hidden="true" />
      </button>
    </nav>
  </aside>
</template>
