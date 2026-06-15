<template>
  <div class="basic-step">
    <div class="field">
      <label for="ccf-title">
        案例标题 <span class="required" aria-hidden="true">*</span>
      </label>
      <input
        id="ccf-title"
        v-model="form.title"
        type="text"
        placeholder="输入具有学术性与引领性的标题"
        :aria-invalid="!!errors.title"
        @blur="$emit('touch', 'title')"
      />
      <div class="field-help">建议标题长度在 15-30 字之间，包含核心教学知识点。</div>
      <div v-if="errors.title" class="field-error" role="alert">{{ errors.title }}</div>
    </div>

    <div class="row two-col">
      <div class="field">
        <label for="ccf-author">作者姓名</label>
        <input
          id="ccf-author"
          :value="displayAuthor"
          type="text"
          readonly
          class="readonly"
          aria-describedby="ccf-author-tip"
        />
        <div id="ccf-author-tip" class="field-help">取自当前登录账号信息</div>
      </div>
      <div class="field">
        <label for="ccf-department">
          所属部门/学院 <span class="required" aria-hidden="true">*</span>
        </label>
        <input
          id="ccf-department"
          v-model="form.department"
          type="text"
          placeholder="例如：马克思主义学院"
          :aria-invalid="!!errors.department"
          @blur="$emit('touch', 'department')"
        />
        <div v-if="errors.department" class="field-error" role="alert">
          {{ errors.department }}
        </div>
      </div>
    </div>

    <div class="tip-card">
      <div class="tip-icon" aria-hidden="true"></div>
      <div class="tip-body">
        <div class="tip-title">编写小贴士</div>
        <p>
          优秀的思政案例应当将价值引领与知识传授有机融合。在“基本信息”阶段，请确保作者姓名准确，并使用官方全称标注所属学院。
        </p>
      </div>
    </div>
  </div>
</template>

<script setup>
defineProps({
  form: {
    type: Object,
    required: true,
  },
  errors: {
    type: Object,
    required: true,
  },
  displayAuthor: {
    type: String,
    default: "",
  },
});

defineEmits(["touch"]);
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

input[type="text"] {
  width: 100%;
  height: 43px;
  padding: 11px 14px;
  border: 1px solid var(--color-border-strong);
  border-radius: 6px;
  font-family: inherit;
  font-size: 14px;
  color: var(--color-text);
  background: var(--color-surface);
  outline: none;
  transition: border-color 0.15s, box-shadow 0.15s;
}

input[type="text"]:focus {
  border-color: var(--color-brand);
  box-shadow: 0 0 0 3px var(--color-brand-light);
}

input[type="text"]::placeholder {
  color: #c8ced8;
}

input.readonly {
  background: #f3f4f6;
  color: var(--color-text-secondary);
}

.field-help {
  margin-top: 8px;
  font-size: 11px;
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

.row.two-col {
  display: grid;
  grid-template-columns: 1fr;
  gap: 0;
}

.tip-card {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 16px 20px;
  border: 0;
  border-radius: 8px;
  background: var(--color-brand-light);
  box-shadow: none;
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
  font-size: 12px;
  font-weight: 700;
  font-family: Georgia, serif;
  line-height: 1;
}

.tip-icon::after {
  content: none;
}

.tip-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text);
  margin-bottom: 4px;
}

.tip-body {
  min-width: 0;
}

.tip-body p {
  margin: 0;
  font-size: 12px;
  color: var(--color-text-secondary);
  line-height: 1.7;
}

@media (min-width: 860px) {
  .row.two-col {
    grid-template-columns: 1fr 1fr;
    gap: 20px;
  }
}
</style>
