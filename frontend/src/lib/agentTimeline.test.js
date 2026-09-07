import { describe, expect, it } from "vitest";
import {
  artifactStatus, durationText, elapsedBetween, sourceHref, sourceRefId,
  toolParamSummary, toolResultSummary, toolRunning, toolState,
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
    expect(toolState({ state: "output-error", errorText: "连接中断" })).toBe("连接中断");
    expect(toolState({ state: "output-error" })).toBe("执行失败");
  });
});

describe("tool parameter summaries", () => {
  it("summarizes readable parameters per known tool", () => {
    expect(toolParamSummary({ type: "tool-search_corpus", input: { query: "科学家", kind: "case" } }))
      .toBe("检索词：科学家（范围：case）");
    expect(toolParamSummary({ type: "tool-propose_revision", input: { paragraph_index: 1 } }))
      .toBe("目标：第 2 段");
  });

  it("keeps unknown tool parameters out of the summary", () => {
    expect(toolParamSummary({ type: "tool-future_tool", input: { secret: "x" } })).toBe("");
    expect(toolParamSummary({ type: "tool-list_tag_catalog", input: { query: "评价" } }))
      .toBe("筛选：评价");
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
});

describe("stable references", () => {
  it("builds in-site links only from stable business ids", () => {
    expect(sourceHref({ kind: "case", id: "c-42" })).toBe("#/cases/c-42");
    expect(sourceHref({ kind: "case", id: "c-42", versionId: "v-1" })).toBe("#/cases/c-42?versionId=v-1");
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
