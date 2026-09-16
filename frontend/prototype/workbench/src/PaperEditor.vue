<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import StarterKit from "@tiptap/starter-kit";
import { EditorContent, useEditor } from "@tiptap/vue-3";
import { MiniLink } from "./mini-link.js";
import { overlayKey, OverlayExtension } from "./decorations.js";
import SelectionBalloon from "./components/SelectionBalloon.vue";
import { findTextRange } from "./text-range.js";
import { initialDoc } from "./content.js";

const props = defineProps({
  snapshot: { type: Object, required: true },
});
const emit = defineEmits(["selection-change", "annotate", "ask-ai", "doc-change", "anchor", "open-ai-menu"]);
const editorEl = ref(null);
let decorationsTick = 0;

const editor = useEditor({
  content: initialDoc,
  extensions: [StarterKit, MiniLink, OverlayExtension.configure({ snapshot: () => props.snapshot })],
  onUpdate: ({ transaction }) => { emit("doc-change", transaction); bumpDecorations(); },
  onSelectionUpdate: () => emit("selection-change", editor.value),
});

function bumpDecorations() {
  nextTick(() => {
    if (!editor.value?.view) return;
    const view = editor.value.view;
    view.dispatch(view.state.tr.setMeta(overlayKey, { tick: ++decorationsTick }));
  });
}

defineExpose({
  editor,
  refresh: bumpDecorations,
  focusQuote(quote, range) {
    const found = findTextRange(editor.value.state.doc, quote, range);
    if (!found) return false;
    const view = editor.value.view;
    view.dispatch(view.state.tr.setSelection(TextSelectionNear(view.state, found)).scrollIntoView());
    editor.value.commands.focus();
    return true;
  },
  insertRevisionRange(range, replacement) {
    editor.value.chain().insertContentAt(range, replacement).run();
  },
});

function onAnchorClick(event) {
  const id = event.target.closest("[data-ann]")?.dataset.ann;
  const item = props.snapshot.annotations.find((a) => a.id === id);
  if (item) emit("anchor", item);
}

// TextSelection 引入放底部避免与 SFC 编译器冲突
import { TextSelection } from "@tiptap/pm/state";
function TextSelectionNear(state, range) {
  return TextSelection.create(state.doc, range.from, range.to);
}
</script>

<template>
  <div ref="editorEl" class="paper-wrap">
    <EditorContent v-if="editor" :editor="editor" class="paper-editor" @click="onAnchorClick" />
    <SelectionBalloon
      v-if="editor"
      :editor="editor"
      @annotate="(sel) => emit('annotate', sel)"
      @ask-ai="(sel) => emit('ask-ai', sel)"
      @open-ai-menu="(event) => emit('open-ai-menu', event)"
      @selection-change="(e) => emit('selection-change', e)"
    />
  </div>
</template>
