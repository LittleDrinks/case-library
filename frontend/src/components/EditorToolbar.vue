<script setup>
import { Bold, Heading2, List, ListOrdered, Pilcrow, Redo2, Undo2 } from "@lucide/vue";
import { sourceKey } from "../lib/citation.js";

const props = defineProps({
  editor: { type: Object, default: null },
  sources: { type: Array, default: () => [] },
});

const tools = [
  { name: "bold", title: "加粗", icon: Bold, run: (editor) => editor.chain().focus().toggleBold().run() },
  { name: "heading", title: "二级标题", icon: Heading2, run: (editor) => editor.chain().focus().toggleHeading({ level: 2 }).run() },
  { name: "paragraph", title: "正文", icon: Pilcrow, run: (editor) => editor.chain().focus().setParagraph().run() },
  { name: "bulletList", title: "项目列表", icon: List, run: (editor) => editor.chain().focus().toggleBulletList().run() },
  { name: "orderedList", title: "编号列表", icon: ListOrdered, run: (editor) => editor.chain().focus().toggleOrderedList().run() },
];

function active(editor, name) {
  if (name === "heading") return editor?.isActive("heading", { level: 2 });
  return editor?.isActive(name);
}

function hasSelection(editor) {
  return Boolean(editor && editor.state.selection.from < editor.state.selection.to);
}

function applyCitation(event) {
  const value = event.target.value;
  if (!hasSelection(props.editor)) return;
  if (value === "remove") return props.editor.chain().unsetMark("citation").run();
  const source = props.sources.find((row) => sourceKey(row) === value);
  if (source) props.editor.chain().setMark("citation", {
    sourceType: source.sourceType, sourceId: source.id,
  }).run();
  event.target.value = "";
}
</script>

<template>
  <div v-if="editor" class="editor-toolbar" role="toolbar" aria-label="正文格式">
    <button
      v-for="tool in tools"
      :key="tool.name"
      type="button"
      :class="{ active: active(editor, tool.name) }"
      :title="tool.title"
      :aria-label="tool.title"
      @mousedown.prevent="tool.run(editor)"
    >
      <component :is="tool.icon" :size="15" aria-hidden="true" />
    </button>
    <span class="toolbar-divider" aria-hidden="true" />
    <select
      class="citation-picker"
      aria-label="正文引用资料"
      @change="applyCitation"
    >
      <option value="">引用资料</option>
      <option value="remove">取消当前引用</option>
      <option v-for="source in sources" :key="sourceKey(source)" :value="sourceKey(source)">
        〔{{ source.number }}〕{{ source.title }}
      </option>
    </select>
    <button type="button" title="撤销" aria-label="撤销" :disabled="!editor.can().undo()" @click="editor.chain().focus().undo().run()">
      <Undo2 :size="15" aria-hidden="true" />
    </button>
    <button type="button" title="重做" aria-label="重做" :disabled="!editor.can().redo()" @click="editor.chain().focus().redo().run()">
      <Redo2 :size="15" aria-hidden="true" />
    </button>
  </div>
</template>
