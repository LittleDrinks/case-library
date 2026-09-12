<script setup>
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { FileText, History, X } from "@lucide/vue";

const props = defineProps({
  tabs: { type: Array, default: () => [] },
  active: { type: String, default: "draft" },
  disabled: { type: Boolean, default: false },
  overwritable: { type: Boolean, default: true },
});
const emit = defineEmits(["select", "close", "overwrite"]);
const expanded = ref(false);
let closeTimer;
const visible = computed(() => expanded.value);

function expand() {
  clearTimeout(closeTimer);
  expanded.value = true;
}

function collapse() {
  clearTimeout(closeTimer);
  closeTimer = setTimeout(() => {
    expanded.value = false;
  }, 450);
}

function toggle() {
  if (visible.value) expanded.value = false;
  else expand();
}

function handleTouchStart(event) {
  if (!event.target.closest?.(".version-tabs-toggle")) expand();
}

function handleFocusOut(event) {
  if (!event.currentTarget.contains(event.relatedTarget)) collapse();
}

function handleKeydown(event) {
  if (["Enter", " "].includes(event.key)) { event.preventDefault(); toggle(); }
}

watch(() => props.active, (active) => { if (active !== "draft") expand(); }, { immediate: true });
onBeforeUnmount(() => clearTimeout(closeTimer));
</script>

<template>
  <nav
    class="version-tabs"
    :class="{ expanded: visible }"
    aria-label="版本 Tab"
    @mouseenter="expand"
    @mouseleave="collapse"
    @touchstart.passive="handleTouchStart"
    @focusin="expand"
    @focusout="handleFocusOut"
  >
    <button
      class="version-tabs-toggle"
      type="button"
      :disabled="disabled"
      :aria-expanded="visible"
      :aria-label="visible ? '收起版本 Tab' : '展开版本 Tab'"
      @click="toggle"
      @keydown="handleKeydown"
    ><History :size="14" /><span>历史版本</span><small>{{ tabs.length + 1 }}</small></button>
    <div class="version-tabs-content">
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
      >恢复此版本</button>
    </div>
  </nav>
</template>
