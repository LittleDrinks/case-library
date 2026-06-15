<template>
  <span
    class="base-spinner"
    :class="`size-${size}`"
    role="status"
    aria-live="polite"
    :aria-label="label"
  >
    <span class="sr-only">{{ label }}</span>
  </span>
</template>

<script setup>
defineProps({
  size: { type: String, default: 'md' },
  label: { type: String, default: '加载中…' },
});
</script>

<style scoped>
.base-spinner {
  display: inline-block;
  border-radius: 50%;
  border-style: solid;
  border-color: var(--color-border);
  border-top-color: var(--color-brand);
  animation: spin 0.8s linear infinite;
  flex-shrink: 0;
}

.size-sm {
  width: 16px;
  height: 16px;
  border-width: 2px;
}

.size-md {
  width: 24px;
  height: 24px;
  border-width: 3px;
}

.size-lg {
  width: 32px;
  height: 32px;
  border-width: 3px;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}
</style>
