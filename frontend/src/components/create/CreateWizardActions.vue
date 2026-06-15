<template>
  <div class="create-wizard-actions">
    <div class="actions-left">
      <button v-if="currentStep > 0 && currentStep < 4" type="button" class="btn-secondary" @click="$emit('prev')">上一步</button>
      <button v-if="currentStep === 4" type="button" class="btn-secondary" @click="$emit('edit')">返回修改</button>
    </div>
    <div class="actions-right">
      <template v-if="currentStep < 4">
        <button type="button" class="btn-secondary" :disabled="saving" @click="$emit('save')">
          {{ saving ? '保存中…' : '保存草稿' }}
        </button>
        <button type="button" class="btn-primary" @click="$emit('next')">
          继续 <span class="arrow" aria-hidden="true">→</span>
        </button>
      </template>
    </div>
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
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  margin-top: 40px;
  padding-top: 24px;
  border-top: 1px solid var(--color-border);
}

.actions-left,
.actions-right {
  display: flex;
  gap: 12px;
  align-items: center;
}

.actions-right {
  margin-left: auto;
}

.btn-primary,
.btn-secondary {
  min-width: 0;
  min-height: 42px;
  padding: 10px 24px;
  border-radius: 6px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: opacity 0.15s, transform 0.05s;
}

.btn-primary {
  border: 1px solid var(--color-brand);
  background: var(--color-brand);
  color: #fff;
  box-shadow: none;
}

.btn-secondary {
  border: 1px solid var(--color-border-strong);
  background: var(--color-surface);
  color: var(--color-text);
}

.btn-primary:disabled,
.btn-secondary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.arrow {
  margin-left: 6px;
  font-size: 14px;
  line-height: 1;
}

@media (max-width: 640px) {
  .create-wizard-actions,
  .actions-left,
  .actions-right {
    width: 100%;
  }

  .btn-primary,
  .btn-secondary {
    flex: 1;
    min-width: 0;
  }

  .actions-left,
  .actions-right {
    justify-content: center;
  }
}
</style>
