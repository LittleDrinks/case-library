<script setup>
import { watch } from "vue";
import StarterKit from "@tiptap/starter-kit";
import { EditorContent, useEditor } from "@tiptap/vue-3";

const props = defineProps({
  document: { type: Object, required: true },
});

const editor = useEditor({
  content: props.document,
  editable: false,
  extensions: [StarterKit.configure({
    heading: { levels: [1, 2, 3] },
    code: false,
    codeBlock: false,
    horizontalRule: false,
  })],
  editorProps: { attributes: { class: "published-document" } },
});

function replaceDocument(document) {
  if (editor.value) editor.value.commands.setContent(document, false);
}

watch(() => props.document, replaceDocument, { deep: true });
</script>

<template>
  <EditorContent :editor="editor" />
</template>
