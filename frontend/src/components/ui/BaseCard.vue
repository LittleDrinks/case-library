<template>
  <div
    class="base-card"
    :class="[{ hoverable }, `padding-${padding}`]"
  >
    <slot />
  </div>
</template>

<script setup>
defineProps({
  hoverable: { type: Boolean, default: false },
  padding: {
    type: String,
    default: 'md',
    validator: (v) => ['none', 'sm', 'md', 'lg'].includes(v),
  },
});
</script>

<style scoped>
.base-card {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 8px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  transition: box-shadow 0.15s, border-color 0.15s;
}

.base-card.hoverable:hover {
  box-shadow: 0 4px 16px rgba(29, 35, 47, 0.08);
  border-color: rgba(141, 27, 53, 0.25);
}

.padding-none {
  padding: 0;
}

.padding-sm {
  padding: 12px;
}

.padding-md {
  padding: 16px;
}

.padding-lg {
  padding: 20px;
}
</style>
