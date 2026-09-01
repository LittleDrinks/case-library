<script setup>
import { computed } from "vue";
import { Check, RotateCcw, X } from "@lucide/vue";
import { candidateDiff, candidateSource } from "../lib/writingCandidate.js";

const props = defineProps({
  candidate: { type: Object, required: true },
  busy: { type: Boolean, default: false },
});
const emit = defineEmits(["mode", "accept", "reject", "rollback"]);
const modes = computed(() => [
  ...(props.candidate.context.quote
    ? [{ id: "replace-selection", label: "替换选区" }] : []),
  { id: "replace-section", label: "替换本节" },
  { id: "append-section", label: "追加到本节" },
  { id: "new-section", label: "新建小节" },
]);
const changes = computed(() => candidateDiff(
  candidateSource(props.candidate, props.candidate.mode), props.candidate.text,
));
const pending = computed(() => props.candidate.status === "pending");

function statusLabel() {
  if (props.candidate.status === "expired") return "正文已变化，请重新生成";
  if (props.candidate.status === "accepted" && props.candidate.rollbackExpired) {
    return "已接受，回滚已过期";
  }
  return ({ accepted: "已接受", rejected: "已拒绝", rolledback: "已回滚" })[
    props.candidate.status
  ];
}
</script>

<template>
  <section class="writing-candidate" role="region" aria-label="待确认修订">
    <header><b>待确认修订</b><span>{{ candidate.context.section }}</span></header>
    <div class="candidate-modes" aria-label="修订落点">
      <button
        v-for="mode in modes"
        :key="mode.id"
        type="button"
        :class="{ active: candidate.mode === mode.id }"
        :aria-label="mode.label"
        :disabled="!pending || busy"
        @click="emit('mode', mode.id)"
      >{{ mode.label }}</button>
    </div>
    <p class="candidate-diff" aria-label="文本差异">
      <template v-for="(change, index) in changes" :key="index">
        <del v-if="change.kind === 'removed'">{{ change.value }}</del>
        <ins v-else-if="change.kind === 'added'">{{ change.value }}</ins>
        <span v-else>{{ change.value }}</span>
      </template>
    </p>
    <p class="candidate-reason"><b>修改理由</b>{{ candidate.reason }}</p>
    <div v-if="pending" class="candidate-actions">
      <button type="button" aria-label="拒绝修订" :disabled="busy" @click="emit('reject')"><X :size="14" />拒绝</button>
      <button class="primary" type="button" aria-label="接受修订" :disabled="busy" @click="emit('accept')"><Check :size="14" />{{ busy ? "处理中" : "接受" }}</button>
    </div>
    <div v-else class="candidate-resolution">
      <span>{{ statusLabel() }}</span>
      <button
        v-if="candidate.status === 'accepted' && !candidate.rollbackExpired"
        type="button"
        aria-label="回滚本批"
        :disabled="busy"
        @click="emit('rollback')"
      ><RotateCcw :size="14" />回滚本批</button>
    </div>
  </section>
</template>
