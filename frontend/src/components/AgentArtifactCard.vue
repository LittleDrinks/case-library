<script setup>
import { computed } from "vue";
import { artifactStatus, sourceHref, sourceRefId, sourceStatusLabel } from "../lib/agentTimeline.js";

const props = defineProps({
  artifact: { type: Object, required: true },
  sending: { type: Boolean, default: false },
  decideError: { type: String, default: "" },
  sourceState: { type: Function, default: () => ({ state: "checking" }) },
  readOnly: { type: Boolean, default: false },
});
const emit = defineEmits(["accept", "reject"]);

const isDocument = computed(() => props.artifact.kind === "document");
const draftPreview = computed(() =>
  (props.artifact.blocks || []).map(blockText).filter(Boolean).join("\n"));

function blockText(block) {
  if (!block) return "";
  if (block.type === "bullet_list") {
    return listText(block, "·");
  }
  if (block.type === "ordered_list") {
    return listText(block, "");
  }
  if (block.type === "blockquote") {
    return block.paragraphs.map((text) => `「${text}」`).join("\n");
  }
  return block.type === "heading" ? `【${block.text}】` : block.text || "";
}

function listText(block, marker) {
  return block.items.map((item, index) => `${marker || index + 1 + "."} ${item}`).join("\n");
}
</script>

<template>
  <div
    class="agent-artifact"
    :data-artifact-id="artifact.id"
    :data-artifact-status="artifact.status"
    :data-artifact-kind="artifact.kind || 'range'"
    data-testid="agent-artifact"
  >
    <b>{{ isDocument ? "全文初稿候选" : "修订候选" }}</b>
    <template v-if="isDocument">
      <pre class="agent-artifact-replacement agent-artifact-draft">{{ draftPreview }}</pre>
    </template>
    <template v-else>
      <p class="agent-artifact-quote">原文：{{ artifact.target.quote }}</p>
      <p class="agent-artifact-replacement">替换为：{{ artifact.replacement }}</p>
    </template>
    <p v-if="artifact.reason" class="agent-artifact-reason">理由：{{ artifact.reason }}</p>
    <p v-if="artifact.annotationId" class="agent-artifact-annotation">
      已关联批注，请在批注面板中合并或关闭
    </p>
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
    <div v-if="artifact.status === 'pending' && !readOnly && !artifact.annotationId" class="agent-artifact-actions">
      <button type="button" data-testid="agent-accept" :disabled="sending" @click="emit('accept', artifact.id)">接受</button>
      <button type="button" data-testid="agent-reject" :disabled="sending" @click="emit('reject', artifact.id)">拒绝</button>
    </div>
  </div>
</template>
