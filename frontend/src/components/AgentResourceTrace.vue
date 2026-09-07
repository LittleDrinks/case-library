<script setup>
const props = defineProps({
  part: { type: Object, required: true },
});

function isResource(part) {
  return part.type?.startsWith("tool-read_skill_resource_");
}

function failed(part) {
  return part.state === "output-error";
}

function pathOf(part) {
  return part.output?.path || part.input?.path || "未知资源";
}

function errorOf(part) {
  return part.errorText || "资源读取失败";
}
</script>

<template>
  <div
    v-if="isResource(props.part)"
    class="agent-resource-trace"
    :class="{ error: failed(props.part) }"
    :data-testid="failed(props.part) ? 'agent-skill-resource-error' : 'agent-skill-resource'"
  >
    <p>{{ failed(props.part) ? "读取资源失败" : "已读取资源" }}：{{ pathOf(props.part) }}</p>
    <p v-if="failed(props.part)">{{ errorOf(props.part) }}</p>
    <pre v-else-if="props.part.output?.content">{{ props.part.output.content }}</pre>
  </div>
</template>

<style scoped>
.agent-resource-trace { margin: 4px 0; color: var(--ink-2); font-size: 11px; }
.agent-resource-trace.error { color: var(--red); }
.agent-resource-trace p { margin: 0; }
.agent-resource-trace pre { max-height: 140px; margin: 3px 0 0; padding: 5px 7px; overflow: auto; background: var(--paper); white-space: pre-wrap; }
</style>
