<template>
  <div class="create-wizard-rail">
    <!-- 移动端步骤摘要 -->
    <div class="wizard-rail-mobile">
      <div class="mobile-progress-header">
        <span class="mobile-progress-title">进度</span>
        <span class="mobile-progress-percent">{{ progressPercent }}% 完成</span>
      </div>
      <div class="mobile-progress-bar-track">
        <div class="mobile-progress-bar" :style="{ width: progressPercent + '%' }"></div>
      </div>
      <div class="mobile-steps">
        <div
          v-for="(step, idx) in steps"
          :key="step.id"
          :class="[
            'mobile-step',
            { active: idx === currentStep, completed: idx < currentStep },
          ]"
        >
          <span class="mobile-step-dot" aria-hidden="true">
            <span v-if="idx >= currentStep">{{ idx + 1 }}</span>
          </span>
          <span class="mobile-step-label">{{ step.label }}</span>
        </div>
      </div>
    </div>

    <!-- 桌面端进度边栏 -->
    <aside class="wizard-rail">
      <div class="rail-header">
        <div class="rail-header-top">
          <div class="rail-title">进度</div>
          <div class="rail-percent">{{ progressPercent }}% 完成</div>
        </div>
        <div class="rail-progress-track">
          <div class="rail-progress-bar" :style="{ width: progressPercent + '%' }"></div>
        </div>
      </div>
      <nav class="rail-steps" aria-label="创建步骤">
        <div
          v-for="(step, idx) in steps"
          :key="step.id"
          :class="[
            'rail-step',
            { active: idx === currentStep, completed: idx < currentStep, future: idx > currentStep },
          ]"
        >
          <div class="rail-step-left">
            <div class="step-icon" aria-hidden="true">
              <svg v-if="step.id === 'basic'" viewBox="0 0 24 24" width="18" height="18">
                <path fill="currentColor" d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
                <polyline points="14 2 14 8 20 8" fill="none" stroke="currentColor" stroke-width="2"></polyline>
              </svg>
              <svg v-else-if="step.id === 'content'" viewBox="0 0 24 24" width="18" height="18">
                <path fill="currentColor" d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"></path>
                <path fill="currentColor" d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"></path>
              </svg>
              <svg v-else-if="step.id === 'classify'" viewBox="0 0 24 24" width="18" height="18">
                <path fill="currentColor" d="M12 2l-9 4.5v6L3 13l9 4.5L21 13l-0-0.5v-6L12 2z"></path>
                <path fill="currentColor" d="M12 22l-9-4.5v-3l9 4.5 9-4.5v3L12 22z"></path>
              </svg>
              <svg v-else-if="step.id === 'review'" viewBox="0 0 24 24" width="18" height="18">
                <path fill="currentColor" d="M12 22c5.523 0 10-4.477 10-10S17.523 2 12 2 2 6.477 2 12s4.477 10 10 10z"></path>
                <path fill="none" stroke="#fff" stroke-width="2" d="M9 12l2 2 4-4"></path>
              </svg>
              <svg v-else viewBox="0 0 24 24" width="18" height="18">
                <path fill="currentColor" d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path>
                <polyline points="22 4 12 14.01 9 11.01" fill="none" stroke="currentColor" stroke-width="2"></polyline>
              </svg>
            </div>
            <div class="step-marker" aria-hidden="true">
              <span v-if="idx >= currentStep">{{ idx + 1 }}</span>
            </div>
          </div>
          <div class="step-label">{{ step.label }}</div>
        </div>
      </nav>
    </aside>
  </div>
</template>

<script setup>
/**
 * 创建向导步骤轨道
 *
 * 同时渲染移动端摘要条和桌面端左侧边栏，仅依赖步骤元数据与当前步骤索引，
 * 不包含任何业务逻辑或状态变更。
 */
defineProps({
  steps: {
    type: Array,
    required: true,
  },
  currentStep: {
    type: Number,
    required: true,
  },
  progressPercent: {
    type: Number,
    required: true,
  },
});
</script>

<style scoped>
.create-wizard-rail {
  display: contents;
}

/* 桌面端边栏 */
.wizard-rail {
  display: none;
  width: 280px;
  flex-shrink: 0;
  background: var(--color-surface);
  border-right: 1px solid var(--color-border);
}

.rail-header {
  padding: 24px;
  border-bottom: 1px solid var(--color-border);
}

.rail-header-top {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  margin-bottom: 12px;
}

.rail-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text-secondary);
}

.rail-percent {
  font-size: 20px;
  font-weight: 700;
  color: #16a34a;
}

.rail-progress-track {
  height: 6px;
  background: #e5e7eb;
  border-radius: 3px;
  overflow: hidden;
}

.rail-progress-bar {
  height: 100%;
  background: #16a34a;
  border-radius: 3px;
  transition: width 0.3s ease;
}

.rail-steps {
  padding: 8px 0 24px;
}

.rail-step {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 20px;
  position: relative;
  color: var(--color-text-secondary);
}

.rail-step.active {
  background: var(--color-brand-light);
  color: var(--color-brand);
}

.rail-step.active::before {
  content: "";
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 4px;
  background: var(--color-brand);
  border-radius: 0 2px 2px 0;
}

.rail-step.completed {
  color: var(--color-text);
}

.rail-step.future {
  color: var(--color-text-muted);
}

.rail-step-left {
  display: flex;
  align-items: center;
  gap: 10px;
}

.step-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
}

.step-marker {
  width: 22px;
  height: 22px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  font-size: 12px;
  font-weight: 700;
  border: 2px solid currentColor;
}

.rail-step.completed .step-marker {
  position: relative;
  background: var(--color-brand);
  color: #fff;
  border-color: var(--color-brand);
}

.rail-step.completed .step-marker::before {
  content: "";
  width: 8px;
  height: 4px;
  border-left: 2px solid currentColor;
  border-bottom: 2px solid currentColor;
  transform: rotate(-45deg) translate(1px, -1px);
}

.rail-step.future .step-marker {
  border-color: var(--color-text-muted);
  color: var(--color-text-muted);
}

.step-label {
  font-size: 14px;
  font-weight: 500;
}

.rail-step.active .step-label {
  font-weight: 600;
}

/* 移动端摘要条 */
.wizard-rail-mobile {
  display: block;
  background: var(--color-surface);
  border-bottom: 1px solid var(--color-border);
  padding: 16px;
}

.mobile-progress-header {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  margin-bottom: 8px;
}

.mobile-progress-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text-secondary);
}

.mobile-progress-percent {
  font-size: 15px;
  font-weight: 700;
  color: #16a34a;
}

.mobile-progress-bar-track {
  height: 6px;
  background: #e5e7eb;
  border-radius: 3px;
  overflow: hidden;
  margin-bottom: 10px;
}

.mobile-progress-bar {
  height: 100%;
  background: #16a34a;
  border-radius: 3px;
  transition: width 0.3s ease;
}

.mobile-steps {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 4px;
}

.mobile-step {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  color: var(--color-text-muted);
  flex: 1;
  min-width: 0;
}

.mobile-step.active {
  color: var(--color-brand);
}

.mobile-step.completed {
  color: var(--color-brand);
}

.mobile-step-dot {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  border: 2px solid currentColor;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  font-weight: 700;
  flex-shrink: 0;
}

.mobile-step.completed .mobile-step-dot {
  position: relative;
  background: var(--color-brand);
  color: #fff;
  border-color: var(--color-brand);
}

.mobile-step.completed .mobile-step-dot::before {
  content: "";
  width: 8px;
  height: 4px;
  border-left: 2px solid currentColor;
  border-bottom: 2px solid currentColor;
  transform: rotate(-45deg) translate(1px, -1px);
}

.mobile-step-label {
  font-size: 11px;
  text-align: center;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 100%;
}

@media (min-width: 860px) {
  .wizard-rail {
    display: block;
  }

  .wizard-rail-mobile {
    display: none;
  }
}
</style>
