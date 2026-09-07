export const TOOL_LABELS = {
  load_capability: "加载 Skill", search_corpus: "检索案例", list_tag_catalog: "查询标签",
  read_source: "阅读来源", propose_revision: "生成修订建议",
};
export const TOOL_STATUS_LABELS = {
  ok: "已完成", pending: "待确认", unavailable: "无法读取", not_found: "未找到",
  no_access: "当前身份无权限读取", empty: "内容为空", error: "读取失败",
};
export const ARTIFACT_STATUS_LABELS = {
  accepted: "已接受", rejected: "已拒绝", expired: "已过期", pending: "待确认",
};
export const RUN_STATUS_LABELS = {
  active: "运行中", completed: "已完成", failed: "运行失败", cancelled: "已取消",
};
export const SOURCE_STATUS_LABELS = {
  checking: "正在核验来源权限", available: "当前可读取", restricted: "当前权限不可读取",
  unavailable: "来源已下线或不可读取",
};

export function toolName(part) {
  return part.type.slice(5);
}

export function toolLabel(part) {
  return TOOL_LABELS[toolName(part)] || toolName(part);
}

export function toolRunning(part) {
  return part.state !== "output-available" && part.state !== "output-error";
}

export function toolState(part) {
  if (part.state === "output-error") return part.errorText || "执行失败";
  if (part.state !== "output-available") return "进行中";
  return TOOL_STATUS_LABELS[part.output?.status] || "已完成";
}

export function sourcesOf(part) {
  if (part.type === "data-source" && part.data?.id) {
    return [{ ...part.data, kind: part.data.sourceType, fromCaseArea: true }];
  }
  return part.state === "output-available" ? part.output?.sources || [] : [];
}

export function toolParamSummary(part) {
  const input = part.input || {};
  if (toolName(part) === "search_corpus") {
    const scope = input.kind && input.kind !== "all" ? `（范围：${input.kind}）` : "";
    return `检索词：${input.query ?? ""}${scope}`;
  }
  if (toolName(part) === "read_source") return `来源：${input.source_type || ""} ${input.source_id || ""}`;
  if (toolName(part) === "propose_revision") {
    return Number.isInteger(input.start) && Number.isInteger(input.end)
      ? `目标：${input.start}–${input.end}` : "";
  }
  if (toolName(part) === "list_tag_catalog") return input.query ? `筛选：${input.query}` : "";
  return "";
}

export function toolResultSummary(part) {
  if (part.state === "output-error") return part.errorText || "执行失败";
  if (part.state !== "output-available") return "";
  const output = part.output || {};
  if (output.artifactId) return "已创建修订候选，等待决定";
  if (part.type === "tool-search_corpus" && !output.sources?.length) return "依据不足，未找到可用来源";
  if (part.type === "tool-search_corpus") return `${(output.sources || []).length} 条来源`;
  if (typeof output.status === "string" && output.status !== "ok") {
    return TOOL_STATUS_LABELS[output.status] || output.status;
  }
  return "";
}

export function sourceHref(source) {
  const kind = source.kind || source.sourceType;
  if (kind === "case") {
    if (source.versionId && !source.sourceCaseId) return "";
    if (source.sourceCaseId && !source.versionId) return "";
    const version = source.versionId ? `?versionId=${encodeURIComponent(source.versionId)}` : "";
    return `#/cases/${encodeURIComponent(source.sourceCaseId || source.id)}${version}`;
  }
  if (kind === "material") return `#/materials/${encodeURIComponent(source.id)}`;
  return "";
}

export function artifactStatus(artifact) {
  return ARTIFACT_STATUS_LABELS[artifact.status] || artifact.status;
}

export function sourceRefId(source) {
  const version = source.versionId ? `:${source.versionId}` : "";
  return `${source.kind || source.sourceType || "unknown"}:${source.id}${version}`;
}

export function sourceStatusLabel(state) {
  return SOURCE_STATUS_LABELS[state?.state] || "无法核验来源状态";
}

export function durationText(seconds) {
  if (!Number.isFinite(seconds) || seconds < 0) return "";
  return seconds >= 100 ? `${Math.round(seconds)}s` : `${seconds.toFixed(1)}s`;
}

export function elapsedBetween(startedAt, finishedAt, now) {
  const start = Date.parse(startedAt);
  if (!Number.isFinite(start)) return "";
  const end = finishedAt ? Date.parse(finishedAt) : now;
  if (!Number.isFinite(end) || end < start) return "";
  return durationText((end - start) / 1000);
}

export function runLabel(run) {
  return RUN_STATUS_LABELS[run?.status] || "运行状态未知";
}

export function runError(run) {
  if (run?.error) return run.error;
  if (run?.status === "failed") return "AI 服务暂不可用";
  return run?.status === "cancelled" ? "运行已取消" : "";
}

export function runForMessage(message, runs = []) {
  const id = message?.metadata?.agentRunId || message?.metadata?.runId;
  return runs.find((run) => run.id === id
    || run.userMessageId === message?.id || run.assistantMessageId === message?.id) || null;
}

export function runAnchor(message, run, messages = []) {
  if (!run) return false;
  if (run.assistantMessageId === message?.id) return true;
  return run.userMessageId === message?.id
    && !messages.some((item) => item.id === run.assistantMessageId);
}
