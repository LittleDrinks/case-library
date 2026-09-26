<script setup>
import { ArrowLeft, Download, Eye } from "@lucide/vue";

defineProps({
  title: { type: String, required: true },
  status: { type: String, required: true },
  saveState: { type: String, required: true },
  editable: { type: Boolean, required: true },
  reviewMode: { type: Boolean, default: false },
  readOnly: { type: Boolean, default: false },
  actions: { type: Array, default: () => [] },
  busyAction: { type: String, default: "" },
  historyAvailable: { type: Boolean, default: false },
  publicCaseId: { type: String, default: "" },
});
const emit = defineEmits(["tool", "export", "lifecycle"]);

const saveLabels = {
  dirty: "未保存",
  saving: "保存中",
  saved: "已保存",
  conflict: "版本冲突",
  error: "保存失败",
};

</script>

<template>
  <header class="workspace-header" :class="{ 'review-header': reviewMode }">
    <div class="workbench-brand">
      <RouterLink to="/my-cases" class="workbench-back" title="返回我的案例" aria-label="返回我的案例"><ArrowLeft :size="16" /></RouterLink>
      <RouterLink to="/" class="workbench-brand-link">
        <img src="/shanghai-university-horizontal-logo.png" alt="上海大学" />
        <span>思政教学案例库 · {{ readOnly ? "阅读" : reviewMode ? "审核" : "工作台" }}</span>
      </RouterLink>
    </div>
    <div class="workspace-state">
      <span class="case-status">{{ status }}</span>
      <span v-if="!readOnly" class="save-state" :data-state="saveState">{{ saveLabels[saveState] }}</span>
    </div>
    <div class="workspace-actions">
      <button type="button" title="导出 DOCX" aria-label="导出 DOCX" @click="emit('export')"><Download :size="17" /></button>
      <RouterLink
        v-if="publicCaseId"
        class="public-page-action"
        :to="{ name: 'case-public', params: { id: publicCaseId } }"
      ><Eye :size="16" aria-hidden="true" />查看公开页</RouterLink>
      <span v-if="actions.length" class="mobile-action-break" aria-hidden="true"></span>
      <button
        v-for="action in actions"
        :key="action.command"
        type="button"
        :class="{ 'lifecycle-action': true, 'primary-action': action.primary }"
        :disabled="Boolean(busyAction)"
        :aria-label="action.label"
        :title="action.label"
        @click="emit('lifecycle', action.command)"
      >{{ busyAction === action.command ? "处理中" : action.label }}</button>
    </div>
  </header>
</template>
