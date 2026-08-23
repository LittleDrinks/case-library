import { afterEach, expect, it, vi } from "vitest";
import { readLocalDraft, storeLocalDraft } from "../lib/localDraft.js";
import { createCrashDraft } from "./useCrashDraft.js";

function setup(onRecover = vi.fn()) {
  const snapshot = { title: "本地标题", document: { type: "doc", content: [] } };
  const draft = createCrashDraft({
    userId: "u-1",
    caseId: "c-1",
    getRevision: () => 4,
    getSnapshot: () => snapshot,
    onRecover,
  });
  return { draft, snapshot, onRecover };
}

afterEach(() => {
  vi.useRealTimers();
  localStorage.clear();
});

it("浏览器崩溃恢复在编辑三百毫秒后保存本地快照", async () => {
    vi.useFakeTimers();
    const { draft, snapshot } = setup();

    draft.queue();
    await vi.advanceTimersByTimeAsync(300);

    expect(readLocalDraft("u-1", "c-1")?.snapshot).toEqual(snapshot);
    draft.destroy();
});

it("浏览器崩溃恢复同一基础修订并保留到服务端保存", () => {
    const { draft, snapshot, onRecover } = setup();
    storeLocalDraft("u-1", "c-1", 4, snapshot);

    expect(draft.load({ revision: 4, title: "服务端标题", document: snapshot.document })).toBe(true);
    expect(onRecover).toHaveBeenCalledWith(snapshot);
    expect(readLocalDraft("u-1", "c-1")).not.toBeNull();

    draft.saved(snapshot);
    expect(readLocalDraft("u-1", "c-1")).toBeNull();
});

it("浏览器崩溃恢复用新修订记录后续编辑", () => {
    let revision = 4;
    let current = { title: "后续编辑", document: { type: "doc", content: [] } };
    const draft = createCrashDraft({
      userId: "u-1", caseId: "c-1",
      getRevision: () => revision,
      getSnapshot: () => current,
      onRecover: vi.fn(),
    });
    storeLocalDraft("u-1", "c-1", 4, current);
    revision = 5;

    draft.saved({ title: "已保存内容", document: current.document });

    expect(readLocalDraft("u-1", "c-1")?.baseRevision).toBe(5);
    expect(readLocalDraft("u-1", "c-1")?.snapshot).toEqual(current);
});

it("浏览器崩溃恢复在基础修订过期时清除且不恢复", () => {
    const { draft, snapshot, onRecover } = setup();
    storeLocalDraft("u-1", "c-1", 3, snapshot);

    expect(draft.load({ revision: 4, title: "服务端标题", document: snapshot.document })).toBe(false);
    expect(onRecover).not.toHaveBeenCalled();
    expect(readLocalDraft("u-1", "c-1")).toBeNull();
});
