<script setup>
import { Bold, Heading2, List, ListOrdered, Pilcrow, Redo2, Undo2 } from "@lucide/vue";

defineProps({ editor: { type: Object, default: null } });

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
    <button type="button" title="撤销" aria-label="撤销" :disabled="!editor.can().undo()" @click="editor.chain().focus().undo().run()">
      <Undo2 :size="15" aria-hidden="true" />
    </button>
    <button type="button" title="重做" aria-label="重做" :disabled="!editor.can().redo()" @click="editor.chain().focus().redo().run()">
      <Redo2 :size="15" aria-hidden="true" />
    </button>
  </div>
</template>
