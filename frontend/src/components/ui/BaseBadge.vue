<template>
  <span class="base-badge" :class="[`variant-${variant}`, `shape-${shape}`]">
    <slot />
  </span>
</template>

<script setup>
defineProps({
  variant: { type: String, default: 'brand' },
  shape: {
    type: String,
    default: 'square',
    validator: (v) => ['square', 'pill'].includes(v),
  },
});
</script>

<style scoped>
.base-badge {
  display: inline-flex;
  align-items: center;
  font-size: 12px;
  font-weight: 600;
  line-height: 1;
}

.variant-brand {
  color: var(--color-brand);
  background: var(--color-brand-light);
}

.variant-secondary {
  color: var(--color-text-secondary);
  background: #f3f4f6;
}

.variant-success {
  color: #166534;
  background: #dcfce7;
}

.variant-danger {
  color: #991b1b;
  background: #fecaca;
}

.shape-square {
  padding: 3px 10px;
  border-radius: 4px;
}

.shape-pill {
  padding: 3px 10px;
  border-radius: 999px;
}
</style>
