<template>
  <div class="field content-field">
    <label for="ccf-content">
      案例正文 <span class="required" aria-hidden="true">*</span>
    </label>
    <div class="editor-wrapper">
      <div class="editor-toolbar" aria-hidden="true">
        <button type="button" class="toolbar-btn" title="加粗">B</button>
        <button type="button" class="toolbar-btn italic" title="斜体">I</button>
        <button type="button" class="toolbar-btn underline" title="下划线">U</button>
        <span class="toolbar-divider"></span>
        <button type="button" class="toolbar-btn" title="无序列表">•</button>
        <button type="button" class="toolbar-btn" title="有序列表">1.</button>
        <span class="toolbar-divider"></span>
        <button type="button" class="toolbar-btn" title="插入链接">
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"></path>
            <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"></path>
          </svg>
        </button>
      </div>
      <textarea
        id="ccf-content"
        ref="contentTextarea"
        :value="modelValue"
        rows="14"
        placeholder="请在此撰写案例正文，建议包含以下内容。可使用 Markdown 语法，如 ## 标题：&#10;&#10;## 案例背景&#10;简述教学场景、课程名称、授课对象等基本信息。&#10;&#10;## 教学过程&#10;详细描述教学环节的设计与实施过程。&#10;&#10;## 思政元素融入&#10;阐述如何将思想政治教育有机融入专业教学。&#10;&#10;## 教学反思&#10;总结教学效果、经验与改进方向。"
        :aria-invalid="!!error"
        @input="$emit('update:modelValue', $event.target.value)"
        @blur="$emit('touch', 'content')"
        @scroll="$emit('editor-scroll')"
      ></textarea>
    </div>
    <div class="textarea-meta">
      <span>{{ wordCount }} / 5000 字</span>
      <span>预计阅读 {{ readingTime }} 分钟</span>
    </div>
    <div v-if="error" class="field-error" role="alert">{{ error }}</div>
  </div>
</template>

<script setup>
import { ref } from "vue";

defineProps({
  modelValue: {
    type: String,
    default: "",
  },
  error: {
    type: String,
    default: "",
  },
  wordCount: {
    type: Number,
    default: 0,
  },
  readingTime: {
    type: Number,
    default: 1,
  },
});

defineEmits(["update:modelValue", "touch", "editor-scroll"]);

const contentTextarea = ref(null);

defineExpose({
  contentTextarea,
});
</script>

<style scoped>
.field {
  margin-bottom: 28px;
}

.field label {
  display: block;
  font-size: 13px;
  font-weight: 500;
  color: var(--color-text);
  margin-bottom: 8px;
}

.required {
  color: var(--color-brand);
  margin-left: 2px;
}

textarea {
  width: 100%;
  padding: 16px;
  border: 0;
  border-radius: 0;
  font-family: inherit;
  font-size: 14px;
  color: var(--color-text);
  background: var(--color-surface);
  outline: none;
  transition: border-color 0.15s, box-shadow 0.15s;
  min-height: 240px;
  resize: vertical;
  line-height: 1.8;
}

textarea::placeholder {
  color: #c8ced8;
}

textarea:focus {
  box-shadow: none;
}

#ccf-content {
  min-height: 320px;
}

.field-error {
  margin-top: 6px;
  font-size: 12px;
  color: var(--color-error-text);
  background: var(--color-error-bg);
  padding: 6px 8px;
  border-radius: 4px;
}

.textarea-meta {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  margin: 0 0 28px;
  font-size: 12px;
  color: var(--color-text-muted);
}

.content-field {
  min-width: 0;
  margin-bottom: 0;
}

.editor-wrapper {
  border: 1px solid var(--color-border-strong);
  border-radius: 8px;
  overflow: hidden;
  background: var(--color-surface);
  margin-bottom: 8px;
}

.editor-toolbar {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 8px 12px;
  background: #fafafa;
  border-bottom: 1px solid var(--color-border);
}

.toolbar-btn {
  width: 32px;
  height: 32px;
  display: grid;
  place-items: center;
  border: 0;
  border-radius: 4px;
  background: transparent;
  color: var(--color-text-secondary);
  font-size: 14px;
  font-weight: 700;
}

.toolbar-btn.italic {
  font-style: italic;
}

.toolbar-btn.underline {
  text-decoration: underline;
}

.toolbar-btn svg {
  width: 16px;
  height: 16px;
  fill: none;
  stroke: currentColor;
  stroke-width: 2.5;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.toolbar-divider {
  width: 1px;
  height: 20px;
  background: var(--color-border);
  margin: 0 4px;
}

@media (min-width: 860px) {
  .editor-wrapper {
    height: 568px;
    display: flex;
    flex-direction: column;
  }

  #ccf-content {
    flex: 1;
    height: auto;
    min-height: 0;
    resize: none;
  }
}
</style>
