<script setup>
import { X } from "@lucide/vue";

defineProps({
  open: { type: Boolean, default: false },
  versionLabel: { type: String, default: "" },
  busy: { type: Boolean, default: false },
  error: { type: String, default: "" },
});
const emit = defineEmits(["cancel", "confirm"]);
</script>

<template>
  <Teleport to="body">
    <div
      v-if="open"
      class="review-decision-backdrop"
      @mousedown.self="!busy && emit('cancel')"
      @keydown.esc="!busy && emit('cancel')"
    >
      <section
        class="review-decision-dialog overwrite-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="overwrite-confirm-title"
      >
        <header>
          <h2 id="overwrite-confirm-title">覆盖当前教师稿？</h2>
          <button type="button" title="关闭" aria-label="关闭" :disabled="busy" @click="emit('cancel')">
            <X :size="18" />
          </button>
        </header>
        <div class="overwrite-body">
          <p class="overwrite-warning">
            将用「{{ versionLabel }}」覆盖当前教师稿：正文等内容将被替换，工作稿上的现有批注将被清除，覆盖后无法找回。
          </p>
          <p class="overwrite-muted">其他历史版本不受影响；确认后在第一个 Tab 继续编辑。</p>
          <p v-if="error" class="review-decision-error" role="alert">{{ error }}</p>
        </div>
        <footer>
          <button type="button" aria-label="取消覆盖" :disabled="busy" @click="emit('cancel')">取消</button>
          <button class="primary" type="button" aria-label="确认覆盖" :disabled="busy" @click="emit('confirm')">
            {{ busy ? "处理中" : "确认覆盖" }}
          </button>
        </footer>
      </section>
    </div>
  </Teleport>
</template>
