<script setup>
import {
  ChevronDown, ChevronUp, MessageCircle, Paperclip, Sparkles,
} from "@lucide/vue";
import AgentChatPanel from "./AgentChatPanel.vue";
import AttachmentPanel from "./AttachmentPanel.vue";
import CommentPanel from "./CommentPanel.vue";
import VersionPanel from "./VersionPanel.vue";

const props = defineProps({
  active: { type: String, required: true },
  open: { type: Boolean, required: true },
  caseRecord: { type: Object, required: true },
  caseTitle: { type: String, required: true },
  caseDocument: { type: Object, required: true },
  user: { type: Object, default: null },
  editable: { type: Boolean, required: true },
  beforeAttachmentMutation: { type: Function, required: true },
  beforeVersionMutation: { type: Function, required: true },
  selection: { type: Object, default: null },
  writingContext: { type: Object, default: null },
  applyCandidate: { type: Function, required: true },
  rollbackCandidateBatch: { type: Function, required: true },
  candidateInvalidation: { type: Number, default: 0 },
  citedKeys: { type: Array, default: () => [] },
  activeCitation: { type: Object, default: null },
});
const emit = defineEmits([
  "select", "toggle", "case-refreshed", "case-restored", "mutation-state",
  "case-revised", "candidate-previews", "annotations",
  "insert-citation", "remove-citation",
]);

const tabs = [
  { id: "ai", label: "AI", icon: Sparkles },
  { id: "comments", label: "批注", icon: MessageCircle },
  { id: "files", label: "资料", icon: Paperclip },
];
function select(tab) {
  emit("select", tab);
}
</script>

<template>
  <aside class="assistant-rail" :class="{ open }">
    <nav class="assistant-tabs" aria-label="辅助面板">
      <button
        v-for="tab in tabs"
        :key="tab.id"
        type="button"
        :class="{ active: active === tab.id }"
        @click="select(tab.id)"
      >
        <component :is="tab.icon" :size="17" aria-hidden="true" />
        <b>{{ tab.label }}</b>
      </button>
      <button class="drawer-toggle" type="button" :title="open ? '收起面板' : '展开面板'" @click="emit('toggle')">
        <ChevronDown v-if="open" :size="18" aria-hidden="true" />
        <ChevronUp v-else :size="18" aria-hidden="true" />
      </button>
    </nav>

    <AgentChatPanel
      v-if="active === 'ai'"
      :case-record="caseRecord"
      :writing-context="writingContext"
      @case-revised="emit('case-revised', $event)"
    />

    <CommentPanel
      v-else-if="active === 'comments'"
      :case-record="caseRecord"
      :user="user"
      :selection="selection"
      @annotations="emit('annotations', $event)"
    />

    <AttachmentPanel
      v-else-if="active === 'files'"
      :case-record="caseRecord"
      :user="user"
      :editable="editable"
      :before-mutation="beforeAttachmentMutation"
      :cited-keys="citedKeys"
      :active-citation="activeCitation"
      @case-refreshed="emit('case-refreshed', $event)"
      @mutation-state="emit('mutation-state', $event)"
      @insert-citation="emit('insert-citation', $event)"
      @remove-citation="emit('remove-citation')"
    />
    <VersionPanel
      v-else-if="active === 'history'"
      :case-record="caseRecord"
      :user="user"
      :editable="editable"
      :before-mutation="beforeVersionMutation"
      @case-refreshed="emit('case-refreshed', $event)"
      @case-restored="emit('case-restored', $event)"
      @mutation-state="emit('mutation-state', $event)"
    />
  </aside>
</template>
