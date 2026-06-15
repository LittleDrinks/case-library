<template>
  <div class="review-step">
    <div class="review-header">
      <span class="review-badge">AI 自查</span>
      <span class="review-percent">{{ aiReviewProgress }}% 已完成</span>
    </div>
    <div class="review-progress-track">
      <div class="review-progress-bar" :style="{ width: aiReviewProgress + '%' }"></div>
    </div>
    <p class="review-note">
      以下结果来自后端 AI 自查接口，仅作为作者提交前参考，不代表专家审核结论。
    </p>

    <div v-if="aiPromptLoadError" class="ai-unavailable-banner" role="status">
      {{ aiPromptLoadError }}
    </div>

    <div class="ai-review-toolbar">
      <button
        type="button"
        class="btn-primary"
        :disabled="aiRunningAll || !canRunAiReview"
        @click="$emit('run-all')"
      >
        {{ aiRunningAll ? "生成中…" : "生成只读审核版本" }}
      </button>
      <span class="ai-toolbar-note">
        需要先填写标题、正文、类型和主题。AI 会生成段落级批注版本，不会给出审批结论。
      </span>
    </div>

    <div class="review-grid">
      <div v-for="item in aiReviewItems" :key="item.id" class="review-card ai-review-card">
        <div class="review-card-top">
          <div>
            <div class="review-card-title">{{ item.name }}</div>
            <div class="review-card-desc">{{ item.description }}</div>
          </div>
          <span class="ai-status-pill" :class="aiReviewState[item.id].status">
            {{ aiStatusLabel(aiReviewState[item.id].status) }}
          </span>
        </div>

        <div v-if="aiReviewState[item.id].status === 'idle'" class="ai-placeholder">
          尚未运行。点击下方按钮获取作者侧自查建议。
        </div>

        <div v-else-if="aiReviewState[item.id].status === 'loading'" class="ai-placeholder">
          正在请求后端 AI 自查…
        </div>

        <div v-else-if="aiReviewState[item.id].status === 'error'" class="ai-error">
          {{ aiReviewState[item.id].error }}
        </div>

        <div v-else class="ai-result">
          <div v-if="aiReviewState[item.id].parsed" class="ai-result-body">
            <div v-if="aiReviewState[item.id].parsed.detail" class="ai-detail">
              {{ aiReviewState[item.id].parsed.detail }}
            </div>
            <div v-if="aiReviewState[item.id].parsed.score != null" class="ai-score">
              评分 {{ aiReviewState[item.id].parsed.score }}
            </div>
            <ul
              v-if="
                Array.isArray(aiReviewState[item.id].parsed.suggestions) &&
                aiReviewState[item.id].parsed.suggestions.length
              "
              class="ai-suggestions"
            >
              <li v-for="suggestion in aiReviewState[item.id].parsed.suggestions" :key="suggestion">
                {{ suggestion }}
              </li>
            </ul>
            <ul
              v-if="
                Array.isArray(aiReviewState[item.id].comments) &&
                aiReviewState[item.id].comments.length &&
                !hasAnnotationPreview(aiReviewState[item.id])
              "
              class="ai-suggestions"
            >
              <li v-for="comment in aiReviewState[item.id].comments" :key="comment.id || comment.message">
                {{ comment.paragraph_id }}：{{ comment.message }}
              </li>
            </ul>
            <div v-if="hasAnnotationPreview(aiReviewState[item.id])" class="ai-annotation-preview">
              <div class="annotation-copy">
                <strong>版本正文</strong>
                <p
                  v-for="paragraph in aiReviewState[item.id].version.paragraphs"
                  :key="paragraph.paragraph_id"
                  :class="{
                    highlighted: commentsForParagraph(aiReviewState[item.id], paragraph.paragraph_id).length,
                  }"
                >
                  <span>{{ paragraph.paragraph_id }}</span>
                  {{ paragraph.text }}
                </p>
              </div>
              <aside class="annotation-comments" aria-label="AI 段落批注">
                <strong>AI 批注</strong>
                <div
                  v-for="comment in aiReviewState[item.id].comments"
                  :key="comment.id || `${comment.paragraph_id}-${comment.message}`"
                  class="annotation-comment"
                >
                  <strong>{{ comment.paragraph_id }}</strong>
                  <p>{{ comment.message }}</p>
                  <small v-if="comment.suggestion">{{ comment.suggestion }}</small>
                </div>
              </aside>
            </div>
          </div>
          <pre v-else class="ai-answer">{{ aiReviewState[item.id].answer }}</pre>
          <div v-if="aiReviewState[item.id].parse_error" class="ai-parse-warning">
            {{ aiReviewState[item.id].parse_error }}
          </div>
        </div>

        <button
          type="button"
          class="btn-secondary ai-run-btn"
          :disabled="aiReviewState[item.id].status === 'loading' || !canRunAiReview"
          @click="$emit('run-item', item.id)"
        >
          {{ aiReviewState[item.id].status === "loading" ? "运行中…" : "运行此项" }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
defineProps({
  aiReviewItems: {
    type: Array,
    required: true,
  },
  aiReviewState: {
    type: Object,
    required: true,
  },
  aiPromptLoadError: {
    type: String,
    default: "",
  },
  aiRunningAll: {
    type: Boolean,
    default: false,
  },
  canRunAiReview: {
    type: Boolean,
    default: false,
  },
  aiReviewProgress: {
    type: Number,
    default: 0,
  },
});

defineEmits(["run-all", "run-item"]);

function commentsForParagraph(state, paragraphId) {
  return (state.comments || []).filter((comment) => comment.paragraph_id === paragraphId);
}

function hasAnnotationPreview(state) {
  return Boolean(state?.version?.paragraphs?.length && state?.comments?.length);
}

function aiStatusLabel(status) {
  if (status === "loading") return "运行中";
  if (status === "success") return "已完成";
  if (status === "error") return "不可用";
  return "待运行";
}
</script>

<style scoped>
.review-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}

.review-badge {
  display: inline-flex;
  align-items: center;
  padding: 4px 10px;
  border-radius: 4px;
  background: var(--color-error-bg);
  color: var(--color-brand);
  font-size: 12px;
  font-weight: 700;
}

.review-percent {
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text-secondary);
}

.review-progress-track {
  height: 8px;
  background: #fee2e2;
  border-radius: 4px;
  overflow: hidden;
  margin-bottom: 10px;
}

.review-progress-bar {
  height: 100%;
  background: var(--color-brand);
  border-radius: 4px;
}

.review-note {
  font-size: 13px;
  color: var(--color-text-secondary);
  margin: 0 0 18px;
}

.ai-unavailable-banner {
  padding: 12px 14px;
  border: 1px solid #f59e0b;
  border-radius: 6px;
  background: #fffbeb;
  color: #92400e;
  font-size: 13px;
  margin-bottom: 14px;
}

.ai-review-toolbar {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 10px;
  margin-bottom: 16px;
}

.ai-toolbar-note {
  font-size: 12px;
  color: var(--color-text-secondary);
  line-height: 1.5;
}

.review-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 12px;
  margin-bottom: 8px;
}

.review-card {
  padding: 16px;
  border: 1px solid var(--color-border);
  border-radius: 6px;
  background: var(--color-surface);
}

.ai-review-card {
  display: flex;
  flex-direction: column;
  min-height: 210px;
}

.review-card-top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}

.ai-status-pill {
  flex-shrink: 0;
  padding: 4px 8px;
  border-radius: 999px;
  background: #f3f4f6;
  color: var(--color-text-secondary);
  font-size: 12px;
  font-weight: 700;
}

.ai-status-pill.loading {
  background: #eff6ff;
  color: #1d4ed8;
}

.ai-status-pill.success {
  background: #dcfce7;
  color: #15803d;
}

.ai-status-pill.error {
  background: #fee2e2;
  color: #b91c1c;
}

.ai-placeholder,
.ai-error,
.ai-result {
  flex: 1;
  margin: 4px 0 14px;
  font-size: 13px;
  line-height: 1.6;
}

.ai-placeholder {
  color: var(--color-text-muted);
}

.ai-error {
  color: #b91c1c;
}

.ai-detail {
  color: var(--color-text);
  margin-bottom: 8px;
}

.ai-score {
  display: inline-flex;
  align-items: center;
  min-height: 26px;
  padding: 3px 8px;
  border-radius: 999px;
  background: var(--color-brand-light);
  color: var(--color-brand);
  font-size: 12px;
  font-weight: 700;
  margin-bottom: 8px;
}

.ai-suggestions {
  margin: 0;
  padding-left: 18px;
  color: var(--color-text-secondary);
}

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

.ai-answer {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  margin: 0;
  font: inherit;
  color: var(--color-text-secondary);
}

.ai-parse-warning {
  margin-top: 8px;
  color: #92400e;
  font-size: 12px;
}

.btn-primary,
.btn-secondary {
  padding: 10px 18px;
  border-radius: 6px;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: opacity 0.15s, transform 0.05s;
}

.btn-primary {
  border: 0;
  background: var(--color-brand);
  color: #fff;
}

.btn-secondary {
  border: 1px solid var(--color-border-strong);
  background: var(--color-surface);
  color: var(--color-text-secondary);
}

.btn-primary:disabled,
.btn-secondary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.ai-run-btn {
  align-self: flex-start;
}

@media (min-width: 860px) {
  .review-grid {
    grid-template-columns: 1fr 1fr;
  }

  .ai-annotation-preview {
    grid-template-columns: minmax(0, 1fr) minmax(220px, 0.65fr);
  }
}
</style>
