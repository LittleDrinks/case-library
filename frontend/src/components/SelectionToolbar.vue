<script setup>
import { ref } from "vue";
import { BubbleMenu } from "@tiptap/vue-3";
import { Bold, Italic, Link, Sparkles, Check, X } from "@lucide/vue";
const props = defineProps({ editor: { type: Object, required: true } });
const emit = defineEmits(["ask-ai"]);
const editingLink = ref(false);
const href = ref("");
const error = ref("");
function openLink() {
  href.value = props.editor.getAttributes("link").href || "";
  error.value = "";
  editingLink.value = true;
}
function saveLink() {
  const url = href.value.trim();
  if (url && !/^https?:\/\//i.test(url)) {
    error.value = "请输入 http:// 或 https:// 开头的链接";
    return;
  }
  const chain = props.editor.chain().focus().extendMarkRange("link");
  if (url) chain.setLink({ href: url }).run();
  else chain.unsetLink().run();
  editingLink.value = false;
}
</script>
<template>
  <div class="selection-menu-host">
    <BubbleMenu :editor="editor" :tippy-options="{ duration: 120, maxWidth: 340 }">
      <div class="selection-toolbar" @mousedown.prevent>
        <template v-if="!editingLink">
          <button type="button" title="加粗" aria-label="选区加粗" :aria-pressed="editor.isActive('bold')" @click="editor.chain().focus().toggleBold().run()"><Bold :size="16" /></button>
          <button type="button" title="斜体" aria-label="选区斜体" :aria-pressed="editor.isActive('italic')" @click="editor.chain().focus().toggleItalic().run()"><Italic :size="16" /></button>
          <button type="button" title="链接" aria-label="编辑选区链接" :aria-pressed="editor.isActive('link')" @click="openLink"><Link :size="16" /></button>
          <span class="toolbar-divider" />
          <button type="button" class="selection-ask-ai" title="带选区问 AI" aria-label="带选区问 AI" @click="emit('ask-ai')"><Sparkles :size="17" /></button>
        </template>
        <form v-else class="selection-link-form" @submit.prevent="saveLink" @mousedown.stop>
          <input v-model="href" aria-label="链接地址" placeholder="https://" @keydown.esc="editingLink = false" />
          <button type="submit" aria-label="保存链接"><Check :size="16" /></button>
          <button type="button" aria-label="取消链接编辑" @click="editingLink = false"><X :size="16" /></button>
          <small v-if="error" role="alert">{{ error }}</small>
        </form>
      </div>
    </BubbleMenu>
  </div>
</template>
