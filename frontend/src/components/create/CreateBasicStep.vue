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
        placeholder="请输入案例标题"
        :aria-invalid="!!errors.title"
        @blur="$emit('touch', 'title')"
      />
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
          placeholder="请输入所属部门或学院"
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
        <ul>
          <li>标题应简洁明了，突出案例的核心问题与教学价值。</li>
          <li>作者姓名取自登录账号，如需修改请联系管理员。</li>
          <li>部门/学院信息将用于案例归属、统计与检索。</li>
        </ul>
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
  margin-bottom: 18px;
}

.field label {
  display: block;
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text);
  margin-bottom: 6px;
}

.required {
  color: var(--color-brand);
  margin-left: 2px;
}

input[type="text"] {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid var(--color-border-strong);
  border-radius: 4px;
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

input.readonly {
  background: #f3f4f6;
  color: var(--color-text-secondary);
}

.field-help {
  margin-top: 4px;
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

.row.two-col {
  display: grid;
  grid-template-columns: 1fr;
  gap: 0;
}

.tip-card {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 14px;
  border: 1px dashed var(--color-border-strong);
  border-radius: 6px;
  background: #fafafa;
}

.tip-icon {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: var(--color-brand-light);
  color: var(--color-brand);
  position: relative;
  flex-shrink: 0;
}

.tip-icon::before {
  content: "";
  position: absolute;
  left: 10px;
  top: 5px;
  width: 2px;
  height: 12px;
  background: currentColor;
  border-radius: 1px;
}

.tip-icon::after {
  content: "";
  position: absolute;
  left: 5px;
  top: 10px;
  width: 12px;
  height: 2px;
  background: currentColor;
  border-radius: 1px;
}

.tip-title {
  font-size: 13px;
  font-weight: 700;
  color: var(--color-text);
  margin-bottom: 6px;
}

.tip-body {
  min-width: 0;
}

.tip-body ul {
  margin: 0;
  padding-left: 16px;
  font-size: 13px;
  color: var(--color-text-secondary);
  line-height: 1.7;
}

@media (min-width: 860px) {
  .tip-card {
    flex-direction: row;
  }

  .row.two-col {
    grid-template-columns: 1fr 1fr;
    gap: 16px;
  }
}
</style>
