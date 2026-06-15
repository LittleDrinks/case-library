<template>
  <div class="classify-step">
    <div class="hint-banner">
      <span class="hint-icon" aria-hidden="true"></span>
      <span>不确定分类？可点击右下角 AI 助手，根据已填写内容获取一次本地建议。</span>
    </div>

    <div class="field">
      <label for="ccf-type">
        案例类型 <span class="required" aria-hidden="true">*</span>
      </label>
      <select
        id="ccf-type"
        v-model="form.type"
        :aria-invalid="!!errors.type"
        @change="$emit('touch', 'type')"
      >
        <option disabled value="">请选择案例类型</option>
        <option v-for="(label, key) in constants.case_types" :key="key" :value="key">
          {{ label }}
        </option>
      </select>
      <div class="field-help">类型决定案例在库中的展示分类与主要使用场景。</div>
      <div v-if="errors.type" class="field-error" role="alert">{{ errors.type }}</div>
    </div>

    <div class="field">
      <label for="ccf-theme">
        案例主题 <span class="required" aria-hidden="true">*</span>
      </label>
      <select
        id="ccf-theme"
        v-model="form.theme"
        :aria-invalid="!!errors.theme"
        @change="$emit('touch', 'theme')"
      >
        <option disabled value="">请选择案例主题</option>
        <option v-for="t in constants.themes" :key="t" :value="t">{{ t }}</option>
      </select>
      <div class="field-help">主题用于跨类型的关键词聚合与检索。</div>
      <div v-if="errors.theme" class="field-error" role="alert">{{ errors.theme }}</div>
    </div>

    <!-- Transient local helper panel -->
    <div
      v-if="showHelper"
      class="helper-panel"
      role="dialog"
      aria-modal="true"
      aria-labelledby="helper-title"
    >
      <div class="helper-header">
        <span id="helper-title">AI 分类助手（本地建议）</span>
        <button
          type="button"
          class="helper-close-btn"
          aria-label="关闭"
          @click="showHelper = false"
        >
          ×
        </button>
      </div>
      <div class="helper-body">
        <p class="helper-desc">请输入您想咨询的问题，例如：“帮我推荐案例类型和主题”。</p>
        <input v-model="helperInput" type="text" placeholder="输入问题…" @keyup.enter="runHelper" />
        <button
          type="button"
          class="btn-helper"
          :disabled="!helperInput.trim()"
          @click="runHelper"
        >
          获取建议
        </button>
        <div v-if="helperResponse" class="helper-response" role="status" aria-live="polite">
          {{ helperResponse }}
        </div>
      </div>
    </div>

    <button
      type="button"
      class="fab-helper"
      aria-label="打开 AI 分类助手"
      @click="showHelper = true"
    >
      <span class="helper-label-desktop">AI</span>
      <span class="helper-label-mobile">AI 建议</span>
    </button>
  </div>
</template>

<script setup>
import { ref } from "vue";

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

defineEmits(["touch"]);

const showHelper = ref(false);
const helperInput = ref("");
const helperResponse = ref("");

function runHelper() {
  const q = helperInput.value.trim();
  if (!q) return;
  const text = (props.form.title + " " + props.form.content).toLowerCase();
  let type = "TYPE_A";
  let theme = "铸魂育人";
  if (text.includes("课程") || text.includes("教学")) type = "TYPE_A";
  if (text.includes("共享") || text.includes("资源")) type = "TYPE_B";
  if (text.includes("实践") || text.includes("活动") || text.includes("社会")) type = "TYPE_C";
  if (text.includes("强国")) theme = "强国建设";
  else if (text.includes("实践") || text.includes("育人")) theme = "实践育人";
  else if (text.includes("数字") || text.includes("技术") || text.includes("网络")) theme = "数字赋能";
  const typeLabel = props.constants.case_types[type] || type;
  helperResponse.value = `根据当前内容，建议类型为「${typeLabel}」，主题选择「${theme}」。您也可以结合自身判断手动调整。`;
}
</script>

<style scoped>
.field {
  margin-bottom: 18px;
}

.field label {
  display: block;
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text);
  margin-bottom: 6px;
}

.required {
  color: var(--color-brand);
  margin-left: 2px;
}

select {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid var(--color-border-strong);
  border-radius: 4px;
  font-family: inherit;
  font-size: 14px;
  color: var(--color-text);
  background: var(--color-surface);
  outline: none;
  transition: border-color 0.15s, box-shadow 0.15s;
}

select:focus {
  border-color: var(--color-brand);
  box-shadow: 0 0 0 3px var(--color-brand-light);
}

.field-help {
  margin-top: 4px;
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

.hint-banner {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 14px;
  background: #fefce8;
  border: 1px solid #fde047;
  border-radius: 6px;
  margin-bottom: 18px;
  font-size: 13px;
  color: #713f12;
}

.hint-icon {
  width: 18px;
  height: 18px;
  border-radius: 50%;
  border: 2px solid currentColor;
  position: relative;
  flex-shrink: 0;
}

.hint-icon::before,
.hint-icon::after {
  content: "";
  position: absolute;
  background: currentColor;
  border-radius: 1px;
}

.hint-icon::before {
  left: 7px;
  top: 3px;
  width: 2px;
  height: 8px;
}

.hint-icon::after {
  left: 7px;
  top: 12px;
  width: 2px;
  height: 2px;
}

.helper-panel {
  position: fixed;
  right: 16px;
  bottom: 80px;
  width: min(92vw, 360px);
  background: var(--color-surface);
  border: 1px solid var(--color-border-strong);
  border-radius: 10px;
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.08);
  z-index: 110;
}

.helper-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 14px;
  border-bottom: 1px solid var(--color-border);
  font-size: 13px;
  font-weight: 700;
  color: var(--color-text);
}

.helper-close-btn {
  background: transparent;
  border: 0;
  font-size: 20px;
  line-height: 1;
  color: var(--color-text-muted);
  cursor: pointer;
}

.helper-body {
  padding: 14px;
}

.helper-desc {
  margin: 0 0 10px;
  font-size: 12px;
  color: var(--color-text-secondary);
}

.helper-body input[type="text"] {
  width: 100%;
  padding: 10px 12px;
  margin-bottom: 10px;
  border: 1px solid var(--color-border-strong);
  border-radius: 4px;
  font-family: inherit;
  font-size: 14px;
  color: var(--color-text);
  background: var(--color-surface);
  outline: none;
}

.btn-helper {
  width: 100%;
  padding: 10px;
  border: 1px solid var(--color-brand);
  border-radius: 6px;
  background: var(--color-brand);
  color: #fff;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
}

.btn-helper:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.helper-response {
  margin-top: 10px;
  padding: 10px;
  background: #f6f7f9;
  border-radius: 6px;
  font-size: 13px;
  color: var(--color-text);
  line-height: 1.5;
}

.fab-helper {
  position: fixed;
  right: 16px;
  bottom: 24px;
  width: 48px;
  height: 48px;
  border-radius: 8px;
  background: var(--color-brand);
  color: #fff;
  border: 0;
  font-size: 20px;
  cursor: pointer;
  box-shadow: 0 6px 16px rgba(141, 27, 53, 0.25);
  z-index: 105;
}

.helper-label-mobile {
  display: none;
}

@media (max-width: 859px) {
  .fab-helper {
    position: static;
    display: flex;
    align-items: center;
    justify-content: center;
    margin: 12px 0 0 auto;
    width: auto;
    min-width: 88px;
    height: 38px;
    padding: 0 14px;
    border: 1px solid rgba(141, 27, 53, 0.22);
    background: var(--color-brand-light);
    color: var(--color-brand);
    font-size: 14px;
    font-weight: 700;
    border-radius: 7px;
    box-shadow: none;
  }

  .helper-label-desktop {
    display: none;
  }

  .helper-label-mobile {
    display: inline;
  }
}
</style>
