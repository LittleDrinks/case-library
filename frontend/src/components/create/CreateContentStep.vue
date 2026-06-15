<template>
  <div class="content-step">
    <div class="content-layout">
      <div class="content-editor-col">
        <div class="markdown-workspace">
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
                v-model="form.content"
                rows="14"
                placeholder="请在此撰写案例正文，建议包含以下内容。可使用 Markdown 语法，如 ## 标题：&#10;&#10;## 案例背景&#10;简述教学场景、课程名称、授课对象等基本信息。&#10;&#10;## 教学过程&#10;详细描述教学环节的设计与实施过程。&#10;&#10;## 思政元素融入&#10;阐述如何将思想政治教育有机融入专业教学。&#10;&#10;## 教学反思&#10;总结教学效果、经验与改进方向。"
                :aria-invalid="!!errors.content"
                @blur="$emit('touch', 'content')"
                @scroll="syncPreviewScroll"
              ></textarea>
            </div>
            <div class="textarea-meta">
              <span>{{ wordCount }} / 5000 字</span>
              <span>预计阅读 {{ readingTime }} 分钟</span>
            </div>
            <div v-if="errors.content" class="field-error" role="alert">{{ errors.content }}</div>
          </div>

          <section class="preview-field" aria-label="Markdown 预览">
            <div class="preview-field-label">Markdown 预览</div>
            <div class="markdown-preview">
            <div class="preview-header">
              <strong>预览</strong>
              <span>按当前正文实时生成</span>
            </div>
            <div
              v-if="form.content.trim()"
              ref="previewBody"
              class="preview-body"
              v-html="renderMarkdown(form.content)"
              @scroll="syncEditorScroll"
            ></div>
            <div v-else class="preview-empty">填写案例正文后，这里会显示排版预览。</div>
            </div>
          </section>
        </div>

        <div class="tip-card">
          <span class="tip-icon" aria-hidden="true"></span>
          <div>
            <div class="tip-title">写作小贴士</div>
            <div class="tip-text">
              优秀的思政案例应当叙事生动、逻辑清晰、价值导向明确。建议在撰写过程中注重真实性与典型性，善用具体数据和场景描写增强说服力。
            </div>
          </div>
        </div>

        <div class="field">
          <label for="ccf-source">来源材料</label>
          <div class="upload-zone" aria-hidden="true">
            <div class="upload-icon">↑</div>
            <div class="upload-title">上传或粘贴来源材料</div>
            <div class="upload-hint">可补充新闻链接、活动记录、访谈纪要或其他支撑材料</div>
          </div>
          <textarea
            id="ccf-source"
            v-model="form.source_material"
            rows="8"
            placeholder="可粘贴新闻链接、公众号正文、活动记录、访谈纪要或其他支撑材料。"
          ></textarea>
          <div class="field-help">来源材料会随版本快照保存，公开案例仅展示正文和来源材料，不展示审核批注。</div>
        </div>
      </div>

      <aside class="toc-panel" aria-label="正文目录">
        <div class="toc-title">目录</div>
        <div class="toc-list">
          <div v-if="tocItems.length === 0" class="toc-empty">
            在编辑器中使用 ## 标题 即可生成目录
          </div>
          <div v-for="item in tocItems" v-else :key="item" class="toc-item">
            {{ item }}
          </div>
        </div>
      </aside>
    </div>
  </div>
</template>

<script setup>
import { computed, ref } from "vue";

const props = defineProps({
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

const contentTextarea = ref(null);
const previewBody = ref(null);
let syncingScroll = false;

const tocItems = computed(() => {
  return String(props.form.content || "")
    .split(/\n+/)
    .map((line) => line.match(/^#{2,4}\s+(.+)$/)?.[1]?.trim())
    .filter(Boolean)
    .slice(0, 12);
});

function syncScroll(source, target) {
  if (!source || !target || syncingScroll) return;
  const sourceMax = source.scrollHeight - source.clientHeight;
  const targetMax = target.scrollHeight - target.clientHeight;
  const ratio = sourceMax > 0 ? source.scrollTop / sourceMax : 0;
  syncingScroll = true;
  target.scrollTop = targetMax > 0 ? ratio * targetMax : 0;
  requestAnimationFrame(() => {
    syncingScroll = false;
  });
}

function syncPreviewScroll() {
  syncScroll(contentTextarea.value, previewBody.value);
}

function syncEditorScroll() {
  syncScroll(previewBody.value, contentTextarea.value);
}

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

#ccf-source {
  border: 1px solid var(--color-border-strong);
  border-radius: 8px;
  min-height: 180px;
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

.textarea-meta {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  margin: 0 0 28px;
  font-size: 12px;
  color: var(--color-text-muted);
}

.markdown-workspace {
  display: grid;
  grid-template-columns: 1fr;
  gap: 20px;
  align-items: start;
  margin-bottom: 24px;
}

.content-field {
  min-width: 0;
  margin-bottom: 0;
}

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

.content-layout {
  display: grid;
  grid-template-columns: 1fr;
  gap: 0;
}

.content-editor-col {
  min-width: 0;
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

.upload-zone {
  border: 2px dashed var(--color-border-strong);
  border-radius: 8px;
  padding: 28px 24px;
  text-align: center;
  background: #fafafa;
  margin-bottom: 14px;
  color: var(--color-text-muted);
}

.upload-icon {
  width: 40px;
  height: 40px;
  margin: 0 auto 12px;
  display: grid;
  place-items: center;
  color: var(--color-text-muted);
  font-size: 26px;
  line-height: 1;
}

.upload-title {
  margin-bottom: 4px;
  font-size: 14px;
  font-weight: 500;
  color: var(--color-text);
}

.upload-hint {
  font-size: 12px;
  color: var(--color-text-muted);
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

.toc-panel {
  display: none;
}

.toc-title {
  margin-bottom: 12px;
  padding-left: 8px;
  font-size: 12px;
  font-weight: 600;
  color: var(--color-text-secondary);
  letter-spacing: 0.5px;
}

.toc-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.toc-item,
.toc-empty {
  padding: 5px 8px;
  border-radius: 4px;
  font-size: 12px;
  line-height: 1.5;
  color: var(--color-text-secondary);
}

.toc-item:first-child {
  color: var(--color-brand);
  font-weight: 500;
  background: var(--color-brand-light);
  border-left: 2px solid var(--color-brand);
}

.toc-empty {
  color: #cccccc;
  font-style: italic;
}

@media (min-width: 860px) {
  .editor-wrapper,
  .markdown-preview {
    height: 568px;
  }

  .editor-wrapper,
  .markdown-preview {
    display: flex;
    flex-direction: column;
  }

  #ccf-content {
    flex: 1;
    height: auto;
    min-height: 0;
    resize: none;
  }

  #ccf-source {
    min-height: 240px;
  }

  .markdown-workspace {
    grid-template-columns: minmax(0, 1fr) minmax(360px, 0.86fr);
    gap: 24px;
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

@media (min-width: 1200px) {
  .content-step {
    width: 100%;
  }

  .content-layout {
    grid-template-columns: minmax(0, 1fr) minmax(180px, 260px);
    gap: 28px;
  }

  .toc-panel {
    display: block;
    position: sticky;
    top: calc(var(--header-height) + 32px);
    align-self: start;
  }
}
</style>
