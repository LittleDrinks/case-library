<template>
  <div class="base-select">
    <label v-if="label" :for="inputId" class="select-label">{{ label }}</label>
    <div class="select-wrap" :class="{ 'has-error': error }">
      <select
        :id="inputId"
        :value="modelValue"
        :disabled="disabled"
        v-bind="$attrs"
        @change="$emit('update:modelValue', $event.target.value)"
      >
        <option v-if="placeholder" value="">{{ placeholder }}</option>
        <option
          v-for="opt in normalizedOptions"
          :key="opt.value"
          :value="opt.value"
        >
          {{ opt.label }}
        </option>
      </select>
    </div>
    <div v-if="error || helpText" class="select-hints">
      <p v-if="error" class="select-error">{{ error }}</p>
      <p v-if="helpText" class="select-help">{{ helpText }}</p>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue';

defineOptions({ inheritAttrs: false });

const props = defineProps({
  modelValue: { type: [String, Number], default: '' },
  id: { type: String, default: undefined },
  label: { type: String, default: '' },
  options: { type: Array, default: () => [] },
  placeholder: { type: String, default: '' },
  error: { type: String, default: '' },
  helpText: { type: String, default: '' },
  disabled: { type: Boolean, default: false },
});

defineEmits(['update:modelValue']);

const inputId = computed(() => props.id || `select-${Math.random().toString(36).slice(2, 9)}`);

const normalizedOptions = computed(() =>
  props.options.map((o) => (typeof o === 'string' ? { value: o, label: o } : o))
);
</script>

<style scoped>
.base-select {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.select-label {
  font-size: 14px;
  font-weight: 500;
  color: var(--color-text);
}

.select-wrap {
  position: relative;
}

.select-wrap select {
  width: 100%;
  padding: 10px 28px 10px 12px;
  border: 1px solid var(--color-border-strong);
  border-radius: 6px;
  font-family: inherit;
  font-size: 14px;
  color: var(--color-text);
  background: var(--color-surface);
  appearance: none;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'%3E%3Cpath fill='%234b5565' d='M6 8L1 3h10z'/%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: right 10px center;
  outline: none;
  transition: border-color 0.15s, box-shadow 0.15s;
  min-height: 40px;
}

.select-wrap select:focus {
  border-color: var(--color-brand);
  box-shadow: 0 0 0 3px var(--color-brand-light);
}

.select-wrap.has-error select {
  border-color: var(--color-error-text);
}

.select-wrap select:disabled {
  background: rgba(29, 35, 47, 0.03);
  cursor: not-allowed;
}

.select-hints {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.select-error {
  margin: 0;
  font-size: 13px;
  color: var(--color-error-text);
}

.select-help {
  margin: 0;
  font-size: 13px;
  color: var(--color-text-muted);
}
</style>
