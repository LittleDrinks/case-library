<script setup>
import {
  ChevronDown, ChevronUp, MessageSquareText, Paperclip, Sparkles,
} from "@lucide/vue";
import AgentChatPanel from "./AgentChatPanel.vue";
import AttachmentPanel from "./AttachmentPanel.vue";
import CommentPanel from "./CommentPanel.vue";
import VersionPanel from "./VersionPanel.vue";

defineProps({
  active: { type: String, required: true },
  open: { type: Boolean, required: true },
  caseRecord: { type: Object, required: true },
  user: { type: Object, default: null },
  editable: { type: Boolean, required: true },
  beforeAttachmentMutation: { type: Function, required: true },
  beforeVersionMutation: { type: Function, required: true },
  selection: { type: Object, default: null },
});
const emit = defineEmits([
  "select", "toggle", "case-refreshed", "case-restored", "mutation-state",
  "annotations",
]);

const tabs = [
  { id: "ai", label: "AI", icon: Sparkles },
  { id: "comments", label: "批注", icon: MessageSquareText },
  { id: "files", label: "附件", icon: Paperclip },
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
      @case-refreshed="emit('case-refreshed', $event)"
      @mutation-state="emit('mutation-state', $event)"
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
