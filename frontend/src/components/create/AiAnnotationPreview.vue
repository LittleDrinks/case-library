<template>
  <div class="ai-annotation-preview">
    <div class="annotation-copy">
      <strong>版本正文</strong>
      <p
        v-for="paragraph in state.version.paragraphs"
        :key="paragraph.paragraph_id"
        :class="{ highlighted: commentsForParagraph(paragraph.paragraph_id).length }"
      >
        <span>{{ paragraph.paragraph_id }}</span>
        {{ paragraph.text }}
      </p>
    </div>
    <aside class="annotation-comments" aria-label="AI 段落批注">
      <strong>AI 批注</strong>
      <div
        v-for="comment in state.comments"
        :key="comment.id || `${comment.paragraph_id}-${comment.message}`"
        class="annotation-comment"
      >
        <strong>{{ comment.paragraph_id }}</strong>
        <p>{{ comment.message }}</p>
        <small v-if="comment.suggestion">{{ comment.suggestion }}</small>
      </div>
    </aside>
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
  display: grid;
  grid-template-columns: 1fr;
  gap: 10px;
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid var(--color-border);
}

.annotation-copy,
.annotation-comments {
  display: grid;
  gap: 8px;
  min-width: 0;
  align-content: start;
}

.annotation-copy > strong,
.annotation-comments > strong {
  font-size: 12px;
  color: var(--color-text-muted);
  letter-spacing: 0;
}

.annotation-copy p {
  margin: 0;
  padding: 9px 10px;
  border: 1px solid var(--color-border);
  border-radius: 6px;
  color: var(--color-text-secondary);
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
}

.annotation-copy p.highlighted {
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

.annotation-comment {
  padding: 9px 10px;
  border: 1px solid rgba(141, 27, 53, 0.22);
  border-left: 3px solid var(--color-brand);
  border-radius: 6px;
  background: #fff;
  box-shadow: 0 8px 20px rgba(141, 27, 53, 0.06);
}

.annotation-comment > strong {
  display: block;
  margin-bottom: 4px;
  color: var(--color-brand);
}

.annotation-comment p,
.annotation-comment small {
  display: block;
  margin: 0;
  color: var(--color-text-secondary);
  line-height: 1.6;
  word-break: break-word;
}

.annotation-comment small {
  margin-top: 4px;
  color: var(--color-text-muted);
}

@media (min-width: 860px) {
  .ai-annotation-preview {
    grid-template-columns: minmax(0, 1fr) minmax(220px, 0.65fr);
  }
}
</style>
