import { describe, expect, it } from "vitest";
import { candidateDiff, parseCandidateResponse } from "./writingCandidate.js";

describe("AI 写作候选", () => {
  it("只接受包含正文和理由的结构化候选", () => {
    const response = '```json\n{"text":"新正文","reason":"对应教学目标"}\n```';
    expect(parseCandidateResponse(response)).toEqual({
      text: "新正文", reason: "对应教学目标",
    });
    expect(() => parseCandidateResponse("直接改成新正文")).toThrow("候选格式无效");
  });

  it("文本 diff 分开标记删除、新增和保留内容", () => {
    expect(candidateDiff("课堂讲授", "课堂讨论")).toEqual([
      { value: "课堂", kind: "equal" },
      { value: "讲授", kind: "removed" },
      { value: "讨论", kind: "added" },
    ]);
  });
});
