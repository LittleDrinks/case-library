import { computed, inject, ref } from "vue";

// 「用于对话」资料上下文：由工作台页（WorkbenchView）按案例提供，
// composer 与资料区（AttachmentPanel「用于对话」）注入同一份；
// 与正文引用（citation mark）相互独立，取消对话上下文不动正文标记。
export const CONVERSATION_SOURCES_KEY = "conversation-sources";

export function conversationSourceKey(source) {
  return `${source.sourceType}:${source.id}`;
}

export function createConversationSources() {
  const selected = ref([]);
  const same = (left, right) => conversationSourceKey(left) === conversationSourceKey(right);
  const has = (source) => selected.value.some((row) => same(row, source));
  const remove = (source) => {
    selected.value = selected.value.filter((row) => !same(row, source));
  };
  const toggle = (source) => {
    selected.value = has(source)
      ? selected.value.filter((row) => !same(row, source)) : [...selected.value, source];
  };
  const clear = () => { selected.value = []; };
  return { sources: computed(() => selected.value), has, toggle, remove, clear };
}

// 未被提供时（独立挂载/测试）退化为实例私有状态；正式页面由 WorkbenchView 提供
export function useConversationSources() {
  return inject(CONVERSATION_SOURCES_KEY, null) || createConversationSources();
}
