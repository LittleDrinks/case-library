<script setup>
import { watch } from "vue";
import StarterKit from "@tiptap/starter-kit";
import { Extension } from "@tiptap/core";
import { Plugin, PluginKey } from "@tiptap/pm/state";
import { Decoration, DecorationSet } from "@tiptap/pm/view";
import { EditorContent, useEditor } from "@tiptap/vue-3";
import { CitationMark } from "../lib/citation.js";

const props = defineProps({
  document: { type: Object, required: true },
  sources: { type: Array, default: () => [] },
});

const citationNumberKey = new PluginKey("publishedCitationNumbers");

function citationKey(mark) {
  return `${mark.attrs.sourceType}:${mark.attrs.sourceId}`;
}

function sourceNumbers(sources) {
  return new Map(sources.map((source) => [
    `${source.sourceType}:${source.id}`, source.number,
  ]));
}

function citationWidget(number) {
  const element = window.document.createElement("sup");
  element.className = "citation-number";
  element.textContent = `〔${number}〕`;
  element.setAttribute("aria-label", `引用${number}`);
  return element;
}

function appendCitationNumber(decorations, numbers, range) {
  const number = numbers.get(range.key);
  if (number == null) return;
  decorations.push(Decoration.widget(range.end, () => citationWidget(number), {
    side: 1, key: `${range.key}:${range.end}`,
  }));
}

function citationDecorations(document, sources) {
  const numbers = sourceNumbers(sources);
  const decorations = [];
  const active = { key: "", parent: null, end: 0 };
  document.descendants((node, position, parent) => {
    const mark = node.isText ? node.marks.find((item) => item.type.name === "citation") : null;
    const key = mark ? citationKey(mark) : "";
    if (active.key && (active.key !== key || active.parent !== parent)) {
      appendCitationNumber(decorations, numbers, active);
      active.key = "";
    }
    if (key) Object.assign(active, { key, parent, end: position + node.nodeSize });
  });
  if (active.key) appendCitationNumber(decorations, numbers, active);
  return DecorationSet.create(document, decorations);
}

const citationExtension = Extension.create({
  name: "publishedCitationNumbers",
  addProseMirrorPlugins() {
    return [new Plugin({
      key: citationNumberKey,
      state: {
        init: (_, state) => citationDecorations(state.doc, props.sources),
        apply(transaction, previous) {
          const sources = transaction.getMeta(citationNumberKey);
          return sources ? citationDecorations(transaction.doc, sources)
            : transaction.docChanged ? citationDecorations(transaction.doc, props.sources) : previous;
        },
      },
      props: { decorations: (state) => citationNumberKey.getState(state) },
    })];
  },
});

const editor = useEditor({
  content: props.document,
  editable: false,
  extensions: [StarterKit.configure({
    heading: { levels: [1, 2, 3] },
    code: false,
    codeBlock: false,
    horizontalRule: false,
  }), CitationMark, citationExtension],
  editorProps: { attributes: { class: "published-document" } },
});

function refreshCitationNumbers() {
  if (!editor.value) return;
  editor.value.view.dispatch(editor.value.state.tr.setMeta(citationNumberKey, props.sources));
}

function replaceDocument(document) {
  if (editor.value) editor.value.commands.setContent(document, false);
}

watch(() => props.document, replaceDocument, { deep: true });
watch(() => props.sources, refreshCitationNumbers, { deep: true });
</script>

<template>
  <EditorContent :editor="editor" />
</template>
