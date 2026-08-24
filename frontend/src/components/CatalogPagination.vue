<script setup>
import { ChevronLeft, ChevronRight } from "@lucide/vue";

const props = defineProps({
  page: { type: Number, required: true },
  total: { type: Number, required: true },
  nextCursor: { type: String, default: null },
  previousCursor: { type: String, default: null },
});
const emit = defineEmits(["change"]);

function change(cursor) {
  if (cursor) emit("change", cursor);
}
</script>

<template>
  <nav
    v-if="previousCursor || nextCursor"
    class="catalog-pagination"
    aria-label="分页"
  >
    <p>第 {{ page }} 页 · 共 {{ total }} 条</p>
    <div>
      <button type="button" aria-label="上一页" :disabled="!previousCursor" @click="change(previousCursor)">
        <ChevronLeft :size="15" aria-hidden="true" />
      </button>
      <button type="button" aria-label="下一页" :disabled="!nextCursor" @click="change(nextCursor)">
        <ChevronRight :size="15" aria-hidden="true" />
      </button>
    </div>
  </nav>
</template>
