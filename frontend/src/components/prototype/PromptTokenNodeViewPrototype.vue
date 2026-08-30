<script setup>
import { FileText, FolderSearch, WandSparkles, X } from "@lucide/vue";
import { NodeViewWrapper, nodeViewProps } from "@tiptap/vue-3";
import { computed } from "vue";

const props = defineProps(nodeViewProps);
const attrs = computed(() => props.node.attrs);
const skill = computed(() => attrs.value.tokenType === "skill");

function remove(event) {
  event.preventDefault();
  event.stopPropagation();
  props.deleteNode();
}
</script>

<template>
  <NodeViewWrapper
    as="span"
    :class="[skill ? 'prompt-skill-token' : 'prompt-context-token', { 'is-selected': selected }]"
    :data-prompt-token="attrs.partId"
    :data-resource-id="attrs.resourceId || undefined"
    :data-skill-id="attrs.skillId || undefined"
  >
    <WandSparkles v-if="skill" :size="12" />
    <FileText v-else-if="attrs.kind === 'selection'" :size="12" />
    <FolderSearch v-else :size="12" />
    <b>{{ attrs.label }}</b><small v-if="skill">{{ attrs.version }}</small>
    <button type="button" :aria-label="skill ? `删除 Skill ${attrs.label}` : `删除引用${attrs.label}`" @mousedown="remove"><X :size="11" /></button>
  </NodeViewWrapper>
</template>
