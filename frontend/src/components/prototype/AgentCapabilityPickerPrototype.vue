<script setup>
import {
  Check, CornerDownLeft, Database, ListChecks, Search,
  WandSparkles, Wrench, X,
} from "@lucide/vue";
import { ref } from "vue";

const props = defineProps({
  skillIds: { type: Array, required: true },
  toolIds: { type: Array, required: true },
});
const emit = defineEmits(["close", "insert-skill", "toggle-tool"]);
const tab = ref("skills");
const skills = [
  { id: "sizheng-case-generator.v2.1.m1", label: "思政案例生成", version: "v2.1", meta: "单段案例修订", icon: ListChecks },
];
const tools = [
  { id: "search_corpus", label: "检索平台资料", meta: "案例、素材与知识库", access: "自动读取", icon: Search },
  { id: "propose_revision", label: "提议正文修订", meta: "生成待确认的修订，不直接改正文", access: "接受后写入", icon: Database },
];

function selected(id) {
  return props.toolIds.includes(id);
}

function inserted(id) {
  return props.skillIds.includes(id);
}
</script>

<template>
  <section class="capability-picker" role="dialog" aria-label="本轮能力" @keydown.esc="emit('close')">
    <header>
      <span><b>本轮能力</b><small>插入 Skills，控制本轮可用工具</small></span>
      <button type="button" aria-label="关闭" @click="emit('close')"><X :size="15" /></button>
    </header>
    <nav aria-label="能力类型">
      <button type="button" :class="{ active: tab === 'skills' }" @click="tab = 'skills'"><WandSparkles :size="14" />Skills <em>{{ skillIds.length }}</em></button>
      <button type="button" :class="{ active: tab === 'tools' }" @click="tab = 'tools'"><Wrench :size="14" />工具 <em>{{ toolIds.length }}</em></button>
    </nav>
    <div v-if="tab === 'skills'" class="capability-list skill-list">
      <button v-for="item in skills" :key="item.id" type="button" :class="{ selected: inserted(item.id) }" :disabled="inserted(item.id)" @click="emit('insert-skill', item)">
        <span class="capability-icon"><component :is="item.icon" :size="15" /></span>
        <span><b>{{ item.label }}</b><small>{{ item.version }} · {{ item.meta }}</small></span>
        <span class="insert-control"><template v-if="inserted(item.id)"><Check :size="13" />已插入</template><template v-else><CornerDownLeft :size="13" />插入</template></span>
      </button>
    </div>
    <div v-else class="capability-list tool-list">
      <button v-for="item in tools" :key="item.id" type="button" @click="emit('toggle-tool', item.id)">
        <span class="capability-icon"><component :is="item.icon" :size="15" /></span>
        <span><b>{{ item.label }}</b><small>{{ item.meta }}</small></span>
        <span class="tool-control"><em>{{ item.access }}</em><i :class="{ enabled: selected(item.id) }"><span /></i></span>
      </button>
    </div>
  </section>
</template>
