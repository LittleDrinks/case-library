<script setup>
import { nextTick, ref, watch } from "vue";
import { X } from "@lucide/vue";

const props = defineProps({
  command: { type: String, default: "" },
  busy: { type: Boolean, default: false },
  error: { type: String, default: "" },
});
const emit = defineEmits(["cancel", "confirm"]);
const firstReasonInput = ref(null);
const reasons = [
  "内容需要补充或修改",
  "事实、数据或来源需要核实",
  "格式或案例信息需要调整",
  "其他",
];
const reasonTypes = ref([]);
const message = ref("");

function cancel() {
  if (!props.busy) emit("cancel");
}

function submit() {
  if (!reasonTypes.value.length || props.busy) return;
  emit("confirm", {
    reasonTypes: [...reasonTypes.value],
    message: message.value.trim() || undefined,
  });
}

function setFirstReasonInput(element) {
  firstReasonInput.value = element;
}

async function resetForm() {
  reasonTypes.value = [];
  message.value = "";
  await nextTick();
  firstReasonInput.value?.focus();
}

watch(() => props.command, resetForm);
</script>

<template>
  <Teleport to="body">
    <div
      v-if="command === 'reject'"
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
          <h2 id="review-decision-title">退回修改</h2>
          <button type="button" title="关闭" aria-label="关闭" :disabled="busy" @click="cancel">
            <X :size="18" />
          </button>
        </header>
        <form @submit.prevent="submit">
          <fieldset>
            <legend>退回原因（至少选择一项）</legend>
            <label v-for="reason in reasons" :key="reason" class="review-decision-reason">
              <input
                :ref="reason === reasons[0] ? setFirstReasonInput : undefined"
                v-model="reasonTypes"
                type="checkbox"
                :value="reason"
                :disabled="busy"
              />
              <span>{{ reason }}</span>
            </label>
          </fieldset>
          <label>
            <span>留言（可选）</span>
            <textarea v-model="message" maxlength="4000" rows="5" :disabled="busy" />
          </label>
          <p v-if="error" class="review-decision-error" role="alert">{{ error }}</p>
          <footer>
            <button type="button" :disabled="busy" @click="cancel">取消</button>
            <button class="primary" type="submit" :disabled="!reasonTypes.length || busy">
              {{ busy ? "处理中" : "确认退回" }}
            </button>
          </footer>
        </form>
      </section>
    </div>
  </Teleport>
</template>
