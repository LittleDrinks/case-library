<script setup>
import {
  ChevronDown, ChevronUp, MessageCircle, MessageSquareText, Paperclip, Sparkles,
} from "@lucide/vue";
import AgentChatPanel from "./AgentChatPanel.vue";
import AttachmentPanel from "./AttachmentPanel.vue";
import CommentPanel from "./CommentPanel.vue";
import PublicSourceList from "./PublicSourceList.vue";
import VersionPanel from "./VersionPanel.vue";
import WritingCandidatePanel from "./WritingCandidatePanel.vue";

const props = defineProps({
  active: { type: String, required: true },
  readOnly: { type: Boolean, default: false },
  versionId: { type: String, default: "" },
  sources: { type: Array, default: () => [] },
  sourcesLoading: { type: Boolean, default: false },
  sourcesError: { type: String, default: "" },
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
});
const emit = defineEmits([
  "select", "toggle", "case-refreshed", "case-restored", "mutation-state",
  "case-revised", "candidate-previews", "annotations", "sources-retry",
]);

const tabs = [
  { id: "ai", label: "AI", icon: Sparkles },
  { id: "chat", label: "对话", icon: MessageSquareText },
  { id: "comments", label: "批注", icon: MessageCircle },
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
        v-show="!readOnly || !['chat', 'comments'].includes(tab.id)"
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
      v-if="readOnly && active === 'ai' && user"
      :key="versionId || 'draft'"
      :case-record="caseRecord"
      :version-id="versionId"
      :read-only="readOnly"
      @case-revised="emit('case-revised', $event)"
    />
    <div v-else-if="readOnly && active === 'ai'" class="panel-empty">
      <RouterLink :to="{ name: 'login' }">登录后讨论本案例</RouterLink>
    </div>
    <WritingCandidatePanel
      v-else-if="active === 'ai'"
      :case-title="caseTitle"
      :case-document="caseDocument"
      :case-id="caseRecord.id"
      :revision="caseRecord.revision"
      :user="user"
      :editable="editable"
      :selection="selection"
      :writing-context="writingContext"
      :apply-candidate="applyCandidate"
      :rollback-candidate-batch="rollbackCandidateBatch"
      :candidate-invalidation="candidateInvalidation"
      @candidate-previews="emit('candidate-previews', $event)"
    />

    <AgentChatPanel
      v-else-if="!readOnly && active === 'chat'"
      :open="open"
      :case-record="caseRecord"
      :writing-context="writingContext"
      @case-revised="emit('case-revised', $event)"
    />

    <CommentPanel
      v-else-if="!readOnly && active === 'comments'"
      :case-record="caseRecord"
      :user="user"
      :selection="selection"
      @annotations="emit('annotations', $event)"
    />

    <div v-else-if="readOnly && active === 'files'" class="assistant-panel panel-scroll">
      <PublicSourceList
        :sources="sources"
        :loading="sourcesLoading"
        :error="sourcesError"
        @retry="emit('sources-retry')"
      />
    </div>
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
