export const TOOL_LABELS = {
  load_capability: "加载 Skill", search_corpus: "检索案例", list_tag_catalog: "查询标签",
  read_source: "阅读来源", propose_revision: "生成修订建议",
  propose_document: "生成 AI 版本", write_document: "直接写入正文",
};
export const TOOL_STATUS_LABELS = {
  ok: "已完成", pending: "处理中", created: "已创建", not_saved: "未保存",
  unavailable: "无法读取", not_found: "未找到",
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

const TOOL_PARAM_SUMMARIES = {
  search_corpus: (input) => {
    const scope = input.kind && input.kind !== "all" ? `（范围：${input.kind}）` : "";
    return `检索词：${input.query ?? ""}${scope}`;
  },
  read_source: (input) => `来源：${input.source_type || ""} ${input.source_id || ""}`,
  propose_revision: (input) => Number.isInteger(input.start) && Number.isInteger(input.end)
    ? `目标：${input.start}–${input.end}` : "",
  propose_document: () => "范围：全文（AI版本）",
  write_document: (input) => input.scope === "selection" ? "范围：选区" : "范围：全文",
  list_tag_catalog: (input) => input.query ? `筛选：${input.query}` : "",
};

export function toolParamSummary(part) {
  const name = toolName(part);
  const summarize = Object.hasOwn(TOOL_PARAM_SUMMARIES, name) ? TOOL_PARAM_SUMMARIES[name] : null;
  return summarize ? summarize(part.input || {}) : "";
}

const TOOL_RESULT_SUMMARIES = {
  "tool-propose_document": documentResultSummary,
  "tool-write_document": (output) => directWriteResultSummary(output),
  "tool-search_corpus": (output) => output.artifactId ? null : output.sources?.length
    ? `${output.sources.length} 条来源` : "依据不足，未找到可用来源",
};

export function toolResultSummary(part) {
  if (part.state === "output-error") return part.errorText || "执行失败";
  if (part.state !== "output-available") return "";
  const output = part.output || {};
  const summarize = Object.hasOwn(TOOL_RESULT_SUMMARIES, part.type)
    ? TOOL_RESULT_SUMMARIES[part.type] : null;
  const summary = summarize ? summarize(output) : null;
  return summary !== null ? summary : genericResultSummary(output);
}

function genericResultSummary(output) {
  if (output.artifactId) return "已创建修订候选，等待决定";
  if (typeof output.status === "string" && output.status !== "ok") {
    return TOOL_STATUS_LABELS[output.status] || output.status;
  }
  return "";
}

function directWriteResultSummary(output) {
  if (output.status !== "written") return null;
  if (output.versionStatus === "created") return "已写入正文并保存 AI 版本，可撤销";
  if (output.versionStatus === "not_saved") return output.versionDetail || "正文已写入，AI版本未保存";
  return "已写入正文，可撤销";
}

function documentResultSummary(output) {
  if (output.status === "created") return "已保存 AI 版本，可在版本时间线查看";
  if (output.status === "not_saved") return output.detail || "AI 版本未保存";
  return output.status === "pending" ? "正在保存 AI 版本" : "";
}

const SOURCE_HREF_BUILDERS = {
  case: (source) => {
    if (Boolean(source.versionId) !== Boolean(source.sourceCaseId)) return "";
    const version = source.versionId ? `?versionId=${encodeURIComponent(source.versionId)}` : "";
    return `#/cases/${encodeURIComponent(source.sourceCaseId || source.id)}${version}`;
  },
  material: (source) => `#/materials/${encodeURIComponent(source.id)}`,
};

export function sourceHref(source) {
  const kind = source.kind || source.sourceType;
  const build = Object.hasOwn(SOURCE_HREF_BUILDERS, kind) ? SOURCE_HREF_BUILDERS[kind] : null;
  return build ? build(source) : "";
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
