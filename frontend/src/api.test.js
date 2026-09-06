import { afterEach, expect, it, vi } from "vitest";
import { api } from "./api.js";

afterEach(() => vi.unstubAllGlobals());

it("loads the persistent thread through the JSON snapshot seam", async () => {
  const fetch = vi.fn().mockResolvedValue(new Response(
    JSON.stringify({ id: "thread-1", messages: [] }),
    { status: 200, headers: { "Content-Type": "application/json" } },
  ));
  vi.stubGlobal("fetch", fetch);

  await expect(api.agentThread("case/1")).resolves.toEqual({ id: "thread-1", messages: [] });
  expect(fetch.mock.calls[0][0]).toBe("/api/cases/case%2F1/agent/thread");
});

it("does not expose the retired token-stream client helpers", () => {
  expect(api.streamAI).toBeUndefined();
  expect(api.chat).toBeUndefined();
});

it("serializes multi-select search facets as repeated query parameters", async () => {
  const fetch = vi.fn().mockResolvedValue(new Response("{}", {
    status: 200, headers: { "Content-Type": "application/json" },
  }));
  vi.stubGlobal("fetch", fetch);

  await api.search("思政", "case", null, 20, {
    typeName: ["校本实践类", "科技创新与科技报国类"],
    audience: ["ug"], publishedWithin: "30d",
  });

  const params = new URL(fetch.mock.calls[0][0], "http://local").searchParams;
  expect(params.getAll("typeName")).toEqual(["校本实践类", "科技创新与科技报国类"]);
  expect(params.getAll("audience")).toEqual(["ug"]);
  expect(params.get("publishedWithin")).toBe("30d");
});
