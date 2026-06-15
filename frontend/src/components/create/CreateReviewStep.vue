<template>
  <div class="review-step">
    <div v-if="aiPromptLoadError" class="ai-unavailable-banner" role="status">
      {{ aiPromptLoadError }}
    </div>

    <section class="review-panel">
      <div class="review-panel-header">
        <div class="review-panel-icon" aria-hidden="true">
          <svg viewBox="0 0 24 24">
            <rect x="3" y="3" width="18" height="18" rx="2"></rect>
            <path d="M3 9h18"></path>
            <path d="m9 15 2 2 4-5"></path>
          </svg>
        </div>
        <div class="review-panel-title-wrap">
          <div class="review-panel-title">AI 智能内容审核</div>
          <div class="review-panel-subtitle">作者侧提交前自查，不代表专家审核结论</div>
        </div>
        <button
          type="button"
          class="btn-primary"
          :disabled="aiRunningAll || !canRunAiReview"
          @click="$emit('run-all')"
        >
          {{ aiRunningAll ? "生成中…" : "生成自查建议" }}
        </button>
      </div>

      <div class="review-panel-body">
        <div v-if="aiRunningAll || hasLoadingItem" class="review-running" role="status">
          <span class="review-spinner" aria-hidden="true"></span>
          <span>AI 正在生成段落批注，请稍候…</span>
        </div>
        <div class="review-progress-row">
          <span>自查进度</span>
          <strong>{{ aiReviewProgress }}%</strong>
        </div>
        <div class="review-progress-track">
          <div class="review-progress-bar" :style="{ width: aiReviewProgress + '%' }"></div>
        </div>
        <p class="review-note">
          需要先填写标题、正文、类型和主题。AI 会生成段落级批注版本，不会给出审批结论。
        </p>

        <div class="review-list">
          <div v-for="item in aiReviewItems" :key="item.id" class="review-item">
            <div class="review-item-main">
              <div class="review-card-top">
                <div>
                  <div class="review-card-title">{{ item.name }}</div>
                  <div class="review-card-desc">{{ item.description }}</div>
                </div>
                <div class="review-card-actions">
                  <span class="ai-status-pill" :class="aiReviewState[item.id].status">
                    {{ aiStatusLabel(aiReviewState[item.id].status) }}
                  </span>
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

              <AiReviewResult :state="aiReviewState[item.id]" />
            </div>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed } from "vue";
import AiReviewResult from "./AiReviewResult.vue";

const props = defineProps({
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

const hasLoadingItem = computed(() => {
  return props.aiReviewItems.some((item) => props.aiReviewState[item.id]?.status === "loading");
});

function aiStatusLabel(status) {
  if (status === "loading") return "运行中";
  if (status === "success") return "已完成";
  if (status === "error") return "不可用";
  return "待运行";
}
</script>

<style scoped>
.review-panel {
  border: 1px solid var(--color-border);
  border-radius: 10px;
  background: var(--color-surface);
  overflow: hidden;
  margin-bottom: 24px;
}

.review-panel-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 20px 24px;
  border-bottom: 1px solid var(--color-border);
}

.review-panel-icon {
  width: 40px;
  height: 40px;
  display: grid;
  place-items: center;
  border-radius: 10px;
  background: var(--color-brand-light);
  color: var(--color-brand);
  flex-shrink: 0;
}

.review-panel-icon svg {
  width: 20px;
  height: 20px;
  fill: none;
  stroke: currentColor;
  stroke-width: 2;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.review-panel-title-wrap {
  flex: 1;
  min-width: 0;
}

.review-panel-title {
  margin-bottom: 2px;
  font-size: 16px;
  font-weight: 600;
  color: var(--color-text);
}

.review-panel-subtitle {
  font-size: 12px;
  color: var(--color-text-secondary);
}

.review-panel-body {
  padding: 24px;
}

.review-running {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 14px;
  padding: 12px 14px;
  border: 1px solid rgba(141, 27, 53, 0.18);
  border-radius: 8px;
  background: var(--color-brand-light);
  color: var(--color-brand);
  font-size: 13px;
  font-weight: 600;
}

.review-spinner {
  width: 18px;
  height: 18px;
  border: 2px solid rgba(141, 27, 53, 0.18);
  border-top-color: var(--color-brand);
  border-radius: 50%;
  animation: review-spin 0.8s linear infinite;
  flex-shrink: 0;
}

@keyframes review-spin {
  to {
    transform: rotate(360deg);
  }
}

.review-progress-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
  font-size: 13px;
  color: var(--color-text-secondary);
}

.review-progress-row strong {
  color: var(--color-brand);
}

.review-progress-track {
  height: 6px;
  background: #f0f0f0;
  border-radius: 3px;
  overflow: hidden;
  margin-bottom: 12px;
}

.review-progress-bar {
  height: 100%;
  background: var(--color-brand);
  border-radius: 3px;
  transition: width 0.2s ease;
}

.review-note {
  font-size: 13px;
  color: var(--color-text-secondary);
  margin: 0 0 20px;
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

.review-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.review-item {
  padding: 16px;
  border: 1px solid var(--color-border);
  border-radius: 8px;
  background: #fafafa;
}

.review-item-main {
  flex: 1;
  min-width: 0;
}

.review-card-top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 14px;
}

.review-card-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text);
}

.review-card-desc {
  margin-top: 4px;
  font-size: 12px;
  line-height: 1.6;
  color: var(--color-text-secondary);
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

.review-card-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
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
  min-height: 42px;
  padding: 10px 18px;
  border-radius: 6px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: opacity 0.15s, transform 0.05s;
  white-space: nowrap;
}

.btn-primary {
  border: 1px solid var(--color-brand);
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
  min-height: 34px;
  padding: 7px 14px;
}

@media (max-width: 700px) {
  .review-panel-header,
  .review-card-top,
  .review-card-actions {
    flex-direction: column;
    align-items: stretch;
  }

  .btn-primary,
  .btn-secondary {
    width: 100%;
    justify-content: center;
  }
}
</style>
