<script setup>
import { artifactStatus, sourceHref, sourceRefId, sourceStatusLabel } from "../lib/agentTimeline.js";

defineProps({
  artifact: { type: Object, required: true },
  sending: { type: Boolean, default: false },
  decideError: { type: String, default: "" },
  sourceState: { type: Function, default: () => ({ state: "checking" }) },
  readOnly: { type: Boolean, default: false },
});
const emit = defineEmits(["accept", "reject"]);
</script>

<template>
  <div
    class="agent-artifact"
    :data-artifact-id="artifact.id"
    :data-artifact-status="artifact.status"
    data-testid="agent-artifact"
  >
    <b>修订候选</b>
    <p class="agent-artifact-quote">原文：{{ artifact.target.quote }}</p>
    <p class="agent-artifact-replacement">替换为：{{ artifact.replacement }}</p>
    <p v-if="artifact.reason" class="agent-artifact-reason">理由：{{ artifact.reason }}</p>
    <p class="agent-artifact-status">状态：{{ artifactStatus(artifact) }}</p>
    <template v-for="source in artifact.sources || []" :key="sourceRefId(source)">
      <a
        v-if="sourceState(source).state === 'available' && (sourceState(source).url || sourceHref(source))"
        class="agent-artifact-source"
        :href="sourceState(source).url || sourceHref(source)"
        target="_blank"
        rel="noopener noreferrer"
        :data-source-ref="sourceRefId(source)"
        :title="`在站内打开：${source.title || source.id}（已按当前权限核验）`"
      >依据：{{ source.title || source.id }} · {{ sourceStatusLabel(sourceState(source)) }}</a>
      <p v-else class="agent-artifact-source" :data-source-ref="sourceRefId(source)">依据：{{ source.title || source.id }} · {{ sourceStatusLabel(sourceState(source)) }}</p>
    </template>
    <p v-if="decideError" class="ai-message-error" role="alert">{{ decideError }}</p>
    <div v-if="artifact.status === 'pending' && !readOnly" class="agent-artifact-actions">
      <button type="button" data-testid="agent-accept" :disabled="sending" @click="emit('accept', artifact.id)">接受</button>
      <button type="button" data-testid="agent-reject" :disabled="sending" @click="emit('reject', artifact.id)">拒绝</button>
    </div>
  </div>
</template>
