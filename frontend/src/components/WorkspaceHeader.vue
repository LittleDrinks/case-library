<script setup>
import { ClipboardCheck, Download, Eye, History, Paperclip, Sparkles } from "@lucide/vue";

const props = defineProps({
  title: { type: String, required: true },
  status: { type: String, required: true },
  saveState: { type: String, required: true },
  editable: { type: Boolean, required: true },
  reviewMode: { type: Boolean, default: false },
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
    <div class="workspace-crumb" :data-mobile-label="reviewMode ? '案例审核' : '案例编辑'">
      <span>{{ reviewMode ? "审核管理" : "我的案例" }}</span><i>/</i><b>{{ title }}</b>
    </div>
    <div class="workspace-state">
      <span class="case-status">{{ status }}</span>
      <span class="save-state" :data-state="saveState">{{ saveLabels[saveState] }}</span>
    </div>
    <div class="workspace-actions">
      <button type="button" title="AI" aria-label="AI" @click="emit('tool', 'chat')"><Sparkles :size="17" /></button>
      <button type="button" title="版本历史" aria-label="版本历史" :disabled="!historyAvailable" @click="emit('tool', 'history')"><History :size="17" /></button>
      <button type="button" title="附件" aria-label="附件" @click="emit('tool', 'files')"><Paperclip :size="17" /></button>
      <button type="button" title="提交前自检" aria-label="提交前自检" disabled><ClipboardCheck :size="17" /></button>
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
