<template>
  <button
    :type="type"
    :disabled="disabled"
    class="base-button"
    :class="[`variant-${variant}`, `size-${size}`]"
    @click="$emit('click', $event)"
  >
    <span v-if="$slots.prefix" class="btn-prefix"><slot name="prefix" /></span>
    <span class="btn-content"><slot /></span>
    <span v-if="$slots.suffix" class="btn-suffix"><slot name="suffix" /></span>
  </button>
</template>

<script setup>
defineProps({
  variant: { type: String, default: 'primary' },
  size: { type: String, default: 'md' },
  type: { type: String, default: 'button' },
  disabled: { type: Boolean, default: false },
});

defineEmits(['click']);
</script>

<style scoped>
.base-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  border: 1px solid transparent;
  border-radius: 6px;
  font-family: var(--font-sans);
  font-weight: 600;
  line-height: 1.4;
  text-decoration: none;
  cursor: pointer;
  transition: background 0.15s, color 0.15s, border-color 0.15s, box-shadow 0.15s;
}

.base-button:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.variant-primary {
  background: var(--color-brand);
  border-color: var(--color-brand);
  color: #fff;
}

.variant-primary:hover:not(:disabled) {
  background: var(--color-brand-dark);
  border-color: var(--color-brand-dark);
}

.variant-secondary {
  background: var(--color-surface);
  border-color: var(--color-border-strong);
  color: var(--color-text-secondary);
}

.variant-secondary:hover:not(:disabled) {
  background: rgba(29, 35, 47, 0.04);
}

.variant-danger {
  background: #b91c1c;
  border-color: #b91c1c;
  color: #fff;
}

.variant-danger:hover:not(:disabled) {
  background: #991b1b;
  border-color: #991b1b;
}

.variant-ghost {
  background: transparent;
  border-color: transparent;
  color: var(--color-text-secondary);
}

.variant-ghost:hover:not(:disabled) {
  background: rgba(29, 35, 47, 0.04);
  color: var(--color-text);
}

.size-sm {
  padding: 6px 12px;
  font-size: 13px;
  min-height: 28px;
}

.size-md {
  padding: 8px 16px;
  font-size: 14px;
  min-height: 36px;
}

.size-lg {
  padding: 10px 20px;
  font-size: 15px;
  min-height: 40px;
}

.btn-prefix,
.btn-suffix {
  display: inline-flex;
  align-items: center;
}
</style>
