<template>
  <div class="ai-annotation-preview">
    <div class="annotation-copy">
      <div class="annotation-summary">
        <strong>版本正文</strong>
        <span>{{ state.comments?.length || 0 }} 条 AI 批注已附在对应段落下方</span>
      </div>
      <article
        v-for="paragraph in state.version.paragraphs"
        :key="paragraph.paragraph_id"
        :class="['annotation-paragraph', { highlighted: commentsForParagraph(paragraph.paragraph_id).length }]"
      >
        <p>
          <span>{{ paragraph.paragraph_id }}</span>
          {{ paragraph.text }}
        </p>
        <div
          v-for="comment in commentsForParagraph(paragraph.paragraph_id)"
          :key="comment.id || `${comment.paragraph_id}-${comment.message}`"
          class="inline-comment"
        >
          <strong>AI 批注</strong>
          <p>{{ comment.message }}</p>
          <small v-if="comment.suggestion">{{ comment.suggestion }}</small>
        </div>
      </article>
    </div>
  </div>
</template>

<script setup>
const props = defineProps({
  state: {
    type: Object,
    required: true,
  },
});

function commentsForParagraph(paragraphId) {
  return (props.state.comments || []).filter((comment) => comment.paragraph_id === paragraphId);
}
</script>

<style scoped>
.ai-annotation-preview {
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid var(--color-border);
}

.annotation-copy {
  display: grid;
  gap: 10px;
  min-width: 0;
  align-content: start;
}

.annotation-summary {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  color: var(--color-text-muted);
  font-size: 12px;
}

.annotation-summary strong {
  font-size: 12px;
  color: var(--color-text-muted);
  letter-spacing: 0;
}

.annotation-paragraph {
  margin: 0;
  padding: 13px 16px;
  border: 1px solid var(--color-border);
  border-radius: 6px;
  background: #fff;
  color: var(--color-text-secondary);
}

.annotation-paragraph p {
  margin: 0;
  line-height: 1.75;
  white-space: pre-wrap;
  word-break: break-word;
}

.annotation-paragraph.highlighted {
  border-color: rgba(141, 27, 53, 0.35);
  background: var(--color-brand-light);
  color: var(--color-text);
}

.annotation-copy span {
  display: inline-flex;
  margin-right: 6px;
  font-weight: 700;
  color: var(--color-brand);
}

.inline-comment {
  margin-top: 12px;
  padding: 12px 14px;
  border: 1px solid rgba(141, 27, 53, 0.22);
  border-left: 3px solid var(--color-brand);
  border-radius: 6px;
  background: #fff;
}

.inline-comment > strong {
  display: block;
  margin-bottom: 4px;
  font-size: 12px;
  color: var(--color-brand);
}

.inline-comment p,
.inline-comment small {
  display: block;
  margin: 0;
  color: var(--color-text-secondary);
  line-height: 1.6;
  word-break: break-word;
}

.inline-comment small {
  margin-top: 4px;
  color: var(--color-text-muted);
}

@media (max-width: 640px) {
  .annotation-summary {
    flex-direction: column;
    gap: 4px;
  }
}
</style>
