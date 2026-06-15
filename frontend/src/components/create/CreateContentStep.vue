<template>
  <div class="content-step">
    <div class="field">
      <label for="ccf-content">
        案例正文 <span class="required" aria-hidden="true">*</span>
      </label>
      <textarea
        id="ccf-content"
        v-model="form.content"
        rows="14"
        placeholder="请使用 Markdown 格式编写案例正文，建议包含背景、问题、分析、反思等部分。"
        :aria-invalid="!!errors.content"
        @blur="$emit('touch', 'content')"
      ></textarea>
      <div class="textarea-meta">
        <span>字数 {{ wordCount }}</span>
        <span>预计阅读 {{ readingTime }} 分钟</span>
      </div>
      <div v-if="errors.content" class="field-error" role="alert">{{ errors.content }}</div>
    </div>

    <div class="field">
      <label for="ccf-source">来源材料</label>
      <textarea
        id="ccf-source"
        v-model="form.source_material"
        rows="8"
        placeholder="可粘贴新闻链接、公众号正文、活动记录、访谈纪要或其他支撑材料。"
      ></textarea>
      <div class="field-help">来源材料会随版本快照保存，公开案例仅展示正文和来源材料，不展示审核批注。</div>
    </div>
  </div>
</template>

<script setup>
defineProps({
  form: {
    type: Object,
    required: true,
  },
  errors: {
    type: Object,
    required: true,
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

defineEmits(["touch"]);
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

textarea {
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
  min-height: 240px;
  resize: vertical;
  line-height: 1.6;
}

textarea:focus {
  border-color: var(--color-brand);
  box-shadow: 0 0 0 3px var(--color-brand-light);
}

#ccf-content {
  min-height: 280px;
}

#ccf-source {
  min-height: 180px;
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

.textarea-meta {
  display: flex;
  justify-content: space-between;
  margin-top: 6px;
  font-size: 12px;
  color: var(--color-text-muted);
}

@media (min-width: 860px) {
  #ccf-content {
    min-height: 380px;
  }

  #ccf-source {
    min-height: 240px;
  }
}
</style>
