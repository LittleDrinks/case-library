import { afterEach, expect, it, vi } from "vitest";
import { readLocalDraft, storeLocalDraft } from "../lib/localDraft.js";
import { createCrashDraft } from "./useCrashDraft.js";

function setup(onRecover = vi.fn(), overrides = {}) {
  const snapshot = { title: "本地标题", document: { type: "doc", content: [] } };
  const draft = createCrashDraft({
    userId: "u-1",
    caseId: "c-1",
    getRevision: () => 4,
    getSnapshot: () => snapshot,
    onRecover,
    ...overrides,
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

  expect(draft.load({
    revision: 4, title: "服务端标题", document: snapshot.document,
  })).toBe(true);
  expect(onRecover).toHaveBeenCalledWith(snapshot);
  expect(readLocalDraft("u-1", "c-1")).not.toBeNull();

  draft.saved(snapshot);
  expect(readLocalDraft("u-1", "c-1")).toBeNull();
});

it("浏览器崩溃恢复用新修订记录后续编辑", () => {
  let revision = 4;
  const current = { title: "后续编辑", document: { type: "doc", content: [] } };
  const draft = createCrashDraft({
    userId: "u-1", caseId: "c-1",
    getRevision: () => revision,
    getSnapshot: () => current,
    onRecover: vi.fn(),
  });
  storeLocalDraft("u-1", "c-1", 4, current);
  revision = 5;

  draft.saved({ title: "已保存内容", document: current.document });

  expect(readLocalDraft("u-1", "c-1")).toEqual({
    userId: "u-1", caseId: "c-1", baseRevision: 5, snapshot: current,
  });
});

it("浏览器崩溃恢复在基础修订过期时清除且不恢复", () => {
  const { draft, snapshot, onRecover } = setup();
  storeLocalDraft("u-1", "c-1", 3, snapshot);

  expect(draft.load({
    revision: 4, title: "服务端标题", document: snapshot.document,
  })).toBe(false);
  expect(onRecover).not.toHaveBeenCalled();
  expect(readLocalDraft("u-1", "c-1")).toBeNull();
});

it("没有本地稿时加载返回 false且不恢复", () => {
  const { draft, onRecover } = setup();

  expect(draft.load({ revision: 4, title: "服务端标题", document: { type: "doc" } })).toBe(false);
  expect(onRecover).not.toHaveBeenCalled();
});

it("干净 flush 不会创建幽灵恢复稿", () => {
  const { draft } = setup();

  draft.flush();

  expect(readLocalDraft("u-1", "c-1")).toBeNull();
});

it("排队快照可由立即 flush 持久化", () => {
  vi.useFakeTimers();
  const { draft, snapshot } = setup();

  draft.queue();
  draft.flush();
  draft.destroy();

  expect(readLocalDraft("u-1", "c-1")?.snapshot).toEqual(snapshot);
});

it("服务端保存相同快照后清除并保持 clean", () => {
  vi.useFakeTimers();
  const { draft, snapshot } = setup();
  draft.queue();
  draft.saved(snapshot);
  draft.flush();
  draft.destroy();

  expect(readLocalDraft("u-1", "c-1")).toBeNull();
});

it("destroy 会取消尚未到期的排队保存", async () => {
  vi.useFakeTimers();
  const { draft } = setup();

  draft.queue();
  draft.destroy();
  await vi.advanceTimersByTimeAsync(301);

  expect(readLocalDraft("u-1", "c-1")).toBeNull();
});

it("零毫秒自定义 debounce 在计时器运行后保存", async () => {
  vi.useFakeTimers();
  const { draft, snapshot } = setup(vi.fn(), { delayMs: 0 });

  draft.queue();
  await vi.advanceTimersByTimeAsync(0);
  draft.destroy();

  expect(readLocalDraft("u-1", "c-1")?.snapshot).toEqual(snapshot);
});

it("五十毫秒自定义 debounce 在截止前不保存、到期后保存", async () => {
  vi.useFakeTimers();
  const { draft, snapshot } = setup(vi.fn(), { delayMs: 50 });

  draft.queue();
  await vi.advanceTimersByTimeAsync(49);
  expect(readLocalDraft("u-1", "c-1")).toBeNull();
  await vi.advanceTimersByTimeAsync(1);
  draft.destroy();

  expect(readLocalDraft("u-1", "c-1")?.snapshot).toEqual(snapshot);
});

it("默认 debounce 在三百毫秒前不保存、到期后保存", async () => {
  vi.useFakeTimers();
  const { draft, snapshot } = setup();

  draft.queue();
  await vi.advanceTimersByTimeAsync(299);
  expect(readLocalDraft("u-1", "c-1")).toBeNull();
  await vi.advanceTimersByTimeAsync(1);
  draft.destroy();

  expect(readLocalDraft("u-1", "c-1")?.snapshot).toEqual(snapshot);
});

it("同标题不同正文的已保存快照继续持久化", () => {
  const { draft, snapshot } = setup();

  draft.saved({
    title: snapshot.title,
    document: { type: "doc", content: [{ type: "paragraph" }] },
  });

  expect(readLocalDraft("u-1", "c-1")).toEqual({
    userId: "u-1", caseId: "c-1", baseRevision: 4, snapshot,
  });
});
