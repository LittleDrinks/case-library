import { describe, expect, it } from "vitest";
import { versionPaperLabel } from "./version.js";

describe("versionPaperLabel", () => {
  it("labels AI versions distinctly", () => {
    expect(versionPaperLabel({ kind: "ai" })).toBe("AI生成版本");
  });

  it("labels submission versions", () => {
    expect(versionPaperLabel({ kind: "submission" })).toBe("提交版本");
  });
});
