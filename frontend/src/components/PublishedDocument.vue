<script setup>
import { onMounted, watch } from "vue";
import StarterKit from "@tiptap/starter-kit";
import { EditorContent, useEditor } from "@tiptap/vue-3";
import {
  CitationMark, citationMarkerExtension, refreshCitationMarkers,
} from "../lib/citation.js";

const props = defineProps({
  document: { type: Object, required: true },
  sources: { type: Array, default: () => [] },
});

const editor = useEditor({
  content: props.document,
  editable: false,
  extensions: [StarterKit.configure({
    heading: { levels: [1, 2, 3] },
    code: false,
    codeBlock: false,
    horizontalRule: false,
  }), CitationMark, citationMarkerExtension],
  editorProps: { attributes: { class: "published-document" } },
});

function replaceDocument(document) {
  if (editor.value) editor.value.commands.setContent(document, false);
}

watch(() => props.document, replaceDocument, { deep: true });
watch(() => props.sources, (sources) => refreshCitationMarkers(editor.value, sources), { deep: true });
onMounted(() => refreshCitationMarkers(editor.value, props.sources));
</script>

<template>
  <EditorContent :editor="editor" />
</template>
