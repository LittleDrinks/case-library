<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from "vue";
import StarterKit from "@tiptap/starter-kit";
import { Extension } from "@tiptap/core";
import { Plugin, PluginKey } from "@tiptap/pm/state";
import { Decoration, DecorationSet } from "@tiptap/pm/view";
import { EditorContent, useEditor } from "@tiptap/vue-3";
import { hashQuote } from "../lib/annotationAnchor.js";
import EditorToolbar from "./EditorToolbar.vue";

const props = defineProps({
  document: { type: Object, required: true },
  revision: { type: Number, default: 0 },
  editable: { type: Boolean, default: true },
  annotatable: { type: Boolean, default: false },
  candidatePreviews: { type: Array, default: () => [] },
  annotations: { type: Array, default: () => [] },
});
const emit = defineEmits(["change", "selection", "writing-context", "annotate"]);
const selection = ref(null);
const triggerPosition = ref({ top: "0", left: "0" });
let selectionBlocked = false;
let selectionRequest = 0;

function isSectionHeading(node) {
  return node.type.name === "heading" && [1, 2].includes(node.attrs.level);
}

function sections(document) {
  const rows = [{ section: "正文", headingFrom: 0, sectionFrom: 0 }];
  document.forEach((node, offset) => {
    if (!isSectionHeading(node)) return;
    rows.push({
      section: node.textContent.trim() || "未命名小节",
      headingFrom: offset, sectionFrom: offset + node.nodeSize,
    });
  });
  return rows.map((row, index) => ({
    ...row, sectionTo: rows[index + 1]?.headingFrom ?? document.content.size,
  }));
}

function sectionAt(document, position) {
  return sections(document).filter((row) => row.headingFrom <= position).at(-1);
}

function writingContext(activeEditor, from, to) {
  const section = sectionAt(activeEditor.state.doc, from);
  const quote = activeEditor.state.doc.textBetween(from, to, " ");
  const sectionText = activeEditor.state.doc
    .textBetween(section.sectionFrom, section.sectionTo, "\n").trim();
  return { ...section, quote, from, to, sectionText };
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
  selectionRequest += 1;
  selection.value = null;
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
    clearSelection();
    emit("writing-context", context);
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

function updateEditor({ editor: activeEditor }) {
  selectionBlocked = true;
  clearSelection();
  emit("change", activeEditor.getJSON());
  emit("writing-context", currentContext(activeEditor));
}

function previewRange(candidate) {
  if (candidate.mode === "replace-selection") {
    return { from: candidate.context.from, to: candidate.context.to, removed: true };
  }
  if (candidate.mode === "replace-section") {
    return { from: candidate.context.sectionFrom, to: candidate.context.sectionTo, removed: true };
  }
  return { from: candidate.context.sectionTo, to: candidate.context.sectionTo, removed: false };
}

function previewWidget(candidate) {
  const wrapper = window.document.createElement("span");
  wrapper.className = "candidate-inline-preview";
  const added = window.document.createElement("ins");
  added.textContent = candidate.mode === "new-section"
    ? `补充\n${candidate.text}` : candidate.text;
  const reason = window.document.createElement("small");
  reason.textContent = `修改理由：${candidate.reason}`;
  wrapper.append(added, reason);
  return wrapper;
}

function candidateDecorations(candidate, index) {
  const range = previewRange(candidate);
  const decorations = [Decoration.widget(
    range.to, () => previewWidget(candidate), { key: String(candidate.id), side: index + 1 },
  )];
  if (range.removed && range.from < range.to) {
    decorations.unshift(Decoration.inline(range.from, range.to, { class: "candidate-inline-removed" }));
  }
  return decorations;
}

function previewDecorations(document, candidates) {
  const pending = candidates.filter((item) => item.status === "pending");
  if (!pending.length) return DecorationSet.empty;
  return DecorationSet.create(document, pending.flatMap(candidateDecorations));
}

const candidatePreviewKey = new PluginKey("candidatePreview");

function applyCandidatePreviews(transaction, previous) {
  const candidates = transaction.getMeta(candidatePreviewKey);
  if (candidates !== undefined) return previewDecorations(transaction.doc, candidates);
  return previous.map(transaction.mapping, transaction.doc);
}

const candidateExtension = Extension.create({
  name: "candidatePreview",
  addProseMirrorPlugins() {
    return [new Plugin({
      key: candidatePreviewKey,
      state: { init: () => DecorationSet.empty, apply: applyCandidatePreviews },
      props: { decorations: (state) => candidatePreviewKey.getState(state) },
    })];
  },
});

const annotationKey = new PluginKey("annotationAnchors");

function annotationAnchor(annotation, document) {
  if (annotation.revision !== props.revision) return null;
  const { from, to } = annotation;
  if (!Number.isInteger(from) || !Number.isInteger(to) || from >= to) return null;
  return document.textBetween(from, to, " ") === annotation.quote
    ? { from, to } : null;
}

function annotationDecorations(document, annotations) {
  return DecorationSet.create(document, annotations.flatMap((annotation) => {
    const range = annotationAnchor(annotation, document);
    return range ? [Decoration.inline(range.from, range.to, { class: "annotation-anchor" })] : [];
  }));
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
      props: { decorations: (state) => annotationKey.getState(state) },
    })];
  },
});

function refreshAnnotationAnchors() {
  if (!editor.value) return;
  const transaction = editor.value.state.tr.setMeta(annotationKey, props.annotations);
  editor.value.view.dispatch(transaction);
}

const editor = useEditor({
  content: props.document,
  editable: props.editable,
  extensions: [StarterKit.configure({
    heading: { levels: [1, 2, 3] },
    code: false,
    codeBlock: false,
    horizontalRule: false,
  }), candidateExtension, annotationExtension],
  editorProps: { attributes: { class: "canvas-editor", spellcheck: "false" } },
  onUpdate: updateEditor,
  onCreate: captureSelection,
  onSelectionUpdate: captureSelection,
});

function paragraphNodes(activeEditor, text) {
  const rows = text.split(/\n+/).map((row) => row.trim()).filter(Boolean);
  return rows.map((row) => activeEditor.schema.nodes.paragraph.create(
    null, activeEditor.schema.text(row),
  ));
}

function assertCurrent(activeEditor, candidate) {
  const { context, mode } = candidate;
  const range = mode === "replace-selection"
    ? [context.from, context.to, context.quote]
    : [context.sectionFrom, context.sectionTo, context.sectionText];
  const current = activeEditor.state.doc.textBetween(range[0], range[1], "\n").trim();
  if (current !== range[2].trim()) throw new Error("目标正文已变化，请重新生成修订。");
}

function replacementNodes(activeEditor, candidate) {
  const nodes = paragraphNodes(activeEditor, candidate.text);
  if (candidate.mode !== "new-section") return nodes;
  const heading = activeEditor.schema.nodes.heading.create(
    { level: 2 }, activeEditor.schema.text("补充"),
  );
  return [heading, ...nodes];
}

function applyCandidate(candidate) {
  const activeEditor = editor.value;
  if (!activeEditor) throw new Error("正文编辑器尚未就绪。");
  assertCurrent(activeEditor, candidate);
  const { context, mode } = candidate;
  if (mode === "replace-selection") {
    activeEditor.chain().insertContentAt(
      { from: context.from, to: context.to }, candidate.text.replace(/\s*\n+\s*/g, " "),
    ).run();
  } else {
    const from = mode === "replace-section" ? context.sectionFrom : context.sectionTo;
    const to = mode === "replace-section" ? context.sectionTo : context.sectionTo;
    activeEditor.chain().insertContentAt(
      { from, to }, replacementNodes(activeEditor, candidate).map((node) => node.toJSON()),
    ).run();
  }
  return activeEditor.getJSON();
}

function replaceDocument(document) {
  if (!editor.value) return;
  const current = JSON.stringify(editor.value.getJSON());
  if (current === JSON.stringify(document)) return;
  selectionBlocked = true;
  clearSelection();
  editor.value.commands.setContent(document, false);
}

watch(() => props.document, replaceDocument, { deep: true });
watch(() => props.editable, (editable) => editor.value?.setEditable(editable, false));
function refreshCandidatePreviews() {
  if (!editor.value) return;
  const transaction = editor.value.state.tr.setMeta(candidatePreviewKey, props.candidatePreviews);
  editor.value.view.dispatch(transaction);
}

watch(() => props.candidatePreviews, refreshCandidatePreviews, { deep: true });
watch(() => props.annotations, refreshAnnotationAnchors, { deep: true });
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
  refreshCandidatePreviews();
  refreshAnnotationAnchors();
});
onBeforeUnmount(() => window.document.removeEventListener("selectionchange", handleSelectionChange));
defineExpose({ applyCandidate, recaptureSelection });
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
