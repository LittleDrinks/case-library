<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import StarterKit from "@tiptap/starter-kit";
import { EditorContent, useEditor } from "@tiptap/vue-3";
import { MiniLink } from "./mini-link.js";
import { overlayKey, OverlayExtension } from "./decorations.js";
import SelectionBalloon from "./components/SelectionBalloon.vue";
import { initialDoc } from "./content.js";

const props = defineProps({
  snapshot: { type: Object, required: true },
});
const emit = defineEmits(["selection-change", "annotate", "ask-ai", "doc-change"]);
const editorEl = ref(null);
let decorationsTick = 0;

const editor = useEditor({
  content: initialDoc,
  extensions: [StarterKit, MiniLink, OverlayExtension.configure({ snapshot: () => props.snapshot })],
  onUpdate: () => { emit("doc-change"); bumpDecorations(); },
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
  focusQuote(quote) {
    const doc = editor.value.state.doc;
    let found = null;
    doc.descendants((node, pos) => {
      if (found || !node.isText || !node.text.includes(quote)) return;
      const start = pos + node.text.indexOf(quote);
      found = { from: start, to: start + quote.length };
      return false;
    });
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

// TextSelection 引入放底部避免与 SFC 编译器冲突
import { TextSelection } from "@tiptap/pm/state";
function TextSelectionNear(state, range) {
  return TextSelection.create(state.doc, range.from, range.to);
}
</script>

<template>
  <div ref="editorEl" class="paper-wrap">
    <EditorContent v-if="editor" :editor="editor" class="paper-editor" />
    <SelectionBalloon
      v-if="editor"
      :editor="editor"
      @annotate="(sel) => emit('annotate', sel)"
      @ask-ai="(sel) => emit('ask-ai', sel)"
      @selection-change="(e) => emit('selection-change', e)"
    />
  </div>
</template>
