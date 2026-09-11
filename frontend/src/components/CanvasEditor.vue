<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from "vue";
import StarterKit from "@tiptap/starter-kit";
import { Extension } from "@tiptap/core";
import { Plugin, PluginKey } from "@tiptap/pm/state";
import { Decoration, DecorationSet } from "@tiptap/pm/view";
import { EditorContent, useEditor } from "@tiptap/vue-3";
import { hashQuote } from "../lib/annotationAnchor.js";
import { CitationMark, createCitationNumbers, refreshCitationNumbers } from "../lib/citation.js";
import EditorToolbar from "./EditorToolbar.vue";

const props = defineProps({
  document: { type: Object, required: true },
  revision: { type: Number, default: 0 },
  editable: { type: Boolean, default: true },
  annotatable: { type: Boolean, default: false },
  annotations: { type: Array, default: () => [] },
  sources: { type: Array, default: () => [] },
});
const emit = defineEmits([
  "change", "selection", "writing-context", "annotate", "annotation-click",
]);
const selection = ref(null);
const cursorPlaced = ref(false);
const triggerPosition = ref({ top: "0", left: "0" });
let selectionBlocked = false;
let selectionRequest = 0;

function sectionName(activeEditor, position) {
  let section = "正文";
  activeEditor.state.doc.nodesBetween(0, position, (node) => {
    if (node.type.name === "heading" && [1, 2].includes(node.attrs.level)) {
      section = node.textContent.trim() || "未命名小节";
    }
  });
  return section;
}

function writingContext(activeEditor, from, to) {
  const section = sectionName(activeEditor, from);
  const quote = quoteText(activeEditor.state.doc, from, to);
  const sameBlock = activeEditor.state.doc.resolve(from).sameParent(activeEditor.state.doc.resolve(to));
  return { section, quote, from, to, sameBlock };
}

function positionTrigger(context) {
  const paper = window.document.querySelector(".document-paper")?.getBoundingClientRect();
  let box;
  try { box = editor.value?.view.coordsAtPos(context.to); }
  catch { return; }
  if (!box || !paper) return;
  triggerPosition.value = { top: `${box.bottom - paper.top + 6}px`, left: `${box.left - paper.left}px` };
}

function clearSelection() {
  selectionBlocked = true;
  selectionRequest += 1;
  selection.value = null;
  triggerPosition.value = { top: "0", left: "0" };
  const browserSelection = window.getSelection();
  if (browserSelection?.rangeCount && editor.value?.view.dom.contains(browserSelection.anchorNode)) {
    browserSelection.removeAllRanges();
  }
  emit("selection", null);
}

// 状态观察：选区无效时只丢弃内部候选并使悬挂的异步捕获失效，不触碰 DOM 选区。
// selectionchange 可能早于编辑器 DOM→state 同步，此刻 state 仍是旧光标；
// 若在此清 DOM 会抹掉用户正在建立的新选区（removeAllRanges 还会再触发 selectionchange）。
// 但必须自增 request：否则悬挂的旧 hashQuote 完成后会把过期选区写回（绕过 null 观察）。
function discardSelection() {
  selectionRequest += 1;
  selection.value = null;
  triggerPosition.value = { top: "0", left: "0" };
  emit("selection", null);
}

function validSelection(activeEditor) {
  const { from, to } = activeEditor.state.selection;
  const { $from, $to } = activeEditor.state.selection;
  return from < to && $from.sameParent($to) && $from.parent.isTextblock;
}

async function captureSelection({ editor: activeEditor }) {
  const { from, to } = activeEditor.state.selection;
  const context = writingContext(activeEditor, from, to);
  if (!props.annotatable || !validSelection(activeEditor) || !context.quote.trim()) {
    discardSelection();
    emit("writing-context", null);
    return;
  }
  selectionBlocked = false;
  const request = ++selectionRequest;
  const quoteHash = await hashQuote(context.quote);
  if (request !== selectionRequest || selectionBlocked) return;
  const captured = { ...context, revision: props.revision, quoteHash };
  selection.value = captured;
  emit("selection", captured);
  emit("writing-context", captured);
  positionTrigger(context);
}

function editorHasDomSelection() {
  const browserSelection = window.getSelection();
  const anchor = browserSelection?.anchorNode;
  const focus = browserSelection?.focusNode;
  return Boolean(
    browserSelection?.rangeCount && !browserSelection.isCollapsed
    && anchor && focus && editor.value?.view.dom.contains(anchor)
    && editor.value.view.dom.contains(focus),
  );
}

async function recaptureSelection() {
  if (!editor.value) return;
  selectionBlocked = false;
  await captureSelection({ editor: editor.value });
}

function handleSelectionChange() {
  if (!editorHasDomSelection()) return;
  void recaptureSelection();
}

function currentContext(activeEditor) {
  const { from, to } = activeEditor.state.selection;
  return writingContext(activeEditor, from, to);
}

function updateEditor({ editor: activeEditor, transaction }) {
  selectionBlocked = true;
  discardSelection();
  emit("change", {
    document: activeEditor.getJSON(),
    steps: transaction.steps.map((step) => step.toJSON()),
  });
  emit("writing-context", currentContext(activeEditor));
}

const annotationKey = new PluginKey("annotationAnchors");

function quoteText(doc, from, to) {
  return doc.textBetween(from, to, "\n", "\n");
}

function annotationAnchor(annotation, doc) {
  if (annotation.status === "resolved") return null;
  if (annotation.anchorState && annotation.anchorState !== "active") return null;
  const { from, to } = annotation;
  if (!Number.isInteger(from) || !Number.isInteger(to) || from >= to) return null;
  return quoteText(doc, from, to) === annotation.quote
    ? { from, to } : null;
}

function annotationDecorations(doc, annotations) {
  return DecorationSet.create(doc, annotations.flatMap((annotation) => {
    const range = annotationAnchor(annotation, doc);
    return range ? [Decoration.inline(
      range.from,
      range.to,
      { class: "annotation-anchor", "data-annotation-id": annotation.id },
      { annotationId: annotation.id },
    )] : [];
  }));
}

function clickedAnnotation(view, position) {
  const decorations = annotationKey.getState(view.state)?.find(position, position + 1) || [];
  return decorations.find((decoration) => decoration.spec.annotationId)?.spec.annotationId;
}

function applyAnnotationAnchors(transaction, previous) {
  const annotations = transaction.getMeta(annotationKey);
  if (annotations !== undefined) return annotationDecorations(transaction.doc, annotations);
  return previous.map(transaction.mapping, transaction.doc);
}

const annotationExtension = Extension.create({
  name: "annotationAnchors",
  addProseMirrorPlugins() {
    return [new Plugin({
      key: annotationKey,
      state: { init: () => DecorationSet.empty, apply: applyAnnotationAnchors },
      props: {
        decorations: (state) => annotationKey.getState(state),
        handleClick: (view, position) => {
          const annotationId = clickedAnnotation(view, position);
          if (!annotationId) return false;
          emit("annotation-click", annotationId);
          return true;
        },
      },
    })];
  },
});

function refreshAnnotationAnchors(activeEditor = editor.value) {
  if (!activeEditor) return;
  const transaction = activeEditor.state.tr.setMeta(annotationKey, props.annotations);
  activeEditor.view.dispatch(transaction);
}

const editor = useEditor({
  content: props.document,
  editable: props.editable,
  extensions: [StarterKit.configure({
    heading: { levels: [1, 2, 3] },
    code: false,
    codeBlock: false,
    horizontalRule: false,
  }), CitationMark, annotationExtension, createCitationNumbers(() => props.sources)],
  editorProps: { attributes: { class: "canvas-editor", spellcheck: "false" } },
  onUpdate: updateEditor,
  onCreate: (context) => {
    captureSelection(context);
    refreshAnnotationAnchors(context.editor);
  },
  onSelectionUpdate: captureSelection,
  onFocus: () => { cursorPlaced.value = true; },
});

function replaceDocument(document) {
  if (!editor.value) return;
  const current = JSON.stringify(editor.value.getJSON());
  if (current === JSON.stringify(document)) return;
  selectionBlocked = true;
  clearSelection();
  cursorPlaced.value = false;
  editor.value.commands.setContent(document, false);
}

watch(() => props.document, replaceDocument, { deep: true });
watch(() => props.editable, (editable) => editor.value?.setEditable(editable, false));
watch(() => props.annotations, () => refreshAnnotationAnchors(), { deep: true });
watch(() => props.sources, () => refreshCitationNumbers(editor.value, props.sources), { deep: true });
watch(() => props.annotatable, (value) => {
  if (value) return;
  selectionBlocked = true;
  clearSelection();
});
watch(() => props.revision, () => {
  selectionBlocked = true;
  clearSelection();
});
onMounted(() => {
  if (!editor.value) return;
  window.document.addEventListener("selectionchange", handleSelectionChange);
  captureSelection({ editor: editor.value });
  refreshAnnotationAnchors();
});
onBeforeUnmount(() => window.document.removeEventListener("selectionchange", handleSelectionChange));

// 资料区发起插入：有选区时把选区关联来源，否则在当前光标处落一个引用锚点。
function insertCitation(source) {
  if (!props.editable || !editor.value) return "readonly";
  const { selection } = editor.value.state;
  const attrs = { sourceType: source.sourceType, sourceId: source.id };
  if (!selection.empty) {
    return editor.value.chain().focus().setMark("citation", attrs).run() ? "linked" : "unpositioned";
  }
  if (!cursorPlaced.value || !selection.$from.parent.inlineContent) return "unpositioned";
  const inserted = editor.value.chain().focus().insertContent({
    type: "text", text: "\u200B", marks: [{ type: "citation", attrs }],
  }).run();
  return inserted ? "inserted" : "unpositioned";
}

defineExpose({ clearSelection, recaptureSelection, insertCitation });
</script>

<template>
  <EditorToolbar v-if="editable" :editor="editor" />
  <button
    v-if="selection"
    class="annotation-trigger"
    type="button"
    :style="triggerPosition"
    aria-label="添加选区批注"
    @mousedown.prevent
    @click="emit('annotate')"
  >+ 批注</button>
  <EditorContent :editor="editor" />
</template>
