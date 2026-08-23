import { afterEach, expect, it, vi } from "vitest";
import { api } from "./api.js";

afterEach(() => vi.unstubAllGlobals());

function streamResponse(chunks) {
  const encoder = new TextEncoder();
  return new Response(new ReadableStream({
    start(controller) {
      chunks.forEach((chunk) => controller.enqueue(encoder.encode(chunk)));
      controller.close();
    },
  }), { status: 200, headers: { "Content-Type": "text/event-stream" } });
}

it("工作台按标准事件流逐段接收 AI 回答", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(streamResponse([
    'event: token\ndata: {"text":"第一',
    '段"}\n\nevent: token\ndata: {"text":"第二段"}\n\n',
    "event: done\ndata: {}\n\n",
  ])));
  const events = [];

  await api.chat([{ role: "user", content: "问题" }], "csrf", (event) => events.push(event));

  expect(events).toEqual([
    { type: "token", text: "第一段" },
    { type: "token", text: "第二段" },
    { type: "done" },
  ]);
});

it("工作台聊天拒绝未配置的 AI 服务", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(
    '{"detail":"AI 服务未配置"}',
    { status: 503, headers: { "Content-Type": "application/json" } },
  )));

  await expect(api.chat([], "csrf", vi.fn())).rejects.toThrow("AI 服务未配置");
});

it("AI 事件流在完成事件前断开时拒绝静默成功", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(streamResponse([
    'event: token\ndata: {"text":"未完成"}\n\n',
  ])));

  await expect(api.chat([], "csrf", vi.fn())).rejects.toThrow("AI 响应意外中断");
});

it("检索将多选分面序列化为重复查询参数", async () => {
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
