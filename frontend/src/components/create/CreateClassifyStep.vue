<template>
  <div class="classify-step">
    <div class="tag-section">
      <div class="tag-section-title">
        学科领域 <span class="required" aria-hidden="true">*</span>
      </div>
      <div class="tag-grid">
        <button
          v-for="(label, key) in constants.case_types"
          :key="key"
          type="button"
          :class="['tag-chip', { selected: form.type === key }]"
          :aria-pressed="form.type === key"
          @click="selectType(key)"
        >
          <span class="tag-checkbox" aria-hidden="true">
            <svg viewBox="0 0 24 24"><polyline points="20 6 9 17 4 12"></polyline></svg>
          </span>
          <span class="tag-label">{{ label }}</span>
        </button>
      </div>
      <div class="field-help">对应当前案例类型字段，用于案例在库中的展示分类与主要使用场景。</div>
      <div v-if="errors.type" class="field-error" role="alert">{{ errors.type }}</div>
    </div>

    <div class="tag-section">
      <div class="tag-section-title">
        思政主题 <span class="required" aria-hidden="true">*</span>
      </div>
      <div class="tag-grid">
        <button
          v-for="theme in constants.themes"
          :key="theme"
          type="button"
          :class="['tag-chip', { selected: form.theme === theme }]"
          :aria-pressed="form.theme === theme"
          @click="selectTheme(theme)"
        >
          <span class="tag-checkbox" aria-hidden="true">
            <svg viewBox="0 0 24 24"><polyline points="20 6 9 17 4 12"></polyline></svg>
          </span>
          <span class="tag-label">{{ theme }}</span>
        </button>
      </div>
      <div class="field-help">主题用于跨类型的关键词聚合与检索。</div>
      <div v-if="errors.theme" class="field-error" role="alert">{{ errors.theme }}</div>
    </div>

    <div class="tag-section">
      <div class="tag-section-title">适用学段</div>
      <div class="tag-grid compact">
        <span class="tag-chip readonly selected">
          <span class="tag-checkbox" aria-hidden="true">
            <svg viewBox="0 0 24 24"><polyline points="20 6 9 17 4 12"></polyline></svg>
          </span>
          <span class="tag-label">本科生</span>
        </span>
        <span class="tag-chip readonly">
          <span class="tag-checkbox" aria-hidden="true"></span>
          <span class="tag-label">硕士研究生</span>
        </span>
        <span class="tag-chip readonly">
          <span class="tag-checkbox" aria-hidden="true"></span>
          <span class="tag-label">博士研究生</span>
        </span>
      </div>
    </div>

    <div class="tip-card">
      <span class="tip-icon" aria-hidden="true"></span>
      <div>
        <div class="tip-title">分类小贴士</div>
        <div class="tip-text">
          建议选择一个案例类型和一个思政主题。分类越准确，越有助于后续审核、检索与推荐。
        </div>
      </div>
    </div>

  </div>
</template>

<script setup>
const props = defineProps({
  form: {
    type: Object,
    required: true,
  },
  errors: {
    type: Object,
    required: true,
  },
  constants: {
    type: Object,
    required: true,
  },
});

const emit = defineEmits(["touch"]);

function selectType(key) {
  props.form.type = key;
  emit("touch", "type");
}

function selectTheme(theme) {
  props.form.theme = theme;
  emit("touch", "theme");
}
</script>

<style scoped>
.tag-section {
  margin-bottom: 32px;
}

.tag-section-title {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 12px;
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text);
}

.required {
  color: var(--color-brand);
  margin-left: 2px;
}

.tag-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 12px;
}

.tag-chip {
  display: flex;
  align-items: center;
  gap: 10px;
  min-height: 48px;
  padding: 12px 14px;
  border: 1.5px solid var(--color-border-strong);
  border-radius: 8px;
  background: var(--color-surface);
  color: var(--color-text);
  text-align: left;
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s;
}

.tag-chip.readonly {
  cursor: default;
}

.tag-chip:hover,
.tag-chip.selected {
  border-color: var(--color-brand);
  background: var(--color-brand-light);
}

.tag-chip.readonly:not(.selected):hover {
  border-color: var(--color-border-strong);
  background: var(--color-surface);
}

.tag-checkbox {
  width: 18px;
  height: 18px;
  display: grid;
  place-items: center;
  border-radius: 50%;
  border: 1.5px solid #cccccc;
  flex-shrink: 0;
  transition: border-color 0.15s, background 0.15s;
}

.tag-checkbox svg {
  width: 10px;
  height: 10px;
  fill: none;
  stroke: #fff;
  stroke-width: 3;
  stroke-linecap: round;
  stroke-linejoin: round;
  opacity: 0;
}

.tag-chip.selected .tag-checkbox {
  background: var(--color-brand);
  border-color: var(--color-brand);
}

.tag-chip.selected .tag-checkbox svg {
  opacity: 1;
}

.tag-label {
  min-width: 0;
  font-size: 13px;
  line-height: 1.4;
}

.field-help {
  margin-top: 8px;
  font-size: 12px;
  color: var(--color-text-muted);
}

.field-error {
  margin-top: 6px;
  font-size: 12px;
  color: var(--color-error-text);
  background: var(--color-error-bg);
  padding: 6px 8px;
  border-radius: 4px;
}

.tip-card {
  display: flex;
  gap: 12px;
  padding: 16px 20px;
  border-radius: 8px;
  background: var(--color-brand-light);
  margin: 24px 0;
}

.tip-icon {
  width: 20px;
  height: 20px;
  border-radius: 50%;
  border: 2px solid currentColor;
  color: var(--color-brand);
  position: relative;
  flex-shrink: 0;
  margin-top: 2px;
}

.tip-icon::before {
  content: "i";
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  font-family: Georgia, serif;
  font-size: 12px;
  font-weight: 700;
  line-height: 1;
}

.tip-title {
  margin-bottom: 4px;
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text);
}

.tip-text {
  font-size: 12px;
  color: var(--color-text-secondary);
  line-height: 1.7;
}

@media (min-width: 700px) {
  .tag-grid {
    grid-template-columns: repeat(3, 1fr);
  }

  .tag-grid.compact {
    grid-template-columns: repeat(3, 1fr);
  }
}
</style>
