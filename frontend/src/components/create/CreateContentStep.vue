<template>
  <div class="content-step">
    <div class="content-layout">
      <div class="content-editor-col">
        <div class="markdown-workspace">
          <CreateContentEditor
            ref="contentEditor"
            v-model="form.content"
            :error="errors.content"
            :word-count="wordCount"
            :reading-time="readingTime"
            @touch="$emit('touch', $event)"
            @editor-scroll="syncPreviewScroll"
          />

          <CreateMarkdownPreview
            ref="markdownPreview"
            :content="form.content"
            @preview-scroll="syncEditorScroll"
          />
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
import CreateContentEditor from "./CreateContentEditor.vue";
import CreateMarkdownPreview from "./CreateMarkdownPreview.vue";

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

const contentEditor = ref(null);
const markdownPreview = ref(null);
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
  syncScroll(contentEditor.value?.contentTextarea, markdownPreview.value?.previewBody);
}

function syncEditorScroll() {
  syncScroll(markdownPreview.value?.previewBody, contentEditor.value?.contentTextarea);
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

.markdown-workspace {
  display: grid;
  grid-template-columns: 1fr;
  gap: 20px;
  align-items: start;
  margin-bottom: 24px;
}

.content-layout {
  display: grid;
  grid-template-columns: 1fr;
  gap: 0;
}

.content-editor-col {
  min-width: 0;
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
  #ccf-source {
    min-height: 240px;
  }

  .markdown-workspace {
    grid-template-columns: minmax(0, 1fr) minmax(360px, 0.86fr);
    gap: 24px;
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
