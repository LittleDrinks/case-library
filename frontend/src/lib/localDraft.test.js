import { afterEach, expect, it, vi } from "vitest";
import { clearLocalDraft, readLocalDraft, storeLocalDraft } from "./localDraft.js";

afterEach(() => {
  localStorage.clear();
  vi.restoreAllMocks();
});

it("浏览器恢复稿按用户和案例隔离基础修订与正文快照", () => {
    const snapshot = { title: "未保存标题", document: { type: "doc", content: [] } };

    expect(storeLocalDraft("u-1", "c-1", 7, snapshot)).toBe(true);
    expect(readLocalDraft("u-1", "c-1")).toEqual({
      userId: "u-1", caseId: "c-1", baseRevision: 7, snapshot,
    });
    expect(readLocalDraft("u-2", "c-1")).toBeNull();
});

it("浏览器恢复稿清除时不影响其他用户的同一案例", () => {
    storeLocalDraft("u-1", "c-1", 2, { title: "甲" });
    storeLocalDraft("u-2", "c-1", 2, { title: "乙" });

    clearLocalDraft("u-1", "c-1");

    expect(readLocalDraft("u-1", "c-1")).toBeNull();
    expect(readLocalDraft("u-2", "c-1")?.snapshot.title).toBe("乙");
});

it("浏览器恢复稿在存储配额异常时静默保留编辑流程", () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementationOnce(() => {
      throw new DOMException("Quota exceeded", "QuotaExceededError");
    });

    expect(storeLocalDraft("u-1", "c-1", 2, { title: "未保存" })).toBe(false);
});
