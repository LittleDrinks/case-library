<script setup>
import { Node } from "@tiptap/core";
import StarterKit from "@tiptap/starter-kit";
import { EditorContent, useEditor, VueNodeViewRenderer } from "@tiptap/vue-3";
import { watch } from "vue";
import PromptTokenNodeViewPrototype from "./PromptTokenNodeViewPrototype.vue";

const props = defineProps({ modelValue: { type: Array, required: true } });
const emit = defineEmits(["update:modelValue"]);

const PromptToken = Node.create({
  name: "promptToken",
  group: "inline",
  inline: true,
  atom: true,
  selectable: true,
  addAttributes() {
    return Object.fromEntries(["partId", "tokenType", "resourceId", "skillId", "kind", "label", "version"].map((name) => [name, { default: "" }]));
  },
  parseHTML() { return [{ tag: "span[data-prompt-token]" }]; },
  renderHTML({ HTMLAttributes }) { return ["span", { ...HTMLAttributes, "data-prompt-token": "" }]; },
  addNodeView() { return VueNodeViewRenderer(PromptTokenNodeViewPrototype); },
});

function tokenAttrs(part) {
  return {
    partId: part.id, tokenType: part.type, resourceId: part.resourceId || "",
    skillId: part.skillId || "", kind: part.kind || "", label: part.label,
    version: part.version || "",
  };
}

function inlineNode(part) {
  if (part.type === "text") return part.text ? { type: "text", text: part.text } : null;
  return { type: "promptToken", attrs: tokenAttrs(part) };
}

function documentFromParts(parts) {
  const content = parts.map(inlineNode).filter(Boolean);
  return { type: "doc", content: [{ type: "paragraph", ...(content.length ? { content } : {}) }] };
}

function textPart(text) {
  return { type: "text", id: `text-${Date.now()}-${Math.random()}`, text };
}

function partFromNode(node) {
  if (node.type === "text") return textPart(node.text || "");
  if (node.type === "hardBreak") return textPart("\n");
  const attrs = node.attrs || {};
  if (attrs.tokenType === "skill") return { type: "skill", id: attrs.partId, skillId: attrs.skillId, label: attrs.label, version: attrs.version };
  return { type: "context", id: attrs.partId, resourceId: attrs.resourceId, label: attrs.label, kind: attrs.kind };
}

function partsFromDocument(document) {
  const blocks = document.content || [];
  const parts = blocks.flatMap((block, index) => [
    ...(index ? [textPart("\n")] : []), ...(block.content || []).map(partFromNode),
  ]);
  return parts.length ? parts : [textPart("")];
}

function updateParts({ editor: activeEditor }) {
  emit("update:modelValue", partsFromDocument(activeEditor.getJSON()));
}

const editor = useEditor({
  content: documentFromParts(props.modelValue),
  extensions: [StarterKit.configure({ code: false, codeBlock: false, heading: false }), PromptToken],
  editorProps: { attributes: { class: "structured-prompt-surface", spellcheck: "false" } },
  onUpdate: updateParts,
});

function sameDocument(parts) {
  return JSON.stringify(documentFromParts(parts)) === JSON.stringify(editor.value?.getJSON());
}

watch(() => props.modelValue, (parts) => {
  if (!editor.value || sameDocument(parts)) return;
  editor.value.commands.setContent(documentFromParts(parts), false);
}, { deep: true });

function insertToken(part) {
  editor.value?.chain().focus().insertContent({ type: "promptToken", attrs: tokenAttrs(part) }).run();
}

function insertContext(item) {
  insertToken({ type: "context", id: `token-${item.id}-${Date.now()}`, resourceId: item.id, label: item.label, kind: item.kind });
}

function insertSkill(item) {
  if (props.modelValue.some((part) => part.type === "skill" && part.skillId === item.id)) return;
  insertToken({ type: "skill", id: `skill-${item.id}-${Date.now()}`, skillId: item.id, label: item.label, version: item.version });
}

defineExpose({ insertContext, insertSkill });
</script>

<template>
  <EditorContent :editor="editor" class="structured-prompt-editor" aria-label="向 Agent 提问" />
</template>
