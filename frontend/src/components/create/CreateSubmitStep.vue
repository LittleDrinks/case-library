<template>
  <div class="submit-step">
    <div class="pass-notice">
      <span class="pass-icon" aria-hidden="true"></span>
      <span>提交后案例将进入专家人工审核流程，请耐心等待。</span>
    </div>

    <div class="submit-card">
      <div class="submit-card-header">
        <h3>提交至专家审核</h3>
        <span class="status-pill">待审核</span>
      </div>
      <ul class="submit-checklist">
        <li :class="{ ok: form.title }">
          <span class="check" aria-hidden="true"></span>
          案例标题：{{ form.title || "未填写" }}
        </li>
        <li :class="{ ok: form.department }">
          <span class="check" aria-hidden="true"></span>
          所属部门/学院：{{ form.department || "未填写" }}
        </li>
        <li :class="{ ok: form.content }">
          <span class="check" aria-hidden="true"></span>
          案例正文：{{ contentSummary }}
        </li>
        <li :class="{ ok: form.type }">
          <span class="check" aria-hidden="true"></span>
          案例类型：{{ form.type ? constants.case_types[form.type] : "未选择" }}
        </li>
        <li :class="{ ok: form.theme }">
          <span class="check" aria-hidden="true"></span>
          案例主题：{{ form.theme || "未选择" }}
        </li>
      </ul>
      <button
        type="button"
        class="btn-submit-final"
        :disabled="submitting || !canSubmit"
        @click="$emit('submit')"
      >
        <span>{{ submitting ? "提交中…" : "正式提交案例" }}</span>
        <svg class="icon" viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
          <path fill="currentColor" d="M2 21l21-9L2 3v7l15 2-15 2v7z"></path>
        </svg>
      </button>
    </div>
  </div>
</template>

<script setup>
defineProps({
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
</script>

<style scoped>
.pass-notice {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 14px;
  border: 1px solid var(--color-brand);
  border-radius: 6px;
  color: var(--color-brand);
  font-size: 14px;
  font-weight: 600;
  margin-bottom: 18px;
}

.pass-icon {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: var(--color-brand);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  flex-shrink: 0;
}

.pass-icon::before {
  content: "";
  width: 10px;
  height: 6px;
  border-left: 2px solid #fff;
  border-bottom: 2px solid #fff;
  transform: rotate(-45deg) translateY(-1px);
}

.submit-card {
  padding: 20px;
  border: 1px solid var(--color-border);
  border-radius: 8px;
  background: var(--color-surface);
}

.submit-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 14px;
}

.submit-card-header h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 700;
  color: var(--color-text);
}

.status-pill {
  padding: 4px 10px;
  border-radius: 999px;
  background: #fef3c7;
  color: #92400e;
  font-size: 12px;
  font-weight: 700;
}

.submit-checklist {
  list-style: none;
  margin: 0 0 20px;
  padding: 0;
}

.submit-checklist li {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 8px 0;
  font-size: 13px;
  color: var(--color-text-secondary);
  border-bottom: 1px solid var(--color-border);
}

.submit-checklist li:last-child {
  border-bottom: 0;
}

.submit-checklist li.ok {
  color: var(--color-text);
}

.submit-checklist .check {
  position: relative;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  flex-shrink: 0;
  border: 2px solid var(--color-border-strong);
  color: var(--color-text-muted);
}

.submit-checklist li.ok .check {
  background: var(--color-brand);
  border-color: var(--color-brand);
  color: #fff;
}

.submit-checklist li.ok .check::before {
  content: "";
  width: 7px;
  height: 4px;
  border-left: 2px solid currentColor;
  border-bottom: 2px solid currentColor;
  transform: rotate(-45deg) translate(1px, -1px);
}

.btn-submit-final {
  width: 100%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 12px 20px;
  border: 0;
  border-radius: 6px;
  background: var(--color-brand);
  color: #fff;
  font-size: 15px;
  font-weight: 700;
  cursor: pointer;
}

.btn-submit-final:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
</style>
