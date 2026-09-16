<script setup>
import { computed, ref, watch } from "vue";
import { Search, Sparkles, ChevronRight } from "@lucide/vue";
import { flattenCommands } from "../commands.js";

// AI 命令菜单：搜索 + 分组 + 子菜单。三种行为：
// prefill（带入选区不发送）/ chat（立即发起请求）/ revise（生成修订预览）。
const props = defineProps({
  command: { type: Object, default: null }, // { selection } 或 null
});
const emit = defineEmits(["close", "run"]);
const query = ref("");
const openGroup = ref("");

const flat = computed(() => flattenCommands(query.value));
const groups = computed(() => {
  const seen = new Map();
  for (const item of flat.value) {
    const key = item.group || "";
    if (!seen.has(key)) seen.set(key, []);
    seen.get(key).push(item);
  }
  return [...seen.entries()].map(([label, items]) => ({ label, items }));
});
const childrenOf = (id) => {
  const group = flattenCommands("").find((c) => c.id === id);
  return group?.children || [];
};

function run(item) {
  emit("run", { item, selection: props.command?.selection || null });
  emit("close");
}
</script>

<template>
  <div class="ai-menu" @mousedown.prevent @keydown.esc="emit('close')">
    <header class="ai-menu-search">
      <Search :size="13" />
      <input ref="first" v-model="query" type="text" placeholder="搜索 AI 命令" />
    </header>
    <div class="ai-menu-body">
      <template v-for="group in groups" :key="group.label">
        <div v-if="group.label" class="ai-menu-group-label">{{ group.label }}</div>
        <template v-for="item in group.items" :key="item.id">
          <div v-if="item.children" class="ai-menu-item has-children" @click="openGroup = openGroup === item.id ? '' : item.id">
            <Sparkles :size="14" class="ic" />
            <span>{{ item.label }}</span>
            <ChevronRight :size="13" class="chev" :class="{ open: openGroup === item.id }" />
          </div>
          <div v-else class="ai-menu-item" :class="`mode-${item.mode}`" @click="run(item)">
            <Sparkles :size="14" class="ic" />
            <span>{{ item.label }}</span>
            <small class="mode-tag">{{ item.mode === "prefill" ? "带入选区" : item.mode === "chat" ? "立即提问" : "生成修订" }}</small>
          </div>
          <div v-if="item.children && openGroup === item.id" class="ai-menu-submenu">
            <div v-for="child in item.children" :key="child.id" class="ai-menu-item" @click="run(child)">
              <span class="sub-dot" />{{ child.label }}
            </div>
          </div>
        </template>
      </template>
      <div v-if="!flat.length" class="ai-menu-empty">没有匹配的命令</div>
    </div>
    <footer class="ai-menu-foot">AI 使用真实模型 · 原型内为演示数据环境</footer>
  </div>
</template>
