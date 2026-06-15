<template>
  <div class="empty-state" :class="`variant-${variant}`">
    <div class="empty-icon">
      <slot name="icon">
        <BaseSpinner v-if="variant === 'loading'" :size="spinnerSize" />
        <span v-else-if="variant === 'error'" class="icon-default" aria-hidden="true">⚠</span>
        <span v-else class="icon-default" aria-hidden="true">🗂</span>
      </slot>
    </div>
    <h3 v-if="displayTitle" class="empty-title">{{ displayTitle }}</h3>
    <p v-if="displayMessage" class="empty-message">{{ displayMessage }}</p>
    <div v-if="$slots.action" class="empty-action">
      <slot name="action" />
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue';
import BaseSpinner from './BaseSpinner.vue';

const props = defineProps({
  variant: { type: String, default: 'empty' },
  title: { type: String, default: '' },
  message: { type: String, default: '' },
  spinnerSize: { type: String, default: 'lg' },
});

const defaultTitles = {
  loading: '加载中…',
  error: '加载失败',
  empty: '暂无数据',
};

const defaultMessages = {
  loading: '请稍候',
  error: '请稍后重试',
  empty: '当前条件下没有找到内容',
};

const displayTitle = computed(() => props.title || defaultTitles[props.variant]);
const displayMessage = computed(() => props.message || defaultMessages[props.variant]);
</script>

<style scoped>
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 56px 24px;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 8px;
  text-align: center;
}

.empty-title {
  margin: 0;
  font-size: 18px;
  font-weight: 700;
  color: var(--color-text);
}

.empty-message {
  margin: 0;
  font-size: 14px;
  color: var(--color-text-secondary);
}

.empty-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--color-text-secondary);
  font-size: 24px;
}

.empty-action {
  margin-top: 4px;
}

.icon-default {
  line-height: 1;
}
</style>
