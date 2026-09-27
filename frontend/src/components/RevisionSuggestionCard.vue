<script setup>
import { Check, ChevronDown, ChevronRight, RefreshCw, Undo2, X } from "@lucide/vue";
import { computed, ref, watch } from "vue";
import { sourceHref, sourceRefId, sourceStatusLabel } from "../lib/agentTimeline.js";

const props = defineProps({
  artifact: { type: Object, required: true },
  expanded: { type: Boolean, default: false },
  sending: { type: Boolean, default: false },
  deciding: { type: Boolean, default: false },
  writeStatus: { type: String, default: "written" },
  decideError: { type: String, default: "" },
  sourceState: { type: Function, default: () => ({ state: "checking" }) },
  readOnly: { type: Boolean, default: false },
});
const emit = defineEmits(["expand", "collapse", "accept", "reject", "refine", "undo"]);

const locallyExpanded = ref(props.expanded);
let pointerDown = false;
const undone = computed(() => props.artifact.status === "accepted" && props.writeStatus === "undone");
const actionsDisabled = computed(() => props.sending || props.deciding || props.artifact.provisional);
const completed = computed(() => props.artifact.status === "superseded");
const title = computed(() => {
  const value = props.artifact.target?.quote || "正文修订";
  return value.length > 54 ? `${value.slice(0, 54)}…` : value;
});
const reasonPreview = computed(() => {
  const value = String(props.artifact.reason || "").trim();
  return value.length > 74 ? `${value.slice(0, 74)}…` : value;
});
const statusText = computed(() => props.artifact.provisional ? "生成中" : undone.value ? "已撤销" : ({
  pending: "待确认", accepted: "已应用", rejected: "已保留",
  expired: "原文已变化", superseded: "已微调",
}[props.artifact.status] || ""));

watch(() => props.expanded, (value) => {
  locallyExpanded.value = value;
});

function toggle() {
  if (locallyExpanded.value) {
    locallyExpanded.value = false;
    emit("collapse", props.artifact.id);
  } else {
    locallyExpanded.value = true;
    emit("expand", props.artifact);
  }
}

function focusCard(event) {
  if (pointerDown || event.currentTarget.contains(event.relatedTarget)) return;
  locallyExpanded.value = true;
  emit("expand", props.artifact);
}

function clickAction(event, name) {
  event.stopPropagation();
  emit(name, props.artifact.id);
}
</script>

<template>
  <article
    class="revision-suggestion"
    :class="{ expanded: locallyExpanded, complete: completed }"
    :data-artifact-id="artifact.id"
    :data-artifact-status="artifact.status"
    data-testid="revision-suggestion"
    @pointerdown="pointerDown = true"
    @pointerup="pointerDown = false"
    @pointercancel="pointerDown = false"
    @pointerleave="pointerDown = false"
    @focusin="focusCard"
  >
    <button
      type="button"
      class="revision-suggestion-head"
      :aria-expanded="locallyExpanded"
      @click="toggle"
    >
      <component :is="locallyExpanded ? ChevronDown : ChevronRight" :size="14" aria-hidden="true" />
      <span class="revision-suggestion-title"><span class="revision-suggestion-title-text">{{ title }}</span></span>
      <span class="revision-suggestion-status" :data-status="undone ? 'undone' : artifact.status">{{ statusText }}</span>
    </button>
    <Transition name="revision-expand">
      <div v-if="reasonPreview && !locallyExpanded" class="revision-suggestion-expansion">
        <div class="revision-suggestion-clip">
          <p class="revision-suggestion-reason-preview">{{ reasonPreview }}</p>
        </div>
      </div>
    </Transition>
    <Transition name="revision-expand">
    <div v-if="locallyExpanded" class="revision-suggestion-expansion">
    <div class="revision-suggestion-clip">
    <div class="revision-suggestion-details">
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
      <p v-if="decideError" class="ai-message-error" role="alert">{{ decideError }}</p>
      <div
        v-if="!readOnly && (artifact.status === 'pending' || artifact.status === 'accepted' && artifact.writeId)"
        class="revision-suggestion-actions"
      >
        <button v-if="undone" type="button" data-testid="agent-redo-revision" :disabled="actionsDisabled" @click="clickAction($event, 'accept')">
          <RefreshCw :size="13" aria-hidden="true" />再次应用
        </button>
        <button v-else-if="artifact.status === 'accepted'" type="button" data-testid="agent-undo-revision" :disabled="actionsDisabled" @click.stop="emit('undo', artifact.writeId)">
          <Undo2 :size="13" aria-hidden="true" />撤销修改
        </button>
        <template v-else>
        <button type="button" data-testid="agent-accept" :disabled="actionsDisabled" @click="clickAction($event, 'accept')">
          <Check :size="13" aria-hidden="true" />应用修改
        </button>
        <button type="button" data-testid="agent-reject" :disabled="actionsDisabled" @click="clickAction($event, 'reject')">
          <X :size="13" aria-hidden="true" />保留原文
        </button>
        </template>
        <button type="button" data-testid="agent-refine" :disabled="actionsDisabled" @click="clickAction($event, 'refine')">
          <RefreshCw :size="13" aria-hidden="true" />微调
        </button>
      </div>
    </div>
    </div>
    </div>
    </Transition>
  </article>
</template>
