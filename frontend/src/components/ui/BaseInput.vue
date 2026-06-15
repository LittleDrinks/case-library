<template>
  <div class="base-input">
    <label v-if="label" :for="inputId" class="input-label">{{ label }}</label>
    <div
      class="input-wrap"
      :class="{
        'has-error': error,
        'has-prefix': $slots.prefix,
        'has-suffix': $slots.suffix,
      }"
    >
      <span v-if="$slots.prefix" class="input-affix input-prefix">
        <slot name="prefix" />
      </span>
      <input
        :id="inputId"
        :type="type"
        :value="modelValue"
        :placeholder="placeholder"
        :disabled="disabled"
        v-bind="$attrs"
        @input="$emit('update:modelValue', $event.target.value)"
        @blur="$emit('blur', $event)"
        @focus="$emit('focus', $event)"
      />
      <span v-if="$slots.suffix" class="input-affix input-suffix">
        <slot name="suffix" />
      </span>
    </div>
    <div v-if="error || helpText" class="input-hints">
      <p v-if="error" class="input-error">{{ error }}</p>
      <p v-if="helpText" class="input-help">{{ helpText }}</p>
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
  type: { type: String, default: 'text' },
  placeholder: { type: String, default: '' },
  error: { type: String, default: '' },
  helpText: { type: String, default: '' },
  disabled: { type: Boolean, default: false },
});

defineEmits(['update:modelValue', 'blur', 'focus']);

const inputId = computed(() => props.id || `input-${Math.random().toString(36).slice(2, 9)}`);
</script>

<style scoped>
.base-input {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.input-label {
  font-size: 14px;
  font-weight: 500;
  color: var(--color-text);
}

.input-wrap {
  display: flex;
  align-items: center;
  border: 1px solid var(--color-border-strong);
  border-radius: 6px;
  background: var(--color-surface);
  transition: border-color 0.15s, box-shadow 0.15s;
  overflow: hidden;
}

.input-wrap:focus-within {
  border-color: var(--color-brand);
  box-shadow: 0 0 0 3px var(--color-brand-light);
}

.input-wrap.has-error {
  border-color: var(--color-error-text);
}

.input-wrap input {
  flex: 1;
  min-width: 0;
  border: 0;
  padding: 10px 14px;
  font-family: inherit;
  font-size: 14px;
  color: var(--color-text);
  background: transparent;
  outline: none;
}

.input-wrap input::placeholder {
  color: var(--color-text-muted);
}

.input-wrap input:disabled {
  background: rgba(29, 35, 47, 0.03);
  cursor: not-allowed;
}

.input-wrap.has-prefix input {
  padding-left: 10px;
}

.input-wrap.has-suffix input {
  padding-right: 10px;
}

.input-affix {
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--color-text-secondary);
  flex-shrink: 0;
}

.input-prefix {
  padding: 0 10px;
  border-right: 1px solid var(--color-border);
}

.input-suffix {
  padding: 0;
  border-left: 1px solid var(--color-border);
}

.input-hints {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.input-error {
  margin: 0;
  font-size: 13px;
  color: var(--color-error-text);
}

.input-help {
  margin: 0;
  font-size: 13px;
  color: var(--color-text-muted);
}
</style>
