<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from "vue";
import StarterKit from "@tiptap/starter-kit";
import { Extension } from "@tiptap/core";
import { Plugin, PluginKey, TextSelection } from "@tiptap/pm/state";
import { Step } from "@tiptap/pm/transform";
import { Decoration, DecorationSet } from "@tiptap/pm/view";
import { EditorContent, useEditor } from "@tiptap/vue-3";
import { CitationMark, createCitationNumbers, refreshCitationNumbers } from "../lib/citation.js";
import EditorToolbar from "./EditorToolbar.vue";

const props = defineProps({
  document: { type: Object, required: true },
  revision: { type: Number, default: 0 },
  editable: { type: Boolean, default: true },
  annotatable: { type: Boolean, default: false },
  annotations: { type: Array, default: () => [] },
  pendingAnchor: { type: Object, default: null },
  sources: { type: Array, default: () => [] },
});
const emit = defineEmits([
  "change", "selection", "writing-context", "annotate", "annotation-click",
]);
const selection = ref(null);
const cursorPlaced = ref(false);
const triggerPosition = ref({ top: "0", left: "0" });
let selectionBlocked = false;
let selectionFrame = 0;
let annotationRefreshPending = false;
let selectedAnnotation = null;
let applyingServerRevision = false;
let revisionEnterTimer = null;
let revisionPreviewGeneration = 0;

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
  const context = { section, quote, from, to, sameBlock };
  return annotationMatchesContext(context) ? { ...context, annotationId: selectedAnnotation.id } : context;
}

function annotationMatchesRange(range) {
  return Boolean(selectedAnnotation && range
    && selectedAnnotation.from === range.from && selectedAnnotation.to === range.to);
}

function annotationMatchesContext(context) {
  return annotationMatchesRange(context) && selectedAnnotation.quote === context.quote;
}

function shouldPreserveAnnotation(activeEditor, context) {
  const domRange = domSelectionRange(activeEditor);
  if (!domRange) return annotationMatchesContext(context);
  return annotationMatchesRange(domRange)
    && (!validSelection(activeEditor) || annotationMatchesContext(context));
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
  cancelSelectionFrame();
  selectionBlocked = true;
  selectedAnnotation = null;
  selection.value = null;
  triggerPosition.value = { top: "0", left: "0" };
  collapseEditorSelection();
  const browserSelection = window.getSelection();
  if (browserSelection?.rangeCount && editor.value?.view.dom.contains(browserSelection.anchorNode)) {
    browserSelection.removeAllRanges();
  }
  flushAnnotationRefresh();
  emit("selection", null);
}

function collapseEditorSelection() {
  const activeEditor = editor.value;
  if (!activeEditor || activeEditor.state.selection.empty) return;
  activeEditor.view.dispatch(activeEditor.state.tr.setSelection(
    TextSelection.near(activeEditor.state.selection.$to),
  ));
}

// 状态观察：原生选区变化先丢弃内部候选，等待编辑器同步后再捕获，不触碰 DOM 选区。
// selectionchange 可能早于编辑器 DOM→state 同步，此刻 state 仍是旧光标；
// 若在此清 DOM 会抹掉用户正在建立的新选区（removeAllRanges 还会再触发 selectionchange）。
function discardSelection(preserveWritingContext = false) {
  if (!preserveWritingContext) selectedAnnotation = null;
  clearCapturedSelection(preserveWritingContext);
}

function clearCapturedSelection(preserveWritingContext = false) {
  selection.value = null;
  triggerPosition.value = { top: "0", left: "0" };
  emit("selection", null);
  if (!preserveWritingContext) emit("writing-context", null);
}

function cancelSelectionFrame() {
  if (!selectionFrame) return;
  cancelAnimationFrame(selectionFrame);
  selectionFrame = 0;
}

function validSelection(activeEditor) {
  const { from, to } = activeEditor.state.selection;
  const { $from, $to } = activeEditor.state.selection;
  return from < to && $from.sameParent($to) && $from.parent.isTextblock;
}

function selectionIsCapturable(activeEditor, context) {
  return props.annotatable && validSelection(activeEditor) && context.quote.trim()
    && !selectionNeedsSync(activeEditor);
}

function validDomSelection(activeEditor, range) {
  if (!range || !props.annotatable || range.from >= range.to) return false;
  const $from = activeEditor.state.doc.resolve(range.from);
  const $to = activeEditor.state.doc.resolve(range.to);
  return $from.sameParent($to) && $from.parent.isTextblock
    && quoteText(activeEditor.state.doc, range.from, range.to).trim();
}

function publishSelection(context) {
  const captured = { ...context, revision: props.revision };
  selection.value = captured;
  emit("selection", captured);
  emit("writing-context", captured);
  positionTrigger(context);
}

function captureSelection({ editor: activeEditor }) {
  const context = currentContext(activeEditor);
  flushAnnotationRefresh(activeEditor);
  const preserveWritingContext = shouldPreserveAnnotation(activeEditor, context);
  if (!selectionIsCapturable(activeEditor, context)) {
    discardSelection(preserveWritingContext);
    return;
  }
  cancelSelectionFrame();
  selectionBlocked = false;
  if (!preserveWritingContext) selectedAnnotation = null;
  clearCapturedSelection(preserveWritingContext);
  publishSelection(context);
}

function domSelectionRange(activeEditor = editor.value) {
  const browserSelection = window.getSelection();
  const anchor = browserSelection?.anchorNode;
  const focus = browserSelection?.focusNode;
  if (!activeEditor || !browserSelection?.rangeCount || browserSelection.isCollapsed) return null;
  if (!anchor || !focus || !activeEditor.view.dom.contains(anchor) || !activeEditor.view.dom.contains(focus)) {
    return null;
  }
  try {
    const anchorPos = activeEditor.view.posAtDOM(anchor, browserSelection.anchorOffset);
    const focusPos = activeEditor.view.posAtDOM(focus, browserSelection.focusOffset);
    return {
      from: Math.min(anchorPos, focusPos), to: Math.max(anchorPos, focusPos),
    };
  } catch { return null; }
}

function editorHasDomSelection() {
  return domSelectionRange() !== null;
}

function selectionNeedsSync(activeEditor) {
  const domRange = domSelectionRange(activeEditor);
  if (!domRange) return false;
  const { from, to } = activeEditor.state.selection;
  return from !== domRange.from || to !== domRange.to;
}

function flushAnnotationRefresh(activeEditor = editor.value) {
  if (!annotationRefreshPending || !activeEditor || selectionNeedsSync(activeEditor)) return;
  refreshAnnotationAnchors(activeEditor);
}

function recaptureSelection() {
  if (!editor.value) return;
  selectionBlocked = false;
  captureSelection({ editor: editor.value });
}

function selectedAnnotationIsValid(activeEditor = editor.value) {
  if (!selectedAnnotation || !activeEditor) return true;
  return props.annotations.some((annotation) => {
    const range = annotationAnchor(annotation, activeEditor.state.doc);
    return annotation.id === selectedAnnotation.id
      && range?.from === selectedAnnotation.from && range?.to === selectedAnnotation.to;
  });
}

function invalidateSelectedAnnotation() {
  const activeEditor = editor.value;
  if (!selectedAnnotation || selectedAnnotationIsValid(activeEditor)) return;
  selectedAnnotation = null;
  if (activeEditor && selectionIsCapturable(activeEditor, currentContext(activeEditor))) {
    recaptureSelection();
    return;
  }
  discardSelection();
}

function scheduleSelectionCapture() {
  cancelSelectionFrame();
  selectionFrame = requestAnimationFrame(() => {
    selectionFrame = 0;
    if (editorHasDomSelection()) recaptureSelection();
  });
}

function preservePendingDomSelection() {
  const activeEditor = editor.value;
  if (!activeEditor || !documentMatches(activeEditor, props.document)) return false;
  const range = domSelectionRange(activeEditor);
  if (!validDomSelection(activeEditor, range) || !selectionNeedsSync(activeEditor)) return false;
  selectionBlocked = true;
  discardSelection();
  scheduleSelectionCapture();
  return true;
}

function handleSelectionChange() {
  const range = domSelectionRange();
  // Selection changes outside the editor (for example focusing the AI
  // composer) do not change the document selection or its annotation link.
  // Editor selection updates and explicit clears still pass through the
  // editor callbacks below.
  if (!range) return;
  discardSelection(annotationMatchesRange(range));
  scheduleSelectionCapture();
}

function currentContext(activeEditor) {
  const { from, to } = activeEditor.state.selection;
  return writingContext(activeEditor, from, to);
}

function documentMatches(activeEditor, document) {
  return JSON.stringify(activeEditor.getJSON()) === JSON.stringify(document);
}

function refreshRevisionSelection() {
  const activeEditor = editor.value;
  if (!activeEditor || selectionBlocked || !documentMatches(activeEditor, props.document)) return false;
  const context = currentContext(activeEditor);
  if (!domSelectionRange(activeEditor) || !selectionIsCapturable(activeEditor, context)) return false;
  const captured = selection.value;
  if (!captured || captured.from !== context.from || captured.to !== context.to
    || captured.quote !== context.quote) {
    captureSelection({ editor: activeEditor });
    return true;
  }
  publishSelection(context);
  return true;
}

function updateEditor({ editor: activeEditor, transaction }) {
  if (applyingServerRevision) return;
  selectionBlocked = true;
  discardSelection();
  emit("change", {
    document: activeEditor.getJSON(),
    steps: transaction.steps.map((step) => step.toJSON()),
  });
  emit("writing-context", currentContext(activeEditor));
}

const annotationKey = new PluginKey("annotationAnchors");
const revisionKey = new PluginKey("revisionSuggestions");

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
function pendingAnchorRange(doc, pending) {
  if (!pending) return null;
  const { from, to } = pending;
  if (!Number.isInteger(from) || !Number.isInteger(to) || from >= to) return null;
  if (to > doc.content.size) return null;
  try {
    return quoteText(doc, from, to) === pending.quote ? { from, to } : null;
  } catch {
    return null;
  }
}

function findTextRange(doc, text, preferredFrom) {
  if (!text) return null;
  let nearest = null;
  doc.descendants((node, position) => {
    if (!node.isTextblock) return;
    const segments = [];
    let cursor = position + 1;
    node.forEach((child) => {
      const value = child.isText ? child.text : child.type.name === "hardBreak" ? "\n" : "";
      if (value) segments.push({ from: cursor, text: value });
      cursor += child.nodeSize;
    });
    const blockText = segments.map((segment) => segment.text).join("");
    let offset = blockText.indexOf(text);
    while (offset >= 0) {
      let consumed = 0;
      let from = null;
      for (const segment of segments) {
        if (offset < consumed + segment.text.length) {
          from = segment.from + offset - consumed;
          break;
        }
        consumed += segment.text.length;
      }
      if (from !== null) {
        const candidate = { from, to: from + text.length };
        const distance = Math.abs(from - preferredFrom);
        if (!nearest || distance < nearest.distance) nearest = { ...candidate, distance };
      }
      offset = blockText.indexOf(text, offset + 1);
    }
  });
  return nearest && { from: nearest.from, to: nearest.to };
}

function annotationMarks(doc, annotations) {
  return annotations.flatMap((annotation) => {
    const range = annotationAnchor(annotation, doc);
    return range ? [Decoration.inline(
      range.from,
      range.to,
      { class: "annotation-anchor", "data-annotation-id": annotation.id },
      { annotationId: annotation.id },
    )] : [];
  });
}

function pendingMarks(doc, pending, previous) {
  const anchor = pendingAnchorRange(doc, pending);
  if (anchor) return [Decoration.inline(
      anchor.from, anchor.to, { class: "pending-anchor" }, { pendingAnchor: true },
    )];
  if (previous && pending) {
    // 正文变化后位置/引文不再匹配：沿映射回迁旧 pending 装饰供审查，不再按旧选区重捕获。
    return previous.find(undefined, undefined, (spec) => spec.pendingAnchor);
  }
  return [];
}

function annotationDecorations(doc, annotations, pending = props.pendingAnchor, previous = null) {
  return DecorationSet.create(doc, [
    ...annotationMarks(doc, annotations), ...pendingMarks(doc, pending, previous),
  ]);
}

function revisionDecorations(doc, state) {
  const decorations = [];
  const preview = state.preview;
  if (preview && pendingAnchorRange(doc, preview)) {
    decorations.push(Decoration.inline(preview.from, preview.to, {
      class: preview.phase === "leaving"
        ? "revision-preview-old leaving" : "revision-preview-old",
    }, { revisionPreview: true }));
    decorations.push(Decoration.widget(preview.to, () => {
      const node = window.document.createElement("span");
      node.className = "revision-preview-new";
      node.textContent = preview.replacement;
      return node;
    }, { side: 1, key: `revision-preview-${preview.id}` }));
  }
  const entered = state.entered;
  if (entered && entered.from < entered.to && entered.to <= doc.content.size) {
    decorations.push(Decoration.inline(entered.from, entered.to, {
      class: "revision-applied-new",
    }, { revisionApplied: true }));
  }
  return DecorationSet.create(doc, decorations);
}

function applyRevisionDecorations(transaction, previous) {
  const meta = transaction.getMeta(revisionKey);
  if (meta) {
    const next = {
      preview: Object.hasOwn(meta, "preview") ? meta.preview : previous.preview,
      entered: Object.hasOwn(meta, "entered") ? meta.entered : previous.entered,
    };
    return { ...next, decorations: revisionDecorations(transaction.doc, next) };
  }
  let preview = previous.preview;
  let entered = previous.entered;
  if (transaction.docChanged) {
    if (preview) {
      const from = transaction.mapping.map(preview.from, 1);
      const to = transaction.mapping.map(preview.to, -1);
      preview = from < to && quoteText(transaction.doc, from, to) === preview.quote
        ? { ...preview, from, to } : null;
    }
    if (entered) {
      const from = transaction.mapping.map(entered.from, -1);
      const to = transaction.mapping.map(entered.to, 1);
      entered = from < to ? { ...entered, from, to } : null;
    }
  }
  const next = { preview, entered };
  return { ...next, decorations: revisionDecorations(transaction.doc, next) };
}

const revisionExtension = Extension.create({
  name: "revisionSuggestions",
  addProseMirrorPlugins() {
    return [new Plugin({
      key: revisionKey,
      state: {
        init: (_, state) => {
          const value = { preview: null, entered: null };
          return { ...value, decorations: revisionDecorations(state.doc, value) };
        },
        apply: applyRevisionDecorations,
      },
      props: { decorations: (state) => revisionKey.getState(state)?.decorations },
    })];
  },
});

function waitForScrollToSettle(container) {
  if (!container) return Promise.resolve();
  return new Promise((resolve) => {
    let idleTimer;
    const finish = () => {
      window.clearTimeout(idleTimer);
      window.clearTimeout(maxTimer);
      container.removeEventListener("scroll", onScroll);
      resolve();
    };
    const onScroll = () => {
      window.clearTimeout(idleTimer);
      idleTimer = window.setTimeout(finish, 120);
    };
    const maxTimer = window.setTimeout(finish, 1800);
    container.addEventListener("scroll", onScroll, { passive: true });
    onScroll();
  });
}

async function previewRevision(target) {
  const generation = ++revisionPreviewGeneration;
  const activeEditor = editor.value;
  if (!activeEditor || (!props.editable && !target.locateOnly)) return false;
  const doc = activeEditor.state.doc;
  const currentRange = target.locateOnly
    ? findTextRange(doc, target.status === "accepted" ? target.replacement : target.quote, target.from)
      || findTextRange(doc, target.replacement, target.from)
    : pendingAnchorRange(doc, target);
  if (!currentRange) return false;
  const position = currentRange.from;
  activeEditor.view.dispatch(activeEditor.state.tr.setMeta(revisionKey, { preview: null, entered: null }));
  try {
    let element = activeEditor.view.domAtPos(position).node;
    if (element.nodeType !== Node.ELEMENT_NODE) element = element.parentElement;
    const block = element?.closest("p, h1, h2, h3, li");
    if (block?.scrollIntoView) {
      const scrollComplete = waitForScrollToSettle(activeEditor.view.dom.closest(".canvas-column"));
      block.scrollIntoView({ behavior: "smooth", block: "center" });
      await scrollComplete;
    }
  } catch { /* Decoration still provides the preview if scrolling is unavailable. */ }
  if (generation !== revisionPreviewGeneration) return false;
  if (target.locateOnly) return true;
  if (!isRevisionCurrent(target)) return false;
  activeEditor.view.dispatch(activeEditor.state.tr.setMeta(revisionKey, {
    preview: { ...target, phase: "preview" }, entered: null,
  }));
  return true;
}

function clearRevisionPreview() {
  revisionPreviewGeneration += 1;
  const activeEditor = editor.value;
  if (!activeEditor) return;
  activeEditor.view.dispatch(activeEditor.state.tr.setMeta(revisionKey, {
    preview: null, entered: null,
  }));
}

function isRevisionCurrent(target) {
  const activeEditor = editor.value;
  return Boolean(activeEditor && pendingAnchorRange(activeEditor.state.doc, target));
}

async function applyRevisionSteps(steps, target) {
  revisionPreviewGeneration += 1;
  const activeEditor = editor.value;
  if (!activeEditor || !isRevisionCurrent(target) || !Array.isArray(steps) || !steps.length) {
    return false;
  }
  const preview = { ...target, phase: "leaving" };
  activeEditor.view.dispatch(activeEditor.state.tr.setMeta(revisionKey, { preview }));
  await new Promise((resolve) => window.setTimeout(resolve, 180));
  if (!isRevisionCurrent(target)) {
    clearRevisionPreview();
    return false;
  }
  let transaction = activeEditor.state.tr;
  try {
    for (const step of steps) transaction = transaction.step(Step.fromJSON(activeEditor.state.schema, step));
  } catch {
    clearRevisionPreview();
    return false;
  }
  const from = transaction.mapping.map(target.from, -1);
  const to = transaction.mapping.map(target.to, 1);
  if (quoteText(transaction.doc, from, to) !== target.replacement) {
    clearRevisionPreview();
    return false;
  }
  transaction.setMeta(revisionKey, { preview: null, entered: { from, to } });
  clearSelection();
  applyingServerRevision = true;
  try {
    activeEditor.view.dispatch(transaction);
  } finally {
    applyingServerRevision = false;
  }
  if (revisionEnterTimer) window.clearTimeout(revisionEnterTimer);
  revisionEnterTimer = window.setTimeout(() => {
    if (editor.value) editor.value.view.dispatch(editor.value.state.tr.setMeta(revisionKey, { entered: null }));
    revisionEnterTimer = null;
  }, 900);
  return true;
}

function applyAnnotationAnchors(transaction, previous) {
  const meta = transaction.getMeta(annotationKey);
  if (meta !== undefined) {
    return annotationDecorations(transaction.doc, meta.annotations, meta.pending, previous);
  }
  return remapDecorations(previous, transaction);
}

function remapDecorations(previous, transaction) {
  const mapped = previous.map(transaction.mapping, transaction.doc);
  if (!transaction.docChanged) return mapped;
  // DecorationSet.map 已完成位置映射与删除合并；此处只在映射后坐标校验原引文：
  // 同一引文偏移（如前置插入）→ 保留，保存门禁可过；引文被改写 → pending 失效丢弃。
  const quote = props.pendingAnchor?.quote;
  const kept = mapped.find().filter((decoration) => {
    if (!decoration.spec.pendingAnchor) return true;
    try {
      return transaction.doc.textBetween(decoration.from, decoration.to, "\n", "\n") === quote;
    } catch {
      return false;
    }
  });
  return kept.length === mapped.find().length
    ? mapped
    : DecorationSet.create(transaction.doc, kept);
}

function pendingDecoration() {
  const decorations = annotationKey.getState(editor.value?.state)?.find() || [];
  return decorations.find((decoration) => decoration.spec.pendingAnchor);
}

function getPendingAnchor() {
  if (!editor.value || !props.pendingAnchor) return null;
  const decoration = pendingDecoration();
  if (!decoration) return null;
  const quote = quoteText(editor.value.state.doc, decoration.from, decoration.to);
  return quote === props.pendingAnchor.quote
    ? { from: decoration.from, to: decoration.to, quote }
    : null;
}

function clickedAnnotation(view, position) {
  const decorations = annotationKey.getState(view.state)?.find(position, position + 1) || [];
  return decorations.find((decoration) => decoration.spec.annotationId)?.spec.annotationId;
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
  if (selectionNeedsSync(activeEditor)) {
    annotationRefreshPending = true;
    return;
  }
  annotationRefreshPending = false;
  const transaction = activeEditor.state.tr.setMeta(
    annotationKey, { annotations: props.annotations, pending: props.pendingAnchor },
  );
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
  }), CitationMark, annotationExtension, revisionExtension,
  createCitationNumbers(() => props.sources)],
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
  if (documentMatches(editor.value, document)) return;
  selectionBlocked = true;
  clearSelection();
  cursorPlaced.value = false;
  editor.value.commands.setContent(document, false);
}

watch(() => props.document, replaceDocument, { deep: true });
watch(() => props.editable, (editable) => editor.value?.setEditable(editable, false));
watch(() => props.annotations, () => {
  invalidateSelectedAnnotation();
  refreshAnnotationAnchors();
}, { deep: true });
watch(() => props.pendingAnchor, () => refreshAnnotationAnchors());
watch(() => props.sources, () => refreshCitationNumbers(editor.value, props.sources), { deep: true });
watch(() => props.annotatable, (value) => {
  if (value) return;
  selectionBlocked = true;
  clearSelection();
});
watch(() => props.revision, () => {
  if (refreshRevisionSelection()) return;
  if (preservePendingDomSelection()) return;
  selectionBlocked = true;
  clearSelection();
});
onMounted(() => {
  if (!editor.value) return;
  window.document.addEventListener("selectionchange", handleSelectionChange);
  captureSelection({ editor: editor.value });
  refreshAnnotationAnchors();
});
onBeforeUnmount(() => {
  cancelSelectionFrame();
  if (revisionEnterTimer) window.clearTimeout(revisionEnterTimer);
  window.document.removeEventListener("selectionchange", handleSelectionChange);
});

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

function selectAnnotation(annotation) {
  const activeEditor = editor.value;
  if (!activeEditor || annotation.anchorState === "deleted" || annotation.anchorState === "changed") return false;
  const range = pendingAnchorRange(activeEditor.state.doc, annotation);
  if (!range) return false;
  selectedAnnotation = { id: annotation.id, from: range.from, to: range.to, quote: annotation.quote };
  activeEditor.chain().setTextSelection(range).focus().scrollIntoView().run();
  return true;
}

defineExpose({
  selectAnnotation, clearSelection, recaptureSelection, insertCitation, getPendingAnchor,
  previewRevision, clearRevisionPreview, isRevisionCurrent, applyRevisionSteps,
});
</script>

<template>
  <Teleport to="#workbench-format-toolbar">
    <EditorToolbar v-if="editable" :editor="editor" />
  </Teleport>
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
