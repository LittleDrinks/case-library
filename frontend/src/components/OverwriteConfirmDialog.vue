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
          <h2 id="overwrite-confirm-title">恢复此版本？</h2>
          <button type="button" title="关闭" aria-label="关闭" :disabled="busy" @click="emit('cancel')">
            <X :size="18" />
          </button>
        </header>
        <div class="overwrite-body">
          <p class="overwrite-warning">
            将用「{{ versionLabel }}」恢复当前教师稿：当前正文和批注会先保存为“恢复前的当前稿”，随后恢复目标版本的正文、批注讨论和状态。
          </p>
          <p class="overwrite-muted">其他历史版本不受影响；取消不会改变当前稿，确认后在当前教师稿继续编辑。</p>
          <p v-if="error" class="review-decision-error" role="alert">{{ error }}</p>
        </div>
        <footer>
          <button type="button" aria-label="取消恢复" :disabled="busy" @click="emit('cancel')">取消</button>
          <button class="primary" type="button" aria-label="确认恢复" :disabled="busy" @click="emit('confirm')">
            {{ busy ? "处理中" : "确认恢复" }}
          </button>
        </footer>
      </section>
    </div>
  </Teleport>
</template>
