<template>
  <div class="submit-step">
    <section class="summary-card">
      <div class="summary-header">
        <div class="summary-icon" aria-hidden="true">
          <svg viewBox="0 0 24 24">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
            <polyline points="14 2 14 8 20 8"></polyline>
            <line x1="16" y1="13" x2="8" y2="13"></line>
            <line x1="16" y1="17" x2="8" y2="17"></line>
          </svg>
        </div>
        <div>
          <div class="summary-title">案例信息汇总</div>
          <div class="summary-subtitle">提交前请再次确认以下内容</div>
        </div>
      </div>

      <div class="field-row">
        <div class="field-label">案例标题</div>
        <div class="field-value">{{ form.title || "—（请填写）" }}</div>
      </div>
      <div class="field-row">
        <div class="field-label">作者姓名</div>
        <div class="field-value">{{ form.author || "—" }}</div>
      </div>
      <div class="field-row">
        <div class="field-label">所属学院</div>
        <div class="field-value">{{ form.department || "—" }}</div>
      </div>
      <div class="field-row field-row-block">
        <div class="field-label">案例正文</div>
        <div class="field-value">
          <CaseReader :content="form.content" :empty-text="contentSummary || '未填写'" compact />
        </div>
      </div>
      <div class="field-row">
        <div class="field-label">案例类型</div>
        <div class="field-value">
          <span v-if="form.type" class="field-tag">{{ constants.case_types[form.type] }}</span>
          <span v-else>—</span>
        </div>
      </div>
      <div class="field-row">
        <div class="field-label">思政主题</div>
        <div class="field-value">
          <span v-if="form.theme" class="field-tag">{{ form.theme }}</span>
          <span v-else>—</span>
        </div>
      </div>
      <div class="field-row">
        <div class="field-label">适用学段</div>
        <div class="field-value">
          <span v-if="targetStageSummary" class="field-tag">{{ targetStageSummary }}</span>
          <span v-else>—</span>
        </div>
      </div>
    </section>

    <section class="confirm-box">
      <div class="confirm-icon" aria-hidden="true">
        <svg viewBox="0 0 24 24">
          <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path>
          <polyline points="22 4 12 14.01 9 11.01"></polyline>
        </svg>
      </div>
      <div class="confirm-title">准备提交</div>
      <p class="confirm-text">
        提交后案例将进入专家人工审核流程，期间仍可在“我的提交”中查看状态。
      </p>
      <label class="agreement-row">
        <input v-model="originalConfirmed" type="checkbox" />
        <span class="agreement-text">我确认本案例内容真实、原创，引用材料已注明来源。</span>
      </label>
      <label class="agreement-row">
        <input v-model="reviewConfirmed" type="checkbox" />
        <span class="agreement-text">我了解提交后案例将进入专家人工审核流程。</span>
      </label>
      <button
        type="button"
        class="btn-submit-final"
        :disabled="submitting || !canSubmit || !canConfirmSubmit"
        @click="$emit('submit')"
      >
        <span>{{ submitting ? "提交中…" : "正式提交案例" }}</span>
        <svg class="icon" viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
          <path fill="currentColor" d="M2 21l21-9L2 3v7l15 2-15 2v7z"></path>
        </svg>
      </button>
    </section>
  </div>
</template>

<script setup>
import { computed, ref } from "vue";
import CaseReader from "../cases/CaseReader.vue";

const props = defineProps({
  form: {
    type: Object,
    required: true,
  },
  constants: {
    type: Object,
    required: true,
  },
  canSubmit: {
    type: Boolean,
    default: false,
  },
  submitting: {
    type: Boolean,
    default: false,
  },
  contentSummary: {
    type: String,
    default: "未填写",
  },
});

defineEmits(["submit"]);

const originalConfirmed = ref(false);
const reviewConfirmed = ref(false);
const canConfirmSubmit = computed(() => originalConfirmed.value && reviewConfirmed.value);
const targetStageSummary = computed(() => {
  return (props.form.target_stages || [])
    .map((stage) => props.constants.target_stages?.[stage] || stage)
    .join("、");
});
</script>

<style scoped>
.summary-card {
  border: 1px solid var(--color-border);
  border-radius: 10px;
  padding: 28px;
  background: var(--color-surface);
  margin-bottom: 20px;
}

.summary-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 20px;
  padding-bottom: 16px;
  border-bottom: 1px solid #f0f0f0;
}

.summary-icon {
  width: 40px;
  height: 40px;
  display: grid;
  place-items: center;
  border-radius: 50%;
  background: var(--color-brand-light);
  color: var(--color-brand);
  flex-shrink: 0;
}

.summary-icon svg,
.confirm-icon svg {
  width: 20px;
  height: 20px;
  fill: none;
  stroke: currentColor;
  stroke-width: 2;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.summary-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--color-text);
}

.summary-subtitle {
  margin-top: 2px;
  font-size: 12px;
  color: var(--color-text-secondary);
}

.field-row {
  display: flex;
  padding: 12px 0;
  border-bottom: 1px solid #f5f5f5;
}

.field-row:last-child {
  border-bottom: 0;
}

.field-label {
  width: 120px;
  flex-shrink: 0;
  font-size: 13px;
  color: var(--color-text-secondary);
  font-weight: 500;
}

.field-value {
  flex: 1;
  min-width: 0;
  font-size: 13px;
  color: var(--color-text);
  overflow-wrap: anywhere;
}

.field-row-block {
  display: block;
}

.field-row-block .field-label {
  width: auto;
  margin-bottom: 10px;
}

.field-tag {
  display: inline-flex;
  align-items: center;
  padding: 3px 10px;
  border-radius: 4px;
  background: var(--color-brand-light);
  color: var(--color-brand);
  font-size: 12px;
  font-weight: 500;
}

.confirm-box {
  border: 1.5px solid var(--color-brand);
  border-radius: 10px;
  padding: 24px;
  background: var(--color-brand-light);
  text-align: center;
  margin: 28px 0;
}

.confirm-icon {
  width: 56px;
  height: 56px;
  display: grid;
  place-items: center;
  border-radius: 50%;
  background: var(--color-brand);
  color: #fff;
  margin: 0 auto 16px;
}

.confirm-icon svg {
  width: 28px;
  height: 28px;
}

.confirm-title {
  margin-bottom: 8px;
  font-family: var(--font-display);
  font-size: 22px;
  font-weight: 700;
  color: var(--color-brand);
}

.confirm-text {
  max-width: 480px;
  margin: 0 auto 20px;
  font-size: 13px;
  line-height: 1.7;
  color: var(--color-text-secondary);
}

.agreement-row {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  max-width: 620px;
  margin: 0 auto 12px;
  padding: 14px;
  border-radius: 8px;
  background: #fafafa;
  text-align: left;
}

.agreement-row input[type="checkbox"] {
  width: 16px;
  height: 16px;
  margin-top: 2px;
  accent-color: var(--color-brand);
  flex-shrink: 0;
}

.agreement-text {
  font-size: 13px;
  line-height: 1.6;
  color: var(--color-text);
}

.btn-submit-final {
  margin-top: 8px;
  width: auto;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  min-height: 42px;
  padding: 10px 24px;
  border: 1px solid var(--color-brand);
  border-radius: 6px;
  background: var(--color-brand);
  color: #fff;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
}

.btn-submit-final:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

@media (max-width: 640px) {
  .summary-card,
  .confirm-box {
    padding: 20px;
  }

  .field-label {
    width: 90px;
  }

  .btn-submit-final {
    width: 100%;
  }
}
</style>
