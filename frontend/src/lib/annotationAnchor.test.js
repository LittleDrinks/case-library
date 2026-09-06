import { afterEach, expect, it, vi } from "vitest";
import { hashQuote } from "./annotationAnchor.js";

afterEach(() => vi.unstubAllGlobals());

it("使用 SHA-256 生成选区引用哈希", async () => {
  await expect(hashQuote("选中的正文")).resolves.toBe(
    "02160444870fe0cc4b1d28962482d0eb5762f10c70396764d681d43a77a4e8e5",
  );
});

it("在不支持 WebCrypto 的本地来源仍生成相同哈希", async () => {
  vi.stubGlobal("crypto", {});
  await expect(hashQuote("选中的正文")).resolves.toBe(
    "02160444870fe0cc4b1d28962482d0eb5762f10c70396764d681d43a77a4e8e5",
  );
});
