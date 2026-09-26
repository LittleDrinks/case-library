<script setup>
import { toolDiagnosticText, toolFailureSummary } from "../lib/agentTimeline.js";

const props = defineProps({
  part: { type: Object, required: true },
  duration: { type: String, default: "" },
});

function isResource(part) {
  return part.type?.startsWith("tool-read_skill_resource_");
}

function failed(part) {
  return ["output-error", "output-denied"].includes(part.state);
}

function denied(part) {
  return part.state === "output-denied";
}

function pathOf(part) {
  return part.output?.path || part.input?.path || "未知资源";
}

function errorOf(part) {
  return toolFailureSummary(part);
}

function labelOf(part) {
  if (denied(part)) return "读取资源已拒绝";
  if (failed(part)) return "读取资源失败";
  return part.state === "output-available" ? "已读取资源" : "正在读取资源";
}
</script>

<template>
  <details
    v-if="isResource(props.part)"
    class="agent-resource-trace"
    :class="{ error: failed(props.part) }"
    :open="!['output-available', 'output-error', 'output-denied'].includes(props.part.state) || undefined"
    :data-testid="failed(props.part) ? 'agent-skill-resource-error' : 'agent-skill-resource'"
  >
    <summary>{{ labelOf(props.part) }}：{{ pathOf(props.part) }}<template v-if="duration"> · {{ duration }}</template></summary>
    <p v-if="failed(props.part)" role="alert">{{ errorOf(props.part) }}</p>
    <details
      v-if="toolDiagnosticText(props.part)"
      data-testid="agent-tool-log"
    >
      <summary>技术日志</summary>
      <pre>{{ toolDiagnosticText(props.part) }}</pre>
    </details>
    <pre v-else-if="props.part.output?.content">{{ props.part.output.content }}</pre>
  </details>
</template>

<style scoped>
.agent-resource-trace { margin: 4px 0; color: var(--ink-2); font-size: 11px; }
.agent-resource-trace.error { color: var(--red); }
.agent-resource-trace p { margin: 0; }
.agent-resource-trace summary { cursor: pointer; overflow-wrap: anywhere; }
.agent-resource-trace pre { margin: 3px 0 0; padding: 5px 7px; background: var(--paper); white-space: pre-wrap; overflow-wrap: anywhere; }
</style>
