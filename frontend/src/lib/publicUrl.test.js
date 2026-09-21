import { describe, expect, it } from "vitest";
import { publicUrl } from "./publicUrl.js";

describe("publicUrl", () => {
  it("accepts HTTP and HTTPS URLs", () => {
    expect(publicUrl("http://example.com/path?q=1")).toBe("http://example.com/path?q=1");
    expect(publicUrl("https://example.com/path?q=1")).toBe("https://example.com/path?q=1");
  });

  it("returns no link for invalid or non-public URLs", () => {
    expect(publicUrl("not a URL")).toBe("");
    expect(publicUrl("javascript:alert(1)")).toBe("");
  });
});
