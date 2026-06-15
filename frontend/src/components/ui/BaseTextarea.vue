<template>
  <div class="base-textarea">
    <label v-if="label" :for="inputId" class="textarea-label">{{ label }}</label>
    <textarea
      :id="inputId"
      :value="modelValue"
      :placeholder="placeholder"
      :rows="rows"
      :maxlength="maxLength"
      :disabled="disabled"
      :class="{ 'has-error': error }"
      v-bind="$attrs"
      @input="$emit('update:modelValue', $event.target.value)"
    ></textarea>
    <div
      v-if="$slots.count || error || helpText || maxLength"
      class="textarea-meta"
    >
      <div v-if="error || helpText" class="textarea-hints">
        <p v-if="error" class="textarea-error">{{ error }}</p>
        <p v-if="helpText" class="textarea-help">{{ helpText }}</p>
      </div>
      <div v-if="$slots.count || maxLength" class="textarea-count">
        <slot name="count" :length="currentLength" :max-length="maxLength">
          {{ currentLength }}<template v-if="maxLength">/{{ maxLength }}</template>
        </slot>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue';

defineOptions({ inheritAttrs: false });

const props = defineProps({
  modelValue: { type: String, default: '' },
  id: { type: String, default: undefined },
  label: { type: String, default: '' },
  placeholder: { type: String, default: '' },
  rows: { type: Number, default: 4 },
  error: { type: String, default: '' },
  helpText: { type: String, default: '' },
  maxLength: { type: Number, default: undefined },
  disabled: { type: Boolean, default: false },
});

defineEmits(['update:modelValue']);

const inputId = computed(() => props.id || `textarea-${Math.random().toString(36).slice(2, 9)}`);
const currentLength = computed(() => (props.modelValue || '').length);
</script>

<style scoped>
.base-textarea {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.textarea-label {
  font-size: 14px;
  font-weight: 500;
  color: var(--color-text);
}

.base-textarea textarea {
  width: 100%;
  resize: vertical;
  border: 1px solid var(--color-border-strong);
  border-radius: 6px;
  padding: 10px 14px;
  font-family: inherit;
  font-size: 14px;
  color: var(--color-text);
  background: var(--color-surface);
  outline: none;
  transition: border-color 0.15s, box-shadow 0.15s;
}

.base-textarea textarea:focus {
  border-color: var(--color-brand);
  box-shadow: 0 0 0 3px var(--color-brand-light);
}

.base-textarea textarea.has-error {
  border-color: var(--color-error-text);
}

.base-textarea textarea::placeholder {
  color: var(--color-text-muted);
}

.base-textarea textarea:disabled {
  background: rgba(29, 35, 47, 0.03);
  cursor: not-allowed;
}

.textarea-meta {
  display: flex;
  justify-content: space-between;
  gap: 12px;
}

.textarea-hints {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.textarea-error {
  margin: 0;
  font-size: 13px;
  color: var(--color-error-text);
}

.textarea-help {
  margin: 0;
  font-size: 13px;
  color: var(--color-text-muted);
}

.textarea-count {
  margin-left: auto;
  font-size: 13px;
  color: var(--color-text-muted);
  white-space: nowrap;
}
</style>
