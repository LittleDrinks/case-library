<template>
  <div class="create-wizard-actions">
    <template v-if="currentStep > 0 && currentStep < 4">
      <button type="button" class="btn-secondary" @click="$emit('prev')">上一步</button>
    </template>
    <template v-if="currentStep < 4">
      <button type="button" class="btn-secondary" :disabled="saving" @click="$emit('save')">
        {{ saving ? '保存中…' : '保存草稿' }}
      </button>
      <button type="button" class="btn-primary" @click="$emit('next')">
        继续 <span class="arrow" aria-hidden="true">→</span>
      </button>
    </template>
    <template v-if="currentStep === 4">
      <button type="button" class="btn-secondary" @click="$emit('edit')">返回修改</button>
    </template>
  </div>
</template>

<script setup>
/**
 * 创建向导底部操作栏
 *
 * 根据当前步骤渲染“上一步/保存草稿/继续/返回修改”按钮，仅负责交互转发，
 * 不处理保存或校验逻辑。
 */
defineProps({
  currentStep: {
    type: Number,
    required: true,
  },
  saving: {
    type: Boolean,
    default: false,
  },
});

defineEmits(["prev", "save", "next", "edit"]);
</script>

<style scoped>
.create-wizard-actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 24px;
  padding-top: 16px;
  border-top: 1px solid var(--color-border);
}

.btn-primary,
.btn-secondary {
  padding: 10px 18px;
  border-radius: 6px;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: opacity 0.15s, transform 0.05s;
}

.btn-primary {
  border: 0;
  background: var(--color-brand);
  color: #fff;
}

.btn-secondary {
  border: 1px solid var(--color-border-strong);
  background: var(--color-surface);
  color: var(--color-text-secondary);
}

.btn-primary:disabled,
.btn-secondary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.arrow {
  margin-left: 2px;
}
</style>
