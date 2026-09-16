<script setup>
import { computed } from "vue";
import { Check, MessageSquare, Pencil, Reply, X } from "@lucide/vue";

// 段旁批注卡：评论与修订卡同列，点击定位原文，可回复/标记处理。
const props = defineProps({
  items: { type: Array, required: true }, // 注视 lane 排序后的卡片
  activeId: { type: String, default: "" },
});
const emit = defineEmits(["locate", "resolve", "reply", "accept", "reject"]);

function kindLabel(item) {
  return item.kind === "revision" ? "修改建议" : "评论";
}
</script>
<template>
  <div class="ann-lane">
    <div
      v-for="item in items"
      :key="item.id"
      :data-ann="item.id"
      :class="['ann-card', `kind-${item.kind}`, { active: item.id === activeId, resolved: item.resolved }]"
      :style="{ top: `${item.top}px` }"
    >
      <header>
        <span class="author">{{ item.author }}</span>
        <span class="time">{{ item.time }}</span>
        <span class="kind-chip">{{ kindLabel(item) }}</span>
      </header>
      <p v-if="item.kind === 'comment'" class="ann-text">{{ item.text }}</p>
      <template v-else>
        <p class="rev-original"><s>{{ item.original }}</s></p>
        <p class="rev-replacement">{{ item.replacement }}</p>
        <small v-if="item.reason" class="rev-reason">{{ item.reason }}</small>
        <div v-if="item.status === 'pending'" class="rev-actions">
          <button type="button" @click.stop="emit('accept', item)"><Check :size="12" /> 采用</button>
          <button type="button" @click.stop="emit('reject', item)"><X :size="12" /> 拒绝</button>
        </div>
        <div v-else class="rev-status">{{ item.status === "accepted" ? "已采用（可撤销）" : "已拒绝" }}</div>
      </template>
      <blockquote v-if="item.kind === 'comment' && !item.resolved" class="ann-quote">“{{ item.anchorQuote }}”</blockquote>
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
  </div>
</template>
