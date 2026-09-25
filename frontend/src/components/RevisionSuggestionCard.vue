<script setup>
import { Check, ChevronDown, ChevronRight, RefreshCw, X } from "@lucide/vue";
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { sourceHref, sourceRefId, sourceStatusLabel } from "../lib/agentTimeline.js";

const props = defineProps({
  artifact: { type: Object, required: true },
  expanded: { type: Boolean, default: false },
  sending: { type: Boolean, default: false },
  deciding: { type: Boolean, default: false },
  decideError: { type: String, default: "" },
  sourceState: { type: Function, default: () => ({ state: "checking" }) },
  readOnly: { type: Boolean, default: false },
});
const emit = defineEmits(["expand", "collapse", "accept", "reject", "refine"]);

const locallyExpanded = ref(props.expanded);
const collapsing = ref(false);
const pendingCollapse = ref(null);
const completed = computed(() => ["accepted", "superseded"].includes(props.artifact.status));
const title = computed(() => {
  const value = props.artifact.target?.section || props.artifact.target?.quote || "正文修订";
  return value.length > 54 ? `${value.slice(0, 54)}…` : value;
});
const reasonPreview = computed(() => {
  const value = String(props.artifact.reason || "").trim();
  return value.length > 74 ? `${value.slice(0, 74)}…` : value;
});
const statusText = computed(() => ({
  pending: "待确认", accepted: "已应用", rejected: "已保留",
  expired: "原文已变化", superseded: "已微调",
}[props.artifact.status] || ""));

watch(() => props.expanded, (value) => {
  if (!collapsing.value) locallyExpanded.value = value;
});

watch(() => props.artifact.status, (status) => {
  if (!["accepted", "rejected", "superseded"].includes(status)) return;
  if (pendingCollapse.value) window.clearTimeout(pendingCollapse.value);
  collapsing.value = true;
  pendingCollapse.value = window.setTimeout(() => {
    locallyExpanded.value = false;
    collapsing.value = false;
    emit("collapse", props.artifact.id);
    pendingCollapse.value = null;
  }, 260);
});

onBeforeUnmount(() => {
  if (pendingCollapse.value) window.clearTimeout(pendingCollapse.value);
});

function toggle() {
  if (completed.value) return;
  if (locallyExpanded.value) {
    locallyExpanded.value = false;
    emit("collapse", props.artifact.id);
  } else {
    locallyExpanded.value = true;
    emit("expand", props.artifact);
  }
}

function clickAction(event, name) {
  event.stopPropagation();
  emit(name, props.artifact.id);
}
</script>

<template>
  <article
    class="revision-suggestion"
    :class="{ expanded: locallyExpanded, collapsing, complete: completed }"
    :data-artifact-id="artifact.id"
    :data-artifact-status="artifact.status"
    data-testid="revision-suggestion"
  >
    <button
      type="button"
      class="revision-suggestion-head"
      :aria-expanded="locallyExpanded"
      :disabled="completed"
      @click="toggle"
    >
      <component :is="locallyExpanded ? ChevronDown : ChevronRight" :size="14" aria-hidden="true" />
      <span class="revision-suggestion-title"><span class="revision-suggestion-title-text">{{ title }}</span></span>
      <span class="revision-suggestion-status" :data-status="artifact.status">{{ statusText }}</span>
    </button>
    <p v-if="reasonPreview" class="revision-suggestion-reason-preview">{{ reasonPreview }}</p>
    <div v-if="locallyExpanded || collapsing" class="revision-suggestion-details">
      <p v-if="artifact.reason" class="revision-suggestion-reason">{{ artifact.reason }}</p>
      <p class="revision-suggestion-location">{{ artifact.target?.quote }}</p>
      <div class="revision-suggestion-sources">
        <template v-for="source in artifact.sources || []" :key="sourceRefId(source)">
          <a
            v-if="sourceState(source).state === 'available' && (sourceState(source).url || sourceHref(source))"
            :href="sourceState(source).url || sourceHref(source)"
            target="_blank"
            rel="noopener noreferrer"
            :data-source-ref="sourceRefId(source)"
          >{{ source.title || source.id }} · {{ sourceStatusLabel(sourceState(source)) }}</a>
          <span v-else :data-source-ref="sourceRefId(source)">
            {{ source.title || source.id }} · {{ sourceStatusLabel(sourceState(source)) }}
          </span>
        </template>
      </div>
      <p v-if="artifact.status === 'expired'" class="revision-suggestion-expired">
        目标原文已变化，这条建议不能应用
      </p>
      <p v-if="artifact.annotationId" class="revision-suggestion-note">
        已关联批注，请在批注面板中处理
      </p>
      <p v-if="decideError" class="ai-message-error" role="alert">{{ decideError }}</p>
      <div
        v-if="artifact.status === 'pending' && !readOnly && !artifact.annotationId"
        class="revision-suggestion-actions"
      >
        <button type="button" data-testid="agent-accept" :disabled="sending || deciding" @click="clickAction($event, 'accept')">
          <Check :size="13" aria-hidden="true" />应用修改
        </button>
        <button type="button" data-testid="agent-reject" :disabled="sending || deciding" @click="clickAction($event, 'reject')">
          <X :size="13" aria-hidden="true" />保留原文
        </button>
        <button type="button" data-testid="agent-refine" :disabled="sending || deciding" @click="clickAction($event, 'refine')">
          <RefreshCw :size="13" aria-hidden="true" />微调
        </button>
      </div>
    </div>
  </article>
</template>
