<script setup>
import { FileText, X } from "@lucide/vue";

defineProps({
  tabs: { type: Array, default: () => [] },
  active: { type: String, default: "draft" },
  disabled: { type: Boolean, default: false },
  overwritable: { type: Boolean, default: true },
});
const emit = defineEmits(["select", "close", "overwrite"]);
</script>

<template>
  <nav class="version-tabs" aria-label="版本 Tab">
    <button
      class="draft-tab"
      type="button"
      role="tab"
      :disabled="disabled"
      :aria-selected="active === 'draft'"
      :class="{ active: active === 'draft' }"
      @click="emit('select', 'draft')"
    ><FileText :size="14" />当前教师稿</button>
    <div class="version-open-tabs" role="tablist" aria-label="已打开的历史版本">
      <div
        v-for="tab in tabs"
        :key="tab.id"
        class="version-tab-chip"
        :class="{ active: active === tab.id }"
      >
        <button
          type="button"
          role="tab"
          :disabled="disabled"
          :aria-label="tab.label"
          :aria-selected="active === tab.id"
          @click="emit('select', tab.id)"
        >{{ tab.label }}</button>
        <button
          class="close-version-tab"
          type="button"
          :disabled="disabled"
          :aria-label="`关闭 ${tab.label}`"
          @click="emit('close', tab.id)"
        ><X :size="12" /></button>
      </div>
    </div>
    <button
      v-if="active !== 'draft' && overwritable"
      class="overwrite-entry"
      type="button"
      :disabled="disabled"
      @click="emit('overwrite')"
    >
      覆盖当前教师稿
    </button>
  </nav>
</template>
