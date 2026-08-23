<script setup>
import { onMounted, ref, watch } from "vue";
import StarterKit from "@tiptap/starter-kit";
import { Extension } from "@tiptap/core";
import { Plugin, PluginKey } from "@tiptap/pm/state";
import { Decoration, DecorationSet } from "@tiptap/pm/view";
import { EditorContent, useEditor } from "@tiptap/vue-3";
import EditorToolbar from "./EditorToolbar.vue";

const props = defineProps({
  document: { type: Object, required: true },
  editable: { type: Boolean, default: true },
  annotatable: { type: Boolean, default: false },
  candidatePreviews: { type: Array, default: () => [] },
});
const emit = defineEmits(["change", "selection", "writing-context", "annotate"]);
const selection = ref(null);
const triggerPosition = ref({ top: "0", left: "0" });

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

function positionTrigger() {
  const range = window.getSelection()?.rangeCount && window.getSelection().getRangeAt(0);
  const paper = window.document.querySelector(".document-paper")?.getBoundingClientRect();
  if (!range || !paper) return;
  const box = range.getBoundingClientRect();
  triggerPosition.value = { top: `${box.bottom - paper.top + 6}px`, left: `${box.left - paper.left}px` };
}

function captureSelection({ editor: activeEditor }) {
  const { from, to } = activeEditor.state.selection;
  const context = writingContext(activeEditor, from, to);
  const quote = context.quote.trim();
  selection.value = props.annotatable && quote ? { quote, section: context.section } : null;
  emit("selection", selection.value);
  emit("writing-context", context);
  if (selection.value) window.requestAnimationFrame(positionTrigger);
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

function updateEditor({ editor: activeEditor }) {
  emit("change", activeEditor.getJSON());
  captureSelection({ editor: activeEditor });
}

const editor = useEditor({
  content: props.document,
  editable: props.editable,
  extensions: [StarterKit.configure({
    heading: { levels: [1, 2, 3] },
    code: false,
    codeBlock: false,
    horizontalRule: false,
  }), candidateExtension],
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
  if (current !== JSON.stringify(document)) editor.value.commands.setContent(document, false);
}

watch(() => props.document, replaceDocument, { deep: true });
watch(() => props.editable, (editable) => editor.value?.setEditable(editable, false));
function refreshCandidatePreviews() {
  if (!editor.value) return;
  const transaction = editor.value.state.tr.setMeta(candidatePreviewKey, props.candidatePreviews);
  editor.value.view.dispatch(transaction);
}

watch(() => props.candidatePreviews, refreshCandidatePreviews, { deep: true });
watch(() => props.annotatable, (value) => {
  if (value) return;
  selection.value = null;
  emit("selection", null);
});
onMounted(() => {
  if (!editor.value) return;
  captureSelection({ editor: editor.value });
  refreshCandidatePreviews();
});
defineExpose({ applyCandidate });
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
