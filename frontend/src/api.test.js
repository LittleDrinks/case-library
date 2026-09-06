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

it("serializes catalog tag conditions as repeated tagIds with tagMode", async () => {
  const fetch = vi.fn().mockResolvedValue(new Response("{}", {
    status: 200, headers: { "Content-Type": "application/json" },
  }));
  vi.stubGlobal("fetch", fetch);

  await api.search("", "case", null, 20, { tagIds: ["tag-1", "tag-2"], tagMode: "any" });

  const params = new URL(fetch.mock.calls[0][0], "http://local").searchParams;
  expect(params.getAll("tagIds")).toEqual(["tag-1", "tag-2"]);
  expect(params.get("tagMode")).toBe("any");
});

function stubJsonFetch(payload = {}) {
  const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify(payload), {
    status: 200, headers: { "Content-Type": "application/json" },
  }));
  vi.stubGlobal("fetch", fetch);
  return fetch;
}

it("lists case sources with the pinned version query", async () => {
  const fetch = stubJsonFetch([]);
  await api.listCaseSources("case/1", "ver-2");
  expect(fetch.mock.calls[0][0]).toBe("/api/cases/case%2F1/case-sources?versionId=ver-2");
});

it("posts a case source with case, version and revision", async () => {
  const fetch = stubJsonFetch();
  await api.addCaseSource("case-1", {
    sourceCaseId: "case-9", versionId: "ver-3", revision: 4,
  }, "csrf-1");
  expect(fetch.mock.calls[0][0]).toBe("/api/cases/case-1/case-sources");
  const options = fetch.mock.calls[0][1];
  expect(options.method).toBe("POST");
  expect(options.headers["X-CSRF-Token"]).toBe("csrf-1");
  expect(JSON.parse(options.body)).toEqual({
    sourceCaseId: "case-9", versionId: "ver-3", revision: 4,
  });
});

it("deletes a case source with the revision guard", async () => {
  const fetch = stubJsonFetch();
  await api.removeCaseSource("case-1", "src/2", 7, "csrf-1");
  expect(fetch.mock.calls[0][0]).toBe("/api/cases/case-1/case-sources/src%2F2?revision=7");
  expect(fetch.mock.calls[0][1].method).toBe("DELETE");
  expect(fetch.mock.calls[0][1].headers["X-CSRF-Token"]).toBe("csrf-1");
});

it("reads the public case pinned to a published version", async () => {
  const fetch = stubJsonFetch();
  await api.getPublicCase("case-1", "ver-5");
  expect(fetch.mock.calls[0][0]).toBe("/api/cases/case-1/public?versionId=ver-5");
});
