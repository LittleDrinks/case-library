<template>
  <article :class="['case-reader', { 'case-reader-compact': compact }]">
    <header v-if="title" class="case-reader-header">
      <h3>{{ title }}</h3>
    </header>
    <div class="case-reader-body" v-html="renderedContent"></div>
  </article>
</template>

<script setup>
import { computed } from 'vue';

const props = defineProps({
  content: {
    type: String,
    default: '',
  },
  title: {
    type: String,
    default: '',
  },
  emptyText: {
    type: String,
    default: '暂无内容',
  },
  compact: {
    type: Boolean,
    default: false,
  },
});

const displayContent = computed(() => {
  const normalized = String(props.content || '').replace(/\\n/g, '\n').trim();
  return normalized || props.emptyText;
});

const renderedContent = computed(() => renderMarkdown(displayContent.value));

function escapeHtml(value) {
  return String(value || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function renderInlineMarkdown(value) {
  return escapeHtml(value)
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/`([^`]+)`/g, '<code>$1</code>');
}

function renderMarkdown(value) {
  const lines = String(value || '').split(/\r?\n/);
  return lines.map((line) => {
    const trimmed = line.trim();
    if (!trimmed) return '<br>';
    const heading = trimmed.match(/^(#{1,4})\s+(.+)$/);
    if (heading) {
      const level = Math.min(4, heading[1].length + 2);
      return `<h${level}>${renderInlineMarkdown(heading[2])}</h${level}>`;
    }
    const orderedItem = trimmed.match(/^(\d+)\.\s+(.+)$/);
    if (orderedItem) {
      return `<p class="md-list-item"><span class="md-list-marker">${orderedItem[1]}.</span><span class="md-list-content">${renderInlineMarkdown(orderedItem[2])}</span></p>`;
    }
    const listItem = trimmed.match(/^[-*]\s+(.+)$/);
    if (listItem) {
      return `<p class="md-list-item"><span class="md-list-marker">-</span><span class="md-list-content">${renderInlineMarkdown(listItem[1])}</span></p>`;
    }
    const quote = trimmed.match(/^>\s*(.+)$/);
    if (quote) {
      return `<blockquote>${renderInlineMarkdown(quote[1])}</blockquote>`;
    }
    return `<p>${renderInlineMarkdown(line)}</p>`;
  }).join('');
}
</script>

<style scoped>
.case-reader {
  width: 100%;
  overflow: hidden;
  border: 1px solid var(--color-border);
  border-radius: 8px;
  background: var(--color-surface);
}

.case-reader-header {
  padding: 12px 18px;
  border-bottom: 1px solid var(--color-border);
  background: #fafafa;
}

.case-reader-header h3 {
  margin: 0;
  font-size: 15px;
  font-weight: 700;
  color: var(--color-text);
}

.case-reader-body {
  padding: 20px 22px;
  font-size: 15px;
  line-height: 1.85;
  color: var(--color-text);
  overflow-wrap: anywhere;
}

.case-reader-body :deep(p),
.case-reader-body :deep(h3),
.case-reader-body :deep(h4),
.case-reader-body :deep(h5),
.case-reader-body :deep(h6) {
  margin: 0;
  word-break: break-word;
}

.case-reader-body :deep(p + p),
.case-reader-body :deep(h3 + p),
.case-reader-body :deep(p + h3),
.case-reader-body :deep(h4 + p) {
  margin-top: 12px;
}

.case-reader-body :deep(h3),
.case-reader-body :deep(h4),
.case-reader-body :deep(h5),
.case-reader-body :deep(h6) {
  font-size: 16px;
  font-weight: 800;
}

.case-reader-body :deep(.md-list-item) {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  gap: 6px;
}

.case-reader-body :deep(.md-list-marker) {
  color: var(--color-text);
}

.case-reader-body :deep(.md-list-content) {
  min-width: 0;
}

.case-reader-body :deep(blockquote) {
  margin: 10px 0;
  padding: 8px 12px;
  border-left: 3px solid var(--color-brand);
  background: #fafafa;
  color: var(--color-text-secondary);
}

.case-reader-body :deep(code) {
  padding: 1px 4px;
  border-radius: 4px;
  background: #f3f4f6;
  font-family: inherit;
  font-size: 0.95em;
}

.case-reader-compact .case-reader-body {
  max-height: 360px;
  overflow: auto;
  font-size: 14px;
  line-height: 1.75;
}

@media (max-width: 640px) {
  .case-reader-body {
    padding: 16px;
    font-size: 14px;
  }
}
</style>
