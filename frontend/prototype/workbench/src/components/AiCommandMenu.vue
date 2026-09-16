<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from "vue";
import { Search, Sparkles, ChevronRight } from "@lucide/vue";
import { aiCommands, flattenCommands } from "../commands.js";

const props = defineProps({ command: { type: Object, default: null } });
const emit = defineEmits(["close", "run"]);
const menuEl = ref(null);
const searchEl = ref(null);
const query = ref("");
const openGroup = ref("");
const submenuLeft = ref(false);
const items = computed(() => query.value.trim() ? flattenCommands(query.value) : aiCommands);
const modeLabel = (item) => ({ prefill: "带入选区", chat: "立即提问", revise: "预览修订" }[item.mode]);

function close() {
  if (openGroup.value) {
    menuEl.value.querySelector(`[data-command="${openGroup.value}"]`)?.focus();
    openGroup.value = "";
    return;
  }
  emit("close");
}
function run(item) {
  emit("run", { item, selection: props.command?.selection || null });
  emit("close");
}
async function open(item, focus = false) {
  if (!item.children) { openGroup.value = ""; return; }
  openGroup.value = item.id;
  submenuLeft.value = menuEl.value.getBoundingClientRect().right + 225 > window.innerWidth;
  if (focus) { await nextTick(); menuEl.value.querySelector(".ai-menu-submenu button")?.focus(); }
}
function activate(item) {
  if (item.children) open(item, true);
  else run(item);
}
function moveFocus(event, direction) {
  const scope = event.target.closest("[role=menu]") || menuEl.value;
  const buttons = [...scope.querySelectorAll(":scope > .ai-menu-option > button, :scope > button")];
  if (!buttons.length) return;
  const index = buttons.indexOf(document.activeElement);
  buttons[(index + direction + buttons.length) % buttons.length].focus();
}
function keydown(event) {
  if (event.isComposing) return;
  if (event.key === "Escape") { event.preventDefault(); event.stopPropagation(); close(); }
  if (["ArrowDown", "ArrowUp"].includes(event.key)) {
    event.preventDefault(); moveFocus(event, event.key === "ArrowDown" ? 1 : -1);
  }
  if (event.key === "ArrowLeft" && openGroup.value) {
    event.preventDefault(); menuEl.value.querySelector(`[data-command="${openGroup.value}"]`)?.focus(); openGroup.value = "";
  }
}
function searchKey(event) {
  if (event.isComposing || event.key !== "ArrowDown") return;
  event.preventDefault(); event.stopPropagation();
  menuEl.value.querySelector(".ai-menu-body button")?.focus();
}
function outside(event) {
  if (menuEl.value?.contains(event.target)) return;
  if (event.target.closest(".ai-cmd-btn, .ai-menu-trigger, .balloon-menu-trigger")) return;
  emit("close");
}
onMounted(async () => { document.addEventListener("pointerdown", outside); await nextTick(); searchEl.value?.focus(); });
onBeforeUnmount(() => document.removeEventListener("pointerdown", outside));
</script>

<template>
  <div ref="menuEl" class="ai-menu" aria-label="AI 命令" @keydown="keydown">
    <header class="ai-menu-search">
      <Search :size="13" />
      <input ref="searchEl" v-model="query" type="search" placeholder="搜索 AI 命令" aria-label="搜索 AI 命令" @input="openGroup = ''" @keydown="searchKey" />
    </header>
    <div class="ai-menu-body" role="menu" aria-label="AI 命令">
      <div v-for="item in items" :key="item.id" class="ai-menu-option" @mouseenter="open(item)">
        <button type="button" role="menuitem" class="ai-menu-item" :data-command="item.id"
          :aria-haspopup="item.children ? 'menu' : undefined" :aria-expanded="item.children ? openGroup === item.id : undefined"
          @click="activate(item)" @keydown.right.prevent="item.children && open(item, true)">
          <Sparkles :size="14" class="ic" /><span>{{ item.label }}</span>
          <ChevronRight v-if="item.children" :size="13" class="chev" />
          <small v-else class="mode-tag">{{ modeLabel(item) }}</small>
        </button>
        <Transition name="command-submenu">
          <div v-if="item.children && openGroup === item.id" class="ai-menu-submenu" :class="{ 'opens-left': submenuLeft }" role="menu" :aria-label="item.label">
            <button v-for="child in item.children" :key="child.id" type="button" role="menuitem" class="ai-menu-item" @click="run(child)">
              <span>{{ child.label }}</span><small class="mode-tag">{{ modeLabel(child) }}</small>
            </button>
          </div>
        </Transition>
      </div>
      <div v-if="!items.length" class="ai-menu-empty" role="status">没有匹配的命令</div>
    </div>
    <footer class="ai-menu-foot">修改先预览，由你决定是否采用</footer>
  </div>
</template>

<style scoped>
.ai-menu { overflow: visible; }
.ai-menu-body { max-height: none; overflow: visible; }
.ai-menu-option { position: relative; }
.ai-menu-item { width: 100%; border: 0; background: transparent; text-align: left; font: inherit; font-size: 12px; }
.ai-menu-item:focus-visible { outline: 2px solid var(--brand); outline-offset: -2px; background: var(--brand-soft); }
.ai-menu-item[aria-expanded="true"] { background: var(--brand-soft); }
.ai-menu-submenu { position: absolute; z-index: 2; top: -5px; left: calc(100% + 2px); width: 218px; margin: 0; padding: 5px; border: 1px solid var(--line); border-radius: 8px; background: white; box-shadow: var(--shadow-pop); }
.ai-menu-submenu::before { content: ""; position: absolute; inset: 0 auto 0 -8px; width: 8px; }
.ai-menu-submenu.opens-left { left: auto; right: calc(100% + 2px); }
.ai-menu-submenu.opens-left::before { left: auto; right: -8px; }
.command-submenu-enter-active, .command-submenu-leave-active { transition: opacity 150ms ease, transform 150ms ease; }
.command-submenu-enter-from, .command-submenu-leave-to { opacity: 0; transform: translateX(-4px); }
@media (max-width: 580px) { .ai-menu-submenu, .ai-menu-submenu.opens-left { position: static; width: auto; margin: 2px 4px 5px 16px; box-shadow: none; } }
@media (prefers-reduced-motion: reduce) { .command-submenu-enter-active, .command-submenu-leave-active { transition: none; } }
</style>
