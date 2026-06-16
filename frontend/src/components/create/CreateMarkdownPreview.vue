<template>
  <section class="preview-field" aria-label="Markdown 预览">
    <div class="preview-field-label">Markdown 预览</div>
    <div class="markdown-preview">
      <div class="preview-header">
        <strong>预览</strong>
        <span>按当前正文实时生成</span>
      </div>
      <div
        v-if="content.trim()"
        ref="previewBody"
        class="preview-body"
        v-html="renderMarkdown(content)"
        @scroll="$emit('preview-scroll')"
      ></div>
      <div v-else ref="previewBody" class="preview-empty">填写案例正文后，这里会显示排版预览。</div>
    </div>
  </section>
</template>

<script setup>
import { ref } from "vue";

defineProps({
  content: {
    type: String,
    default: "",
  },
});

defineEmits(["preview-scroll"]);

const previewBody = ref(null);

function escapeHtml(value) {
  return String(value || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function renderInlineMarkdown(value) {
  return escapeHtml(value)
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/`([^`]+)`/g, "<code>$1</code>");
}

function renderMarkdown(value) {
  const lines = String(value || "").split(/\r?\n/);
  return lines.map((line) => {
    const trimmed = line.trim();
    if (!trimmed) return "<br>";
    const heading = trimmed.match(/^(#{1,4})\s+(.+)$/);
    if (heading) {
      const level = Math.min(4, heading[1].length + 2);
      return `<h${level}>${renderInlineMarkdown(heading[2])}</h${level}>`;
    }
    const ordered = trimmed.match(/^(\d+)\.\s+(.+)$/);
    if (ordered) {
      return `<p class="md-list-item">${ordered[1]}. ${renderInlineMarkdown(ordered[2])}</p>`;
    }
    const unordered = trimmed.match(/^[-*]\s+(.+)$/);
    if (unordered) {
      return `<p class="md-list-item">- ${renderInlineMarkdown(unordered[1])}</p>`;
    }
    const quote = trimmed.match(/^>\s*(.+)$/);
    if (quote) {
      return `<blockquote>${renderInlineMarkdown(quote[1])}</blockquote>`;
    }
    return `<p>${renderInlineMarkdown(line)}</p>`;
  }).join("");
}

defineExpose({
  previewBody,
  renderMarkdown,
});
</script>

<style scoped>
.preview-field {
  min-width: 0;
}

.preview-field-label {
  margin-bottom: 8px;
  min-height: 18px;
  font-size: 13px;
  font-weight: 500;
  color: var(--color-text);
}

.markdown-preview {
  min-width: 0;
  margin: 0;
  border: 1px solid var(--color-border);
  border-radius: 8px;
  background: var(--color-surface);
  overflow: hidden;
}

.preview-header {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--color-border);
  background: #fafafa;
}

.preview-header strong {
  font-size: 13px;
  color: var(--color-text);
}

.preview-header span {
  font-size: 12px;
  color: var(--color-text-muted);
}

.preview-body {
  padding: 18px 20px;
  max-height: 420px;
  overflow: auto;
  color: var(--color-text);
  font-size: 14px;
  line-height: 1.85;
}

.preview-body :deep(p),
.preview-body :deep(h3),
.preview-body :deep(h4),
.preview-body :deep(h5),
.preview-body :deep(h6) {
  margin: 0;
  word-break: break-word;
}

.preview-body :deep(p + p),
.preview-body :deep(p + h3),
.preview-body :deep(h3 + p),
.preview-body :deep(blockquote + p),
.preview-body :deep(p + blockquote) {
  margin-top: 10px;
}

.preview-body :deep(h3),
.preview-body :deep(h4),
.preview-body :deep(h5),
.preview-body :deep(h6) {
  font-size: 16px;
  font-weight: 800;
}

.preview-body :deep(.md-list-item) {
  padding-left: 16px;
}

.preview-body :deep(blockquote) {
  margin: 8px 0;
  padding: 8px 12px;
  border-left: 3px solid var(--color-brand);
  background: #fafafa;
  color: var(--color-text-secondary);
}

.preview-body :deep(code) {
  padding: 1px 4px;
  border-radius: 4px;
  background: #f3f4f6;
  font-family: inherit;
  font-size: 0.95em;
}

.preview-empty {
  padding: 24px 20px;
  color: var(--color-text-muted);
  font-size: 13px;
}

@media (min-width: 860px) {
  .markdown-preview {
    height: 568px;
    display: flex;
    flex-direction: column;
  }

  .preview-body,
  .preview-empty {
    flex: 1;
    max-height: none;
    min-height: 0;
    overflow: auto;
  }

  .preview-empty {
    display: flex;
    align-items: center;
  }
}
</style>
