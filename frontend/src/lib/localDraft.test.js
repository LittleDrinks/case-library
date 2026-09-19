import { afterEach, expect, it, vi } from "vitest";
import {
  clearLocalDraft, readLocalDraft, sameDraft, storeLocalDraft,
} from "./localDraft.js";

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

it("没有草稿时读取返回 null", () => {
  expect(readLocalDraft("u-missing", "c-missing")).toBeNull();
});

it("损坏 JSON 和读取异常都返回 null", () => {
  storeLocalDraft("u-1", "c-1", 2, { title: "损坏前" });
  const storageKey = localStorage.key(0);
  localStorage.setItem(storageKey, "{");
  expect(readLocalDraft("u-1", "c-1")).toBeNull();

  vi.spyOn(Storage.prototype, "getItem").mockImplementationOnce(() => {
    throw new DOMException("read failed");
  });
  expect(readLocalDraft("u-1", "c-1")).toBeNull();
});

it("清除不存在草稿与移除异常都保持静默", () => {
  expect(clearLocalDraft("u-missing", "c-missing")).toBeUndefined();
  vi.spyOn(Storage.prototype, "removeItem").mockImplementationOnce(() => {
    throw new DOMException("remove failed");
  });
  expect(clearLocalDraft("u-1", "c-1")).toBeUndefined();
});

it("相同标题但不同正文不视为同一恢复稿", () => {
  const title = "同标题";
  expect(sameDraft(
    { snapshot: { title, document: { type: "doc", content: [] } } },
    { title, document: { type: "doc", content: [{ type: "paragraph" }] } },
  )).toBe(false);
});

it("缺少恢复稿快照时不匹配", () => {
  expect(sameDraft(null, { title: "标题", document: { type: "doc" } })).toBe(false);
  expect(sameDraft(undefined, { title: "标题", document: { type: "doc" } })).toBe(false);
  expect(sameDraft({}, { title: "标题", document: { type: "doc" } })).toBe(false);
  expect(sameDraft({ snapshot: null }, { title: "标题", document: { type: "doc" } })).toBe(false);
});

it("浏览器恢复稿在存储配额异常时静默保留编辑流程", () => {
  vi.spyOn(Storage.prototype, "setItem").mockImplementationOnce(() => {
    throw new DOMException("Quota exceeded", "QuotaExceededError");
  });

  expect(storeLocalDraft("u-1", "c-1", 2, { title: "未保存" })).toBe(false);
});
