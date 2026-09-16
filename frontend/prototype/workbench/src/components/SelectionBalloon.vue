<script setup>
import { nextTick, onBeforeUnmount, onMounted, ref } from "vue";
import { BubbleMenu } from "@tiptap/vue-3";
import { Bold, ChevronDown, Italic, Link2, MessageSquarePlus, Sparkles, X } from "@lucide/vue";

const props = defineProps({ editor: { type: Object, required: true } });
const emit = defineEmits(["annotate", "ask-ai", "selection-change", "open-ai-menu"]);
const linking = ref(false);
const linkUrl = ref("");
const toolbarEl = ref(null);
const linkEl = ref(null);
const linkError = ref("");
let savedSelection = null;
let tooltip = null;
const bubbleDuration = matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : 180;
const shouldShow = ({ editor, from, to }) => !editor.view.composing && from !== to && Boolean(editor.state.doc.textBetween(from, to).trim());

function currentSelection() {
  const { from, to } = props.editor.state.selection;
  return { from, to, quote: props.editor.state.doc.textBetween(from, to, " ") };
}
function openMenu(event) {
  emit("open-ai-menu", { ...currentSelection(), rect: event.currentTarget.getBoundingClientRect() });
}
function format(name) {
  props.editor.chain().focus()[name]().run();
}
async function openLink() {
  savedSelection = currentSelection();
  linking.value = true;
  linkError.value = "";
  linkUrl.value = props.editor.getAttributes("link").href || "";
  await nextTick(); linkEl.value?.focus();
}
function closeLink() {
  linking.value = false;
  if (savedSelection) props.editor.chain().setTextSelection(savedSelection).focus().run();
}
function applyLink() {
  const url = linkUrl.value.trim();
  if (url && !/^(https?:\/\/|mailto:|#)/i.test(url)) { linkError.value = "请输入 https://、http:// 或 mailto: 链接"; return; }
  const chain = props.editor.chain().setTextSelection(savedSelection).focus();
  if (url) chain.setLink({ href: url }).run();
  else chain.unsetLink().run();
  linking.value = false;
}
function toolbarKey(event) {
  if (event.key === "Escape") {
    event.preventDefault(); event.stopPropagation();
    if (linking.value) closeLink();
    else { props.editor.commands.focus(); tooltip?.hide(); }
  }
  if (linking.value || !["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
  event.preventDefault();
  const buttons = [...toolbarEl.value.querySelectorAll(":scope > button")];
  const index = buttons.indexOf(document.activeElement);
  const next = event.key === "Home" ? 0 : event.key === "End" ? buttons.length - 1 : (index + (event.key === "ArrowRight" ? 1 : -1) + buttons.length) % buttons.length;
  buttons[next]?.focus();
}
function shortcut(event) {
  if (!event.altKey || event.key !== "F10" || props.editor.state.selection.empty) return;
  if (!props.editor.view.dom.contains(document.activeElement)) return;
  event.preventDefault(); tooltip?.show(); toolbarEl.value?.querySelector("button")?.focus();
}
function outside(event) {
  if (linking.value && !toolbarEl.value?.contains(event.target)) linking.value = false;
}
onMounted(() => { document.addEventListener("keydown", shortcut); document.addEventListener("pointerdown", outside); });
onBeforeUnmount(() => { document.removeEventListener("keydown", shortcut); document.removeEventListener("pointerdown", outside); });
</script>

<template>
  <bubble-menu :editor="editor" :should-show="shouldShow" :update-delay="200"
    :tippy-options="{ duration: bubbleDuration, placement: 'top', offset: [0, 8], maxWidth: 'calc(100vw - 24px)', onCreate: (instance) => tooltip = instance }"
    @update="$emit('selection-change', editor)">
    <div ref="toolbarEl" class="sel-balloon" role="toolbar" aria-label="选区操作" @keydown="toolbarKey">
      <button type="button" title="加粗" aria-label="加粗" :aria-pressed="editor.isActive('bold')" :class="{ active: editor.isActive('bold') }" @mousedown.prevent @click="format('toggleBold')"><Bold :size="15" /></button>
      <button type="button" title="斜体" aria-label="斜体" :aria-pressed="editor.isActive('italic')" :class="{ active: editor.isActive('italic') }" @mousedown.prevent @click="format('toggleItalic')"><Italic :size="15" /></button>
      <button type="button" title="链接" aria-label="链接" :aria-expanded="linking" :class="{ active: editor.isActive('link') }" @mousedown.prevent @click="openLink"><Link2 :size="15" /></button>
      <span class="balloon-divider" />
      <button type="button" title="批注" aria-label="批注" @mousedown.prevent @click="emit('annotate', currentSelection())"><MessageSquarePlus :size="15" /></button>
      <button type="button" title="问 AI" aria-label="问 AI" class="ai" @mousedown.prevent @click="emit('ask-ai', currentSelection())"><Sparkles :size="15" /></button>
      <button type="button" title="AI 命令" aria-label="AI 命令" class="ai balloon-menu-trigger" @mousedown.prevent @click="openMenu"><ChevronDown :size="12" /></button>
      <form v-if="linking" class="balloon-link-form" @submit.prevent="applyLink">
        <input ref="linkEl" v-model="linkUrl" type="text" placeholder="https://…" aria-label="链接地址" />
        <button type="submit">应用</button>
        <button type="button" title="取消" aria-label="取消链接编辑" @click="closeLink"><X :size="12" /></button>
        <small v-if="linkError" role="alert">{{ linkError }}</small>
      </form>
    </div>
  </bubble-menu>
</template>

<style scoped>
.sel-balloon { position: relative; }
.sel-balloon button:focus-visible { outline: 2px solid var(--brand); outline-offset: -2px; }
.balloon-link-form { flex-wrap: wrap; width: min(330px, calc(100vw - 24px)); }
.balloon-link-form input { flex: 1; min-width: 100px; }
.balloon-link-form small { flex-basis: 100%; color: var(--red); font-size: 11px; }
</style>
