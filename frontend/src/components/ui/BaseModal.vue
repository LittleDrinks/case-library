<template>
  <Teleport to="body">
    <Transition name="modal-fade">
      <div
        v-if="modelValue"
        class="modal-overlay"
        @click.self="onOverlayClick"
      >
        <div
          class="modal-panel"
          role="dialog"
          aria-modal="true"
          :aria-labelledby="hasHeader ? titleId : undefined"
        >
          <div v-if="hasHeader || showClose" class="modal-header">
            <slot name="header">
              <h3 v-if="title" :id="titleId">{{ title }}</h3>
            </slot>
            <button
              v-if="showClose"
              type="button"
              class="modal-close"
              aria-label="关闭"
              @click="close"
            >
              ×
            </button>
          </div>
          <div class="modal-body">
            <slot name="body" />
          </div>
          <div v-if="$slots.footer" class="modal-footer">
            <slot name="footer" />
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script>
let bodyLockCount = 0;
let originalBodyOverflow = '';

function lockBodyScroll() {
  if (typeof document === 'undefined') return;
  if (bodyLockCount === 0) {
    originalBodyOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
  }
  bodyLockCount += 1;
}

function unlockBodyScroll() {
  if (typeof document === 'undefined' || bodyLockCount === 0) return;
  bodyLockCount -= 1;
  if (bodyLockCount === 0) {
    document.body.style.overflow = originalBodyOverflow;
    originalBodyOverflow = '';
  }
}
</script>

<script setup>
import { computed, onBeforeUnmount, watch } from 'vue';

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  title: { type: String, default: '' },
  showClose: { type: Boolean, default: true },
  closeOnOverlay: { type: Boolean, default: true },
  closeOnEsc: { type: Boolean, default: true },
});

const emit = defineEmits(['update:modelValue', 'close']);

const titleId = `modal-title-${Math.random().toString(36).slice(2, 9)}`;
const hasHeader = computed(() => props.title || false);
let effectsApplied = false;

function close() {
  emit('update:modelValue', false);
  emit('close');
}

function onOverlayClick() {
  if (props.closeOnOverlay) {
    close();
  }
}

function onKeydown(event) {
  if (event.key === 'Escape' && props.modelValue && props.closeOnEsc) {
    close();
  }
}

function cleanupModalEffects() {
  if (typeof document === 'undefined') return;
  document.removeEventListener('keydown', onKeydown);
  if (effectsApplied) {
    unlockBodyScroll();
    effectsApplied = false;
  }
}

function applyModalEffects(open) {
  if (typeof document === 'undefined') return;
  cleanupModalEffects();
  if (open) {
    document.addEventListener('keydown', onKeydown);
    lockBodyScroll();
    effectsApplied = true;
  }
}

watch(
  () => props.modelValue,
  (open) => applyModalEffects(open),
  { immediate: true }
);

onBeforeUnmount(cleanupModalEffects);
</script>

<style scoped>
.modal-overlay {
  position: fixed;
  inset: 0;
  z-index: 200;
  background: rgba(0, 0, 0, 0.35);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 16px;
}

.modal-panel {
  width: 100%;
  max-width: 720px;
  max-height: calc(100vh - 32px);
  background: var(--color-surface);
  border-radius: 10px;
  box-shadow: 0 20px 50px rgba(0, 0, 0, 0.12);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid var(--color-border);
  flex-shrink: 0;
}

.modal-header h3 {
  margin: 0;
  font-size: 18px;
  font-weight: 700;
  color: var(--color-text);
  line-height: 1.4;
  padding-right: 16px;
}

.modal-close {
  background: transparent;
  border: 0;
  font-size: 22px;
  line-height: 1;
  color: var(--color-text-muted);
  cursor: pointer;
  flex-shrink: 0;
}

.modal-close:hover {
  color: var(--color-text);
}

.modal-body {
  padding: 20px;
  overflow-y: auto;
  flex: 1;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  padding: 14px 20px;
  border-top: 1px solid var(--color-border);
  flex-shrink: 0;
  flex-wrap: wrap;
}

.modal-fade-enter-active,
.modal-fade-leave-active {
  transition: opacity 0.2s;
}

.modal-fade-enter-from,
.modal-fade-leave-to {
  opacity: 0;
}
</style>
