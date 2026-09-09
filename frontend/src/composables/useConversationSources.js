import { computed, ref } from "vue";

// 本案例「用于对话」的资料上下文，跨 composer 与资料区共享；
// 与正文引用（citation mark）相互独立，取消对话上下文不动正文标记。
const selected = ref([]);

export function conversationSourceKey(source) {
  return `${source.sourceType}:${source.id}`;
}

function sameSource(left, right) {
  return conversationSourceKey(left) === conversationSourceKey(right);
}

function has(source) {
  return selected.value.some((row) => sameSource(row, source));
}

function toggle(source) {
  selected.value = has(source)
    ? selected.value.filter((row) => !sameSource(row, source))
    : [...selected.value, source];
}

function remove(source) {
  selected.value = selected.value.filter((row) => !sameSource(row, source));
}

function clear() {
  selected.value = [];
}

export function useConversationSources() {
  return { sources: computed(() => selected.value), has, toggle, remove, clear };
}
