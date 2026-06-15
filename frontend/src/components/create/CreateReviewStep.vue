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

        <AiReviewResult :state="aiReviewState[item.id]" />

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
import AiReviewResult from "./AiReviewResult.vue";

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
}
</style>
