<script setup>
// 选区浮条：B / I / 链接 / 批注 / 问AI。mousedown.prevent 保选区；菜单不抢焦点。
import { computed, ref } from "vue";
import { BubbleMenu } from "@tiptap/vue-3";
import { Bold, Italic, Link2, MessageSquarePlus, Sparkles } from "@lucide/vue";

const props = defineProps({ editor: { type: Object, required: true } });
const emit = defineEmits(["annotate", "ask-ai", "selection-change"]);
const linking = ref(false);
const linkUrl = ref("");

const shouldShow = ({ editor, from, to }) => {
  const nonEmpty = from !== to;
  const hasText = editor.state.doc.textBetween(from, to).trim().length > 0;
  if (!nonEmpty || !hasText) { linking.value = false; return false; }
  return true;
};

function currentSelection(editor) {
  const { from, to } = editor.state.selection;
  return { from, to, quote: editor.state.doc.textBetween(from, to, " ") };
}

function runAnnotate() {
  emit("annotate", currentSelection(props.editor));
}
function runAskAi() {
  emit("ask-ai", currentSelection(props.editor));
}
function applyLink() {
  const url = linkUrl.value.trim();
  if (url) {
    props.editor.chain().focus().extendMarkRange("link").setLink({ href: url }).run();
  }
  linking.value = false;
  linkUrl.value = "";
}
</script>

<template>
  <bubble-menu
    :editor="editor"
    :should-show="shouldShow"
    :tippy-options="{ duration: 120, placement: 'top', offset: [0, 8] }"
    class="sel-balloon"
    @update="$emit('selection-change', editor)"
  >
    <button type="button" title="加粗" :class="{ active: editor.isActive('bold') }" @mousedown.prevent @click="editor.chain().focus().toggleBold().run()"><Bold :size="15" /></button>
    <button type="button" title="斜体" :class="{ active: editor.isActive('italic') }" @mousedown.prevent @click="editor.chain().focus().toggleItalic().run()"><Italic :size="15" /></button>
    <button type="button" title="链接" :class="{ active: editor.isActive('link') }" @mousedown.prevent="linking = !linking"><Link2 :size="15" /></button>
    <span class="balloon-divider" />
    <button type="button" title="批注" @mousedown.prevent="runAnnotate"><MessageSquarePlus :size="15" /></button>
    <button type="button" title="问 AI" class="ai" @mousedown.prevent="runAskAi"><Sparkles :size="15" /></button>
    <div v-if="linking" class="balloon-link-form" @mousedown.prevent.stop>
      <input v-model="linkUrl" type="url" placeholder="https://…" @keydown.enter.prevent="applyLink" />
      <button type="button" @click="applyLink">应用</button>
    </div>
  </bubble-menu>
</template>
