<script setup>
import { computed, nextTick, ref, watch } from "vue";
import { X } from "@lucide/vue";

const props = defineProps({
  command: { type: String, default: "" },
  busy: { type: Boolean, default: false },
  error: { type: String, default: "" },
});
const emit = defineEmits(["cancel", "confirm"]);
const reasonInput = ref(null);
const reasonType = ref("");
const summary = ref("");
const copy = computed(() => ({
  reject: { title: "退回修改", confirm: "确认退回" },
  supplement: { title: "要求补充", confirm: "确认要求补充" },
}[props.command]));

function cancel() {
  if (!props.busy) emit("cancel");
}

function submit() {
  const reason = reasonType.value.trim();
  if (!reason || props.busy) return;
  emit("confirm", { reasonType: reason, summary: summary.value.trim() || undefined });
}

async function resetForm() {
  reasonType.value = "";
  summary.value = "";
  await nextTick();
  reasonInput.value?.focus();
}

watch(() => props.command, resetForm);
</script>

<template>
  <Teleport to="body">
    <div
      v-if="copy"
      class="review-decision-backdrop"
      @mousedown.self="cancel"
      @keydown.esc="cancel"
    >
      <section
        class="review-decision-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="review-decision-title"
      >
        <header>
          <h2 id="review-decision-title">{{ copy.title }}</h2>
          <button type="button" title="关闭" aria-label="关闭" :disabled="busy" @click="cancel">
            <X :size="18" />
          </button>
        </header>
        <form @submit.prevent="submit">
          <label>
            <span>原因类型</span>
            <input ref="reasonInput" v-model="reasonType" required maxlength="80" />
          </label>
          <label>
            <span>总评</span>
            <textarea v-model="summary" maxlength="4000" rows="5" />
          </label>
          <p v-if="error" class="review-decision-error" role="alert">{{ error }}</p>
          <footer>
            <button type="button" :disabled="busy" @click="cancel">取消</button>
            <button class="primary" type="submit" :disabled="!reasonType.trim() || busy">
              {{ busy ? "处理中" : copy.confirm }}
            </button>
          </footer>
        </form>
      </section>
    </div>
  </Teleport>
</template>
