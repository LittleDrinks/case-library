<script setup>
import { ref } from "vue";
import AnnotationInput from "./AnnotationInput.vue";
import { Check, ChevronDown, MessageSquare, Pencil, Reply, X } from "@lucide/vue";

// 段旁批注卡：默认折叠为紧凑摘要行，点头展开正文并定位原文；同一时刻最多展开一条。
// expandedId（展开态）与 activeId（定位高亮态）分离：定位不强制展开。
const props = defineProps({
  variant: { type: String, default: "A" },
  draft: { type: Object, default: null },
  previewId: { type: String, default: "" },
  items: { type: Array, required: true }, // 注视 lane 排序后的卡片
  activeId: { type: String, default: "" },
  expandedId: { type: String, default: "" },
  placeholderHeight: { type: Number, default: 0 }, // lane 占位高度：保证 paper-scroll 能滚到最后一张卡
});
const emit = defineEmits(["toggle", "resolve", "reply", "accept", "reject", "save", "cancel", "preview"]);

const replying = ref("");
const onlyOpen = ref(false);
function saveReply(item, text) {
  emit("reply", { item, text });
  replying.value = "";
}
function summary(item) {
  const body = item.kind === "revision" ? `${item.original} → ${item.replacement}` : item.text;
  return body.length > 44 ? `${body.slice(0, 44)}…` : body;
}
function kindLabel(item) {
  return item.kind === "revision" ? "修改建议" : "评论";
}
function statusLabel(item) {
  if (item.kind === "revision") return { accepted: "已采用", rejected: "已拒绝", stale: "原文已变化" }[item.status] || "待处理";
  return item.resolved ? "已处理" : "";
}
// 折叠/展开只由头部按钮切换；正文点击不收起（按钮自带 .stop，文字选取不受影响）。
function onHeadClick(item) {
  emit("toggle", item);
}
</script>
<template>
  <div class="ann-lane">
    <header v-if="variant === 'C'" class="ann-inbox-head"><div><b>批注</b><span>{{ items.filter(i => !i.resolved).length }} 条待处理</span></div><button type="button" :aria-pressed="onlyOpen" @click="onlyOpen = !onlyOpen">{{ onlyOpen ? '显示全部' : '仅待处理' }}</button></header>
    <div v-if="draft" class="annotation-draft"><b>新批注</b><AnnotationInput @save="(text) => emit('save', text)" @cancel="emit('cancel')" /></div>
    <div
      v-for="(item, index) in items"
      v-show="variant !== 'C' || !onlyOpen || !item.resolved"

      :key="item.id"
      :data-ann="item.id"
      :class="['ann-card', `kind-${item.kind}`, { active: item.id === activeId, resolved: item.resolved, expanded: item.id === expandedId }]"
      :style="{ top: `${item.top}px` }"
    >
      <button
        type="button"
        class="ann-head"
        :aria-expanded="item.id === expandedId"
        :title="item.id === expandedId ? '收起' : '展开并定位原文'"
        @click.stop="onHeadClick(item)"
      >
        <span v-if="variant === 'B'" class="ann-marker-number">{{ index + 1 }}</span>
        <span class="ann-head-kind" :title="kindLabel(item)" :aria-label="kindLabel(item)"><MessageSquare v-if="item.kind === 'comment'" :size="13" /><Pencil v-else :size="13" /></span>
        <span class="author">{{ item.author }}</span>
        <span v-if="statusLabel(item)" class="ann-head-status">{{ statusLabel(item) }}</span>
        <time v-if="item.id === expandedId" class="ann-time">{{ item.time }}</time>
        <span v-else class="ann-head-sum">{{ summary(item) }}</span>
        <span v-if="item.replies?.length && item.id !== expandedId" class="ann-head-replies"><MessageSquare :size="10" /> {{ item.replies.length }}</span>
        <ChevronDown :size="13" class="ann-head-chev" :class="{ open: item.id === expandedId }" />
      </button>
      <button v-if="item.id === expandedId && item.kind === 'comment'" class="ann-resolve-top" type="button" :aria-label="item.resolved ? '重新打开批注' : '解决批注'" :title="item.resolved ? '重新打开' : '解决批注'" @click.stop="emit('resolve', item)"><Check :size="15" /></button>
      <div class="ann-expansion" :inert="item.id !== expandedId" :aria-hidden="item.id !== expandedId">
        <div class="ann-body">
          <div v-if="item.anchorMissing" class="ann-meta">原文已变化</div>
          <p v-if="item.kind === 'comment'" class="ann-text">{{ item.text }}</p>
          <template v-else>
            <p class="rev-original"><s>{{ item.original }}</s></p>
            <p class="rev-replacement">{{ item.replacement }}</p>
            <small v-if="item.reason" class="rev-reason">{{ item.reason }}</small>
            <div v-if="item.status === 'pending'" class="rev-actions">
              <button type="button" @click.stop="emit('preview', item)">{{ previewId === item.id ? "关闭预览" : "预览修改" }}</button>
              <button type="button" @click.stop="emit('accept', item)"><Check :size="12" /> 采用</button>
              <button type="button" @click.stop="emit('reject', item)"><X :size="12" /> 拒绝</button>
            </div>
            <div v-else class="rev-status"><Check v-if="item.status === 'accepted'" :size="11" /><X v-else :size="11" /> {{ item.status === "accepted" ? "已采用（可撤销）" : item.status === "stale" ? "原文已变化，请重新生成" : "已拒绝" }}</div>
          </template>
          <ul v-if="item.replies?.length" class="ann-replies">
            <li v-for="r in item.replies" :key="r.id">
              <div class="ann-reply-head"><b>{{ r.author }}</b><time>{{ r.time }}</time></div>
              <p>{{ r.text }}</p>
            </li>
          </ul>
          <footer v-if="item.kind === 'comment'" class="ann-card-foot">
            <button v-if="!item.resolved" type="button" @click.stop="replying = item.id"><Reply :size="13" /> 回复这条批注…</button>

          </footer>
          <AnnotationInput v-if="replying === item.id" label="回复批注" @save="(text) => saveReply(item, text)" @cancel="replying = ''" />
        </div>
      </div>
    </div>
    <div class="ann-lane-spacer" :style="{ height: `${placeholderHeight}px` }" aria-hidden="true" />
  </div>
</template>
