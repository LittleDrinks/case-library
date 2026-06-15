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
        <div class="rail-title">进度</div>
        <div class="rail-percent">{{ progressPercent }}% 完成</div>
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
          <div class="step-icon" aria-hidden="true">
            <svg v-if="idx < currentStep" viewBox="0 0 24 24">
              <polyline points="20 6 9 17 4 12"></polyline>
            </svg>
            <svg v-else-if="idx === currentStep" viewBox="0 0 24 24">
              <circle cx="12" cy="12" r="10"></circle>
            </svg>
            <svg v-else-if="step.id === 'basic'" viewBox="0 0 24 24">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
              <polyline points="14 2 14 8 20 8"></polyline>
            </svg>
            <svg v-else-if="step.id === 'content'" viewBox="0 0 24 24">
              <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"></path>
              <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"></path>
            </svg>
            <svg v-else-if="step.id === 'classify'" viewBox="0 0 24 24">
              <path d="M12 2 2 7l10 5 10-5-10-5z"></path>
              <path d="m2 17 10 5 10-5"></path>
              <path d="m2 12 10 5 10-5"></path>
            </svg>
            <svg v-else-if="step.id === 'review'" viewBox="0 0 24 24">
              <rect x="3" y="3" width="18" height="18" rx="2"></rect>
              <path d="M3 9h18"></path>
            </svg>
            <svg v-else viewBox="0 0 24 24">
              <polyline points="20 6 9 17 4 12"></polyline>
            </svg>
          </div>
          <div class="step-copy">
            <div class="step-label">{{ step.label }}</div>
            <div class="step-desc">{{ stepDescription(step.id) }}</div>
          </div>
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

function stepDescription(stepId) {
  const descriptions = {
    basic: "填写标题与作者",
    content: "撰写案例正文",
    classify: "选择学科分类",
    review: "智能内容审核",
    confirm: "确认并提交",
  };
  return descriptions[stepId] || "";
}
</script>

<style scoped>
.create-wizard-rail {
  display: contents;
}

/* 桌面端边栏 */
.wizard-rail {
  display: none;
  width: 260px;
  flex-shrink: 0;
  background: var(--color-surface);
  border-right: 1px solid var(--color-border);
}

.rail-header {
  padding: 32px 20px 24px;
}

.rail-title {
  margin-bottom: 8px;
  font-size: 12px;
  font-weight: 600;
  color: var(--color-text);
  letter-spacing: 0.5px;
}

.rail-percent {
  margin-top: 24px;
  font-size: 11px;
  font-weight: 400;
  color: var(--color-text-secondary);
}

.rail-progress-track {
  width: 100%;
  height: 4px;
  background: #f0f0f0;
  border-radius: 2px;
  overflow: hidden;
}

.rail-progress-bar {
  height: 100%;
  background: var(--color-brand);
  border-radius: 2px;
  transition: width 0.3s ease;
}

.rail-steps {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 0 20px 24px;
}

.rail-step {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  min-height: 0;
  padding: 12px;
  border-radius: 8px;
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
  top: 12px;
  bottom: 12px;
  width: 3px;
  border-radius: 0 2px 2px 0;
  background: var(--color-brand);
}

.rail-step.completed {
  color: var(--color-text);
}

.rail-step.future {
  color: #bbbbbb;
}

.step-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border-radius: 50%;
  flex-shrink: 0;
  color: currentColor;
  margin-top: 1px;
}

.step-icon svg {
  width: 12px;
  height: 12px;
  fill: none;
  stroke: currentColor;
  stroke-width: 2.5;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.rail-step.completed .step-icon {
  background: var(--color-brand);
  color: #fff;
  border-color: var(--color-brand);
}

.rail-step.active .step-icon {
  background: var(--color-brand-light);
  color: var(--color-brand);
  border: 1.5px solid var(--color-brand);
}

.rail-step.future .step-icon {
  background: #f5f5f5;
  color: #bbbbbb;
  border: 1.5px solid #e5e5e5;
}

.rail-step.future .step-icon svg {
  stroke-width: 2;
}

.step-copy {
  min-width: 0;
}

.step-label {
  font-size: 13px;
  font-weight: 500;
  line-height: 1.4;
}

.rail-step.active .step-label {
  font-weight: 600;
}

.step-desc {
  display: block;
  margin-top: 2px;
  font-size: 11px;
  color: var(--color-text-secondary);
}

.rail-step.future .step-desc {
  color: #cccccc;
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
  color: var(--color-success);
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
  background: var(--color-success);
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
