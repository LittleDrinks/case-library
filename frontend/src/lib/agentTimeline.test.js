import { describe, expect, it } from "vitest";
import {
  artifactStatus, durationText, elapsedBetween, sourceHref, sourceRefId,
  toolParamSummary, toolResultSummary, toolRunning, toolState,
  toolDiagnosticText,
} from "./agentTimeline.js";

describe("tool running states", () => {
  it("treats every non-terminal state as running", () => {
    expect(toolRunning({ state: "input-streaming" })).toBe(true);
    expect(toolRunning({ state: "input-available" })).toBe(true);
    expect(toolRunning({ state: "output-available" })).toBe(false);
    expect(toolRunning({ state: "output-error" })).toBe(false);
  });

  it("maps terminal states to readable labels including failures", () => {
    expect(toolState({ state: "input-available" })).toBe("进行中");
    expect(toolState({ state: "output-available", output: { status: "ok" } })).toBe("已完成");
    expect(toolState({ state: "output-available", output: { status: "no_access" } })).toBe("当前身份无权限读取");
    expect(toolState({ state: "output-available", output: { status: "future_status" } }))
      .toBe("结果状态未知");
    expect(toolState({ state: "output-error", errorText: "连接中断" })).toBe("未完成");
    expect(toolState({ state: "output-error" })).toBe("未完成");
    expect(toolRunning({ state: "output-denied" })).toBe(false);
    expect(toolState({ state: "output-denied" })).toBe("已拒绝");
  });
});

describe("tool parameter summaries", () => {
  it("summarizes readable parameters per known tool", () => {
    expect(toolParamSummary({ type: "tool-search_corpus", input: { query: "科学家", kind: "case" } }))
      .toBe("检索词：科学家（范围：case）");
    expect(toolParamSummary({ type: "tool-propose_revision", input: { start: 9, end: 13 } }))
      .toBe("目标：9–13");
  });

  it("keeps unknown tool parameters out of the summary", () => {
    expect(toolParamSummary({ type: "tool-future_tool", input: { secret: "x" } })).toBe("");
    expect(toolParamSummary({ type: "tool-list_tag_catalog", input: { query: "评价" } }))
      .toBe("筛选：评价");
  });
});

describe("document write scope summaries", () => {
  it("summarizes whole-draft scopes without character positions", () => {
    expect(toolParamSummary({ type: "tool-propose_document", input: {} }))
      .toBe("范围：全文（AI版本）");
    expect(toolParamSummary({ type: "tool-write_document", input: { scope: "document" } }))
      .toBe("范围：全文");
    expect(toolParamSummary({ type: "tool-write_document", input: { scope: "selection" } }))
      .toBe("范围：选区");
  });
});

describe("tool result summaries", () => {
  it("summarizes result counts without leaking raw payloads", () => {
    expect(toolResultSummary({ type: "tool-search_corpus", state: "output-available", output: { sources: [{}, {}] } }))
      .toBe("2 条来源");
    expect(toolResultSummary({ type: "tool-read_source", state: "output-available", output: { content: "SECRET" } }))
      .toBe("");
  });

  it("points at the pending decision without leaking payloads", () => {
    expect(toolResultSummary({ type: "tool-propose_revision", state: "output-available", output: { artifactId: "a-1" } }))
      .toBe("已创建修订候选，等待决定");
  });

  it("gives operation-specific next steps without exposing internal errors", () => {
    const failedSearch = {
      type: "tool-search_corpus", state: "output-error",
      errorText: "Error: internal provider failure",
    };
    expect(toolResultSummary(failedSearch, { status: "active" }))
      .toBe("案例检索未能完成。本轮仍在处理，请等待后续结果。");
    expect(toolResultSummary(failedSearch, { status: "completed" }))
      .toBe("案例检索未能完成。本轮已结束；请调整检索范围或查询词后重新发起请求。");
    expect(toolResultSummary(failedSearch, { status: "completed" })).not.toContain("internal provider");
    expect(toolResultSummary({
      type: "tool-search_corpus", state: "output-available",
      output: { status: "future_status" },
    })).toBe("工具返回了无法识别的结果状态");
  });

  it("explains the explicit missing-reason validation without exposing wrapped diagnostics", () => {
    const errorText = "工具校验失败：修订必须给出具体修改理由，且不能为空白；internal provider detail";
    const failedRevision = {
      type: "tool-propose_revision", state: "output-error", errorText,
    };
    const summary = toolResultSummary(failedRevision, { status: "completed" });

    expect(summary)
      .toBe("缺少具体修改理由，修订建议未能生成。本轮已结束；请补充具体修改理由后重新发送。");
    expect(summary).not.toContain("internal provider detail");
    expect(toolDiagnosticText(failedRevision)).toBe(errorText);
  });

  it("explains denied tool calls as unexecuted actions", () => {
    expect(toolResultSummary({ type: "tool-search_corpus", state: "output-denied" }))
      .toBe("这项操作未获授权，因此没有执行。请改用可访问的资料或调整请求后继续。");
  });

  it("explains structured source access failures with an alternative", () => {
    expect(toolResultSummary({
      type: "tool-read_source", state: "output-available",
      output: { status: "no_access", detail: "来源当前不可读" },
    })).toBe("当前身份无权读取此来源（来源当前不可读）。请改用其他可访问来源后继续。");
  });
});

describe("document write result summaries", () => {
  it("reports AI versions without leaking payloads", () => {
    const propose = { type: "tool-propose_document", state: "output-available" };
    expect(toolResultSummary({ ...propose, output: { status: "created", versionId: "cv-2" } }))
      .toBe("已保存 AI 版本，可在版本时间线查看");
    expect(toolResultSummary({ ...propose, output: { status: "not_saved" } }))
      .toBe("AI 版本未保存");
  });

  it("reports direct writes only when truly written", () => {
    const write = { type: "tool-write_document", state: "output-available" };
    expect(toolResultSummary({ ...write, output: { status: "written", id: "w-1" } }))
      .toBe("已写入正文，可撤销");
    expect(toolResultSummary({
      ...write, output: { status: "written", id: "w-1", versionStatus: "created" },
    })).toBe("已写入正文并保存 AI 版本，可撤销");
    expect(toolResultSummary({ ...write, output: {} })).toBe("");
  });
});

describe("stable references", () => {
  it("builds in-site links only from stable business ids", () => {
    expect(sourceHref({ kind: "case", id: "c-42" })).toBe("#/cases/c-42");
    expect(sourceHref({ kind: "case", id: "mounted-1", sourceCaseId: "c-42", versionId: "v-1" })).toBe("#/cases/c-42?versionId=v-1");
    expect(sourceHref({ kind: "case", id: "mounted-1", versionId: "v-1" })).toBe("");
    expect(sourceHref({ sourceType: "material", id: "m-7" })).toBe("#/materials/m-7");
    expect(sourceHref({ url: "https://evil.example/x" })).toBe("");
  });

  it("keeps a stable reference id per source", () => {
    expect(sourceRefId({ kind: "case", id: "c-42" })).toBe("case:c-42");
    expect(sourceRefId({ sourceType: "attachment", id: "a-1" })).toBe("attachment:a-1");
    expect(sourceRefId({ kind: "case", id: "c-42", versionId: "v-1" })).toBe("case:c-42:v-1");
  });
});

it("labels artifact decisions including expiry", () => {
  expect(artifactStatus({ status: "pending" })).toBe("待确认");
  expect(artifactStatus({ status: "expired" })).toBe("已过期");
  expect(artifactStatus({ status: "weird" })).toBe("weird");
});

describe("real durations", () => {
  it("formats seconds into readable lengths", () => {
    expect(durationText(2.34)).toBe("2.3s");
    expect(durationText(120)).toBe("120s");
    expect(durationText(Number.NaN)).toBe("");
  });

  it("computes elapsed only from valid real timestamps", () => {
    expect(elapsedBetween("2026-09-07T10:00:00Z", "2026-09-07T10:00:03.5Z")).toBe("3.5s");
    expect(elapsedBetween("bad", "2026-09-07T10:00:03Z")).toBe("");
    expect(elapsedBetween("2026-09-07T10:00:03Z", "2026-09-07T10:00:00Z")).toBe("");
  });

  it("measures a still-running span up to the given now", () => {
    const now = Date.parse("2026-09-07T10:00:07Z");
    expect(elapsedBetween("2026-09-07T10:00:00Z", undefined, now)).toBe("7.0s");
  });
});
