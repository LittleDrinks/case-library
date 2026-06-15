<template>
  <div v-if="state.status === 'idle'" class="ai-placeholder">
    尚未运行。点击下方按钮获取作者侧自查建议。
  </div>

  <div v-else-if="state.status === 'loading'" class="ai-placeholder">正在请求后端 AI 自查…</div>

  <div v-else-if="state.status === 'error'" class="ai-error">
    {{ state.error }}
  </div>

  <div v-else class="ai-result">
    <div v-if="state.parsed" class="ai-result-body">
      <div v-if="state.parsed.detail" class="ai-detail">
        {{ state.parsed.detail }}
      </div>
      <div v-if="state.parsed.score != null" class="ai-score">评分 {{ state.parsed.score }}</div>
      <ul
        v-if="Array.isArray(state.parsed.suggestions) && state.parsed.suggestions.length"
        class="ai-suggestions"
      >
        <li v-for="suggestion in state.parsed.suggestions" :key="suggestion">
          {{ suggestion }}
        </li>
      </ul>
      <ul
        v-if="Array.isArray(state.comments) && state.comments.length && !hasAnnotationPreview"
        class="ai-suggestions"
      >
        <li v-for="comment in state.comments" :key="comment.id || comment.message">
          {{ comment.paragraph_id }}：{{ comment.message }}
        </li>
      </ul>
      <AiAnnotationPreview v-if="hasAnnotationPreview" :state="state" />
    </div>
    <pre v-else class="ai-answer">{{ state.answer }}</pre>
    <div v-if="state.parse_error" class="ai-parse-warning">
      {{ state.parse_error }}
    </div>
  </div>
</template>

<script setup>
import { computed } from "vue";
import AiAnnotationPreview from "./AiAnnotationPreview.vue";

const props = defineProps({
  state: {
    type: Object,
    required: true,
  },
});

const hasAnnotationPreview = computed(() =>
  Boolean(props.state?.version?.paragraphs?.length && props.state?.comments?.length),
);
</script>

<style scoped>
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
</style>
