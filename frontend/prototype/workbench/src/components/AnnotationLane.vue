<script setup>
import { Check, ChevronDown, MessageSquare, Pencil, Quote as QuoteIcon, Reply, X } from "@lucide/vue";

// 段旁批注卡：默认折叠为紧凑摘要行，点头展开正文并定位原文；同一时刻最多展开一条。
// expandedId（展开态）与 activeId（定位高亮态）分离：定位不强制展开。
const props = defineProps({
  items: { type: Array, required: true }, // 注视 lane 排序后的卡片
  activeId: { type: String, default: "" },
  expandedId: { type: String, default: "" },
  placeholderHeight: { type: Number, default: 0 }, // lane 占位高度：保证 paper-scroll 能滚到最后一张卡
});
const emit = defineEmits(["toggle", "resolve", "reply", "accept", "reject"]);

function summary(item) {
  const body = item.kind === "revision" ? `${item.original} → ${item.replacement}` : item.text;
  return body.length > 44 ? `${body.slice(0, 44)}…` : body;
}
function kindLabel(item) {
  return item.kind === "revision" ? "修改建议" : "评论";
}
function statusLabel(item) {
  if (item.kind === "revision") return item.status === "accepted" ? "已采用" : item.status === "rejected" ? "已拒绝" : "待处理";
  return item.resolved ? "已处理" : "";
}
// 折叠/展开只由头部按钮切换；正文点击不收起（按钮自带 .stop，文字选取不受影响）。
function onHeadClick(item) {
  emit("toggle", item);
}
</script>
<template>
  <div class="ann-lane">
    <div
      v-for="item in items"

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
        <span class="ann-head-kind"><MessageSquare v-if="item.kind === 'comment'" :size="12" /><Pencil v-else :size="12" /> {{ kindLabel(item) }}</span>
        <span class="author">{{ item.author }}</span>
        <span v-if="statusLabel(item)" class="ann-head-status">{{ statusLabel(item) }}</span>
        <span class="ann-head-sum">{{ summary(item) }}</span>
        <span v-if="item.replies?.length" class="ann-head-replies"><MessageSquare :size="10" /> {{ item.replies.length }}</span>
        <ChevronDown :size="13" class="ann-head-chev" :class="{ open: item.id === expandedId }" />
      </button>
      <template v-if="item.id === expandedId">
        <div class="ann-body">
          <p v-if="item.kind === 'comment'" class="ann-text">{{ item.text }}</p>
          <template v-else>
            <p class="rev-original"><s>{{ item.original }}</s></p>
            <p class="rev-replacement">{{ item.replacement }}</p>
            <small v-if="item.reason" class="rev-reason">{{ item.reason }}</small>
            <div v-if="item.status === 'pending'" class="rev-actions">
              <button type="button" @click.stop="emit('accept', item)"><Check :size="12" /> 采用</button>
              <button type="button" @click.stop="emit('reject', item)"><X :size="12" /> 拒绝</button>
            </div>
            <div v-else class="rev-status"><Check v-if="item.status === 'accepted'" :size="11" /><X v-else :size="11" /> {{ item.status === "accepted" ? "已采用（可撤销）" : "已拒绝" }}</div>
          </template>
          <blockquote v-if="item.kind === 'comment' && !item.resolved" class="ann-quote"><QuoteIcon :size="11" class="ann-quote-ic" /><span>“{{ item.anchorQuote }}”</span></blockquote>
          <ul v-if="item.replies?.length" class="ann-replies">
            <li v-for="r in item.replies" :key="r.id">
              <b>{{ r.author }}</b> · {{ r.time }}<br />{{ r.text }}
            </li>
          </ul>
          <footer v-if="item.kind === 'comment'" class="ann-card-foot">
            <button v-if="!item.resolved" type="button" @click.stop="emit('reply', item)"><Reply :size="12" /> 回复</button>
            <button type="button" @click.stop="emit('resolve', item)">
              <Check :size="12" /> {{ item.resolved ? "重新打开" : "标记处理" }}
            </button>
          </footer>
        </div>
      </template>
    </div>
    <div class="ann-lane-spacer" :style="{ height: `${placeholderHeight}px` }" aria-hidden="true" />
  </div>
</template>
