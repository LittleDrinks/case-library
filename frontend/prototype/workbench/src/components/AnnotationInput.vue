<script setup>
import { nextTick, onMounted, ref } from "vue";
const props = defineProps({ label: { type: String, default: "写下批注" } });
const emit = defineEmits(["save", "cancel"]);
const text = ref("");
const input = ref(null);
onMounted(() => nextTick(() => input.value?.focus()));
function save() {
  if (text.value.trim()) emit("save", text.value.trim());
}
</script>
<template>
  <form class="annotation-input" @submit.prevent="save" @keydown.esc.stop="emit('cancel')">
    <textarea ref="input" v-model="text" :aria-label="label" :placeholder="label" rows="3" @keydown.ctrl.enter.prevent="save" />
    <footer><span>Ctrl + Enter 发送</span><button type="button" @click="emit('cancel')">取消</button><button type="submit" :disabled="!text.trim()">发送</button></footer>
  </form>
</template>
