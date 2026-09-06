<script setup>
import { computed, onBeforeUnmount, ref, shallowRef, watch } from "vue";
import { createForceLayout } from "../lib/forceGraph.js";
import { buildSearchGraph } from "../lib/searchGraph.js";

const props = defineProps({ query: String, items: { type: Array, required: true } });
const graph = computed(() => buildSearchGraph(props.query, props.items));
const selectedId = ref("");
const stage = ref(null);
const bounds = ref({ width: 1000, height: 520 });
const layout = shallowRef(null);
const layoutNodes = shallowRef([]);
const layoutLinks = shallowRef([]);
const dragState = ref(null);
const suppressedClick = ref("");
let resizeObserver;
const byId = computed(() => new Map(layoutNodes.value.map((node) => [node.id, node])));
const selected = computed(() => byId.value.get(selectedId.value));
const resourceNodes = computed(() => layoutNodes.value.filter((node) => node.item));

function updateFrame(nodes, links, size) {
  layoutNodes.value = [...nodes];
  layoutLinks.value = [...links];
  bounds.value = { ...size };
}

function resetLayout() {
  layout.value?.stop();
  layout.value = createForceLayout(graph.value, bounds.value, updateFrame);
  selectedId.value = "";
}

function select(node) {
  if (suppressedClick.value === node.id) {
    suppressedClick.value = "";
    return;
  }
  selectedId.value = selectedId.value === node.id ? "" : node.id;
}

function nodeLabel(node) {
  const type = { case: "案例", knowledge: "知识", material: "素材", topic: "主题", query: "检索" }[node.type];
  return `${type}：${node.label}`;
}

function line(link) {
  const source = typeof link.source === "object" ? link.source : byId.value.get(link.source);
  const target = typeof link.target === "object" ? link.target : byId.value.get(link.target);
  return { x1: source.x, y1: source.y, x2: target.x, y2: target.y };
}

function relationLabel(link) {
  return `${byId.value.get(link.source).label} ${link.label} ${byId.value.get(link.target).label}`;
}

function eventPoint(event) {
  const rect = stage.value.getBoundingClientRect();
  return { x: event.clientX - rect.left, y: event.clientY - rect.top };
}

function startDrag(node, event) {
  if (event.button !== 0) return;
  dragState.value = { id: node.id, pointerId: event.pointerId, moved: false };
  event.currentTarget.setPointerCapture?.(event.pointerId);
  const point = eventPoint(event);
  layout.value.pin(node.id, point.x, point.y);
}

function moveDrag(node, event) {
  if (dragState.value?.id !== node.id) return;
  dragState.value.moved = true;
  const point = eventPoint(event);
  layout.value.pin(node.id, point.x, point.y);
}

function endDrag(node, event) {
  if (dragState.value?.id !== node.id) return;
  if (dragState.value.moved) suppressedClick.value = node.id;
  event.currentTarget.releasePointerCapture?.(dragState.value.pointerId);
  layout.value.release(node.id);
  dragState.value = null;
}

function resizeLayout(rect) {
  if (rect.width > 0 && rect.height > 0) layout.value?.resize(rect.width, rect.height);
}

function observeStage(element) {
  resizeObserver?.disconnect();
  if (!element) return;
  resizeObserver = new ResizeObserver(([entry]) => resizeLayout(entry.contentRect));
  resizeObserver.observe(element);
}

watch(graph, resetLayout, { immediate: true });
watch(stage, observeStage);
onBeforeUnmount(() => {
  resizeObserver?.disconnect();
  layout.value?.stop();
});

defineExpose({ graph });
</script>

<template>
  <section class="search-graph" role="region" aria-label="当前检索结果图谱">
    <header class="graph-heading">
      <div><b>结果关系图</b><small>实体与关系均来自当前可见结果</small></div>
      <p><span><i class="legend-dot case-dot" />案例</span><span><i class="legend-dot knowledge-dot" />知识</span><span><i class="legend-dot material-dot" />素材</span><span><i class="legend-dot topic-dot" />主题</span><span><i class="legend-line" />共同主题</span></p>
    </header>
    <div v-if="graph.total" ref="stage" class="graph-stage">
      <svg :viewBox="`0 0 ${bounds.width} ${bounds.height}`" preserveAspectRatio="none" aria-hidden="true">
        <line v-for="(link, index) in layoutLinks" :key="index" v-bind="line(link)" :class="`graph-link ${link.label === '共同主题' ? 'topic-link' : ''}`" />
      </svg>
      <button v-for="node in layoutNodes" :key="node.id" type="button" :class="`graph-node ${node.type}-node`" :style="{ left: `${node.x}px`, top: `${node.y}px` }" :aria-label="nodeLabel(node)" :aria-pressed="selectedId === node.id" @click="select(node)" @pointerdown="startDrag(node, $event)" @pointermove="moveDrag(node, $event)" @pointerup="endDrag(node, $event)" @pointercancel="endDrag(node, $event)">
        <span>{{ node.label }}</span>
      </button>
    </div>
    <p v-else class="search-empty">当前筛选没有可展示的关系</p>
    <footer v-if="graph.total" class="graph-summary">
      <span>显示 {{ graph.shown }} / {{ graph.total }} 条结果</span>
      <span>{{ graph.links.length }} 条关系</span>
    </footer>
    <aside v-if="selected?.item" class="graph-selection" aria-live="polite">
      <div><span>{{ { case: '案例', knowledge: '知识', material: '素材' }[selected.type] }}</span><b>{{ selected.label }}</b><p>{{ selected.item.summary || "暂无摘要" }}</p></div>
      <RouterLink v-if="selected.type === 'case'" :to="{ name: 'case-public', params: { id: selected.item.id } }">查看案例</RouterLink>
      <RouterLink v-else-if="selected.type === 'material'" :to="{ name: 'material-detail', params: { id: selected.item.id }, query: { from: 'search' } }">查看素材</RouterLink>
    </aside>
    <ul class="visually-hidden" aria-label="图谱资源清单"><li v-for="node in resourceNodes" :key="node.id">{{ nodeLabel(node) }}</li></ul>
    <ul class="visually-hidden" aria-label="图谱关系列表"><li v-for="(link, index) in graph.links" :key="index">{{ relationLabel(link) }}</li></ul>
  </section>
</template>
