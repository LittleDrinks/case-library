import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, expect, test, vi } from "vitest";
import SearchAIAnswer from "./SearchAIAnswer.vue";
import { api } from "../api.js";
import { session } from "../session.js";

vi.mock("../api.js", () => ({ api: { aiSettings: vi.fn() } }));

const RouterLinkStub = {
  props: ["to"],
  template: '<a :data-to="JSON.stringify(to)"><slot /></a>',
};
const items = [
  { id: "c-05", kind: "case", title: "重复标题" },
  { id: "mat-1", kind: "material", title: "素材一", sourceUrl: "https://example.com/doc" },
  { id: "kn-1", kind: "knowledge", title: "知识一" },
  { id: "m-kcsz", kind: "material", title: "重复标题" },
];
const nextItems = [{ id: "case-2", kind: "case", title: "案例二" }];

function snapshotOf(overrides = {}) {
  return { revision: 1, query: "课程思政", items, ...overrides };
}

function sseHeaders() {
  return { "Content-Type": "text/event-stream", "x-vercel-ai-ui-message-stream": "v1" };
}

function answerFrames(text) {
  return [
    'data: {"type":"start","messageId":"m-1"}\n\n',
    'data: {"type":"start-step"}\n\n',
    'data: {"type":"text-start","id":"t-1"}\n\n',
    `data: {"type":"text-delta","id":"t-1","delta":${JSON.stringify(text)}}\n\n`,
    'data: {"type":"text-end","id":"t-1"}\n\n',
    'data: {"type":"finish-step"}\n\n',
    'data: {"type":"finish","finishReason":"stop"}\n\n',
    "data: [DONE]\n\n",
  ];
}

function answerResponse(text) {
  const encoder = new TextEncoder();
  return new Response(new ReadableStream({
    start(controller) {
      answerFrames(text).forEach((frame) => controller.enqueue(encoder.encode(frame)));
      controller.close();
    },
  }), { status: 200, headers: sseHeaders() });
}

function pendingStream() {
  const encoder = new TextEncoder();
  let controller;
  const stream = new ReadableStream({ start(opened) { controller = opened; } });
  const push = (frame) => controller.enqueue(encoder.encode(frame));
  answerFrames("").slice(0, 3).forEach(push);
  return {
    response: new Response(stream, { status: 200, headers: sseHeaders() }),
    pushDelta: (text) => {
      try { push(`data: {"type":"text-delta","id":"t-1","delta":${JSON.stringify(text)}}\n\n`); }
      catch { /* 已被取代的旧流会被取消。 */ }
    },
    close: () => { try { controller.close(); } catch { /* 已取消。 */ } },
  };
}

function held() {
  let resolve;
  let reject;
  const promise = new Promise((done, fail) => { resolve = done; reject = fail; });
  return { promise, resolve, reject };
}

function mountAnswer(props = {}) {
  return mount(SearchAIAnswer, {
    props: { snapshot: snapshotOf(), ...props },
    global: { stubs: { RouterLink: RouterLinkStub } },
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.unstubAllGlobals();
  session.user = { id: "u-1", name: "老师" };
  session.csrfToken = "csrf";
  api.aiSettings.mockResolvedValue({ configured: true });
});

test("空查询不检查模型配置也不请求摘要", async () => {
  const fetch = vi.fn();
  vi.stubGlobal("fetch", fetch);
  mountAnswer({ snapshot: snapshotOf({ query: "" }) });
  await flushPromises();
  expect(api.aiSettings).not.toHaveBeenCalled();
  expect(fetch).not.toHaveBeenCalled();
});

test("无可见结果时不发起任何 AI 请求", async () => {
  const fetch = vi.fn();
  vi.stubGlobal("fetch", fetch);
  mountAnswer({ snapshot: snapshotOf({ items: [] }) });
  await flushPromises();
  expect(api.aiSettings).not.toHaveBeenCalled();
  expect(fetch).not.toHaveBeenCalled();
});

test("短关键词自动流式生成且默认部分预览可展开收起", async () => {
  const fetch = vi.fn().mockResolvedValue(answerResponse("摘要正文"));
  vi.stubGlobal("fetch", fetch);
  const wrapper = mountAnswer({ snapshot: snapshotOf({ query: "思政" }) });
  await flushPromises();
  expect(fetch).toHaveBeenCalledTimes(1);
  expect(fetch.mock.calls[0][0]).toBe("/api/search/summary");
  expect(wrapper.text()).toContain("摘要正文");
  expect(wrapper.text()).not.toContain("省流");
  const toggle = wrapper.get(".ai-answer-toggle");
  expect(toggle.attributes("aria-expanded")).toBe("false");
  expect(wrapper.get(".ai-answer-text").classes()).toContain("collapsed");
  await toggle.trigger("click");
  expect(wrapper.get(".ai-answer-text").classes()).not.toContain("collapsed");
  await wrapper.get(".ai-answer-toggle").trigger("click");
  expect(wrapper.get(".ai-answer-text").classes()).toContain("collapsed");
});

test("新修订到达后旧流式回答不得覆盖新回答", async () => {
  const stale = pendingStream();
  const fetch = vi.fn()
    .mockResolvedValueOnce(stale.response)
    .mockResolvedValueOnce(answerResponse("新回答"));
  vi.stubGlobal("fetch", fetch);
  const wrapper = mountAnswer();
  await flushPromises();
  await wrapper.setProps({ snapshot: snapshotOf({ revision: 2, items: nextItems }) });
  await flushPromises();
  stale.pushDelta("旧回答");
  stale.close();
  await flushPromises();
  expect(fetch).toHaveBeenCalledTimes(2);
  const body = JSON.parse(fetch.mock.calls[1][1].body);
  expect(body.items.map((item) => item.id)).toEqual(["case-2"]);
  expect(wrapper.text()).toContain("新回答");
  expect(wrapper.text()).not.toContain("旧回答");
});

test("新修订开始时旧答案与来源被原子清除", async () => {
  const pending = held();
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(answerResponse("依据〔2〕。")));
  const wrapper = mountAnswer();
  await flushPromises();
  expect(wrapper.get(".ai-answer-sources").text()).toContain("素材一");
  api.aiSettings.mockReturnValueOnce(pending.promise);
  await wrapper.setProps({ snapshot: snapshotOf({ revision: 2 }) });
  expect(wrapper.text()).not.toContain("依据");
  expect(wrapper.find(".ai-answer-sources").exists()).toBe(false);
  pending.resolve({ configured: true });
});

test("被压住的旧设置请求返回不得清除较新答案与来源", async () => {
  const stale = held();
  api.aiSettings.mockReset();
  api.aiSettings.mockReturnValueOnce(stale.promise).mockResolvedValue({ configured: true });
  const fetch = vi.fn().mockResolvedValue(answerResponse("新回答见〔kn-1〕。"));
  vi.stubGlobal("fetch", fetch);
  const wrapper = mountAnswer();
  await flushPromises();
  await wrapper.setProps({ snapshot: snapshotOf({ revision: 2, items: nextItems }) });
  await flushPromises();
  stale.reject(new Error("过时失败"));
  await flushPromises();
  expect(wrapper.text()).toContain("新回答");
  expect(wrapper.text()).not.toContain("AI 服务暂不可用");
  expect(fetch).toHaveBeenCalledTimes(1);
});

test("卸载后挂起的设置请求与流不得恢复旧内容", async () => {
  const pending = held();
  api.aiSettings.mockReset();
  api.aiSettings.mockReturnValue(pending.promise);
  const fetch = vi.fn();
  vi.stubGlobal("fetch", fetch);
  const wrapper = mountAnswer();
  await flushPromises();
  wrapper.unmount();
  pending.resolve({ configured: true });
  await flushPromises();
  expect(fetch).not.toHaveBeenCalled();
});

test("相同查询再次提交得到新修订仍重新生成", async () => {
  const fetch = vi.fn().mockResolvedValue(answerResponse("回答"));
  vi.stubGlobal("fetch", fetch);
  const wrapper = mountAnswer();
  await flushPromises();
  await wrapper.setProps({ snapshot: snapshotOf({ revision: 2 }) });
  await flushPromises();
  expect(fetch).toHaveBeenCalledTimes(2);
  expect(JSON.parse(fetch.mock.calls[1][1].body).query).toBe("课程思政");
});

test("同 ID 摘录变化的新快照触发重新生成", async () => {
  const fetch = vi.fn().mockResolvedValue(answerResponse("回答"));
  vi.stubGlobal("fetch", fetch);
  const wrapper = mountAnswer();
  await flushPromises();
  const revised = items.map((item) => ({ ...item, summary: "更新后的摘要" }));
  await wrapper.setProps({ snapshot: snapshotOf({ revision: 2, items: revised }) });
  await flushPromises();
  expect(fetch).toHaveBeenCalledTimes(2);
  const body = JSON.parse(fetch.mock.calls[1][1].body);
  expect(body.items[0].summary).toBe("更新后的摘要");
});

test("四种标记形式解析并统一呈现顺序编号，未知标记保持纯文本", async () => {
  const answer = "见〔1〕、[m-kcsz]、〔kn-1〕与〔c-05〕，另见〔mat-9〕与[8]。";
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(answerResponse(answer)));
  const wrapper = mountAnswer();
  await flushPromises();
  const markers = wrapper.get(".ai-answer-text").findAll(".ai-marker");
  expect(markers.map((marker) => marker.text())).toEqual(["〔1〕", "〔4〕", "〔3〕", "〔1〕"]);
  expect(wrapper.text()).toContain("〔mat-9〕");
  expect(wrapper.text()).toContain("[8]");
});

test("回答按 Markdown 渲染标题、列表与可滚动表格，引用仍可定位", async () => {
  const answer = "## 结论〔1〕\n\n- **要点**加粗\n\n| 指标〔1〕 | 数值 |\n| --- | --- |\n| 甲 | 12 |";
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(answerResponse(answer)));
  const wrapper = mountAnswer();
  await flushPromises();
  const body = wrapper.get(".ai-answer-text");
  expect(body.get("h2").text()).toContain("结论");
  expect(body.get("li").text()).toContain("要点");
  expect(body.get("li").get("strong").text()).toBe("要点");
  expect(body.get(".md-table-scroll table").exists()).toBe(true);
  expect(body.findAll(".ai-marker").map((marker) => marker.text())).toEqual(["〔1〕", "〔1〕"]);
  await body.get(".ai-marker").trigger("click");
  expect(wrapper.emitted("locate")[0]).toEqual([{ kind: "case", id: "c-05" }]);
  expect(wrapper.get(".ai-answer-sources").text()).toContain("重复标题");
});

test("流式过程中未完成的 Markdown 不破坏页面且与完成态一致", async () => {
  const pending = pendingStream();
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(pending.response));
  const wrapper = mountAnswer();
  await flushPromises();
  pending.pushDelta("## 未完成\n\n**加粗");
  await flushPromises();
  expect(wrapper.get(".ai-answer-text h2").text()).toBe("未完成");
  expect(wrapper.get(".stream-caret").exists()).toBe(true);
  pending.pushDelta("，表格如下\n\n| 列A | 列B |\n| --- | --- |\n| 甲 | 乙 |");
  await flushPromises();
  expect(wrapper.get(".ai-answer-text .md-table-scroll table").exists()).toBe(true);
  pending.close();
  await flushPromises();
  expect(wrapper.get(".ai-answer-text .md-table-scroll table").exists()).toBe(true);
});

test("已解析引用与来源行按稳定 kind+id 定位精确结果卡片", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(answerResponse("依据[2]与〔kn-1〕。")));
  const wrapper = mountAnswer();
  await flushPromises();
  const markers = wrapper.get(".ai-answer-text").findAll(".ai-marker");
  await markers[0].trigger("click");
  expect(wrapper.emitted("locate")[0]).toEqual([{ kind: "material", id: "mat-1" }]);
  await markers[1].trigger("click");
  expect(wrapper.emitted("locate")[1]).toEqual([{ kind: "knowledge", id: "kn-1" }]);
  const sources = wrapper.get(".ai-answer-sources").findAll("button");
  expect(sources.map((source) => source.text())).toEqual(["〔2〕 素材一", "〔3〕 知识一"]);
  await sources[1].trigger("click");
  expect(wrapper.emitted("locate")[2]).toEqual([{ kind: "knowledge", id: "kn-1" }]);
});

test("重名结果按 ID 区分定位而非标题", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(answerResponse("对比〔c-05〕和[m-kcsz]。")));
  const wrapper = mountAnswer();
  await flushPromises();
  const markers = wrapper.get(".ai-answer-text").findAll(".ai-marker");
  await markers[0].trigger("click");
  await markers[1].trigger("click");
  expect(wrapper.emitted("locate")).toEqual([
    [{ kind: "case", id: "c-05" }],
    [{ kind: "material", id: "m-kcsz" }],
  ]);
});

test("摘要请求最多携带当前结果前 15 条", async () => {
  const many = Array.from({ length: 20 }, (_, index) => (
    { id: `m-${index}`, kind: "material", title: `素材${index}` }
  ));
  const fetch = vi.fn().mockResolvedValue(answerResponse("回答"));
  vi.stubGlobal("fetch", fetch);
  mountAnswer({ snapshot: snapshotOf({ items: many }) });
  await flushPromises();
  const body = JSON.parse(fetch.mock.calls[0][1].body);
  expect(body.items).toHaveLength(15);
  expect(body.items[14].id).toBe("m-14");
});

test("未登录时保留登录约束且不发起请求", async () => {
  session.user = null;
  const fetch = vi.fn();
  vi.stubGlobal("fetch", fetch);
  const wrapper = mountAnswer();
  await flushPromises();
  expect(wrapper.text()).toContain("登录后可基于当前检索结果生成摘要");
  expect(api.aiSettings).not.toHaveBeenCalled();
  expect(fetch).not.toHaveBeenCalled();
});

test("模型未配置时提示配置且不请求摘要", async () => {
  api.aiSettings.mockResolvedValue({ configured: false });
  const fetch = vi.fn();
  vi.stubGlobal("fetch", fetch);
  const wrapper = mountAnswer();
  await flushPromises();
  expect(wrapper.text()).toContain("当前账号尚未配置可用模型");
  expect(fetch).not.toHaveBeenCalled();
});

test("模型失败展示错误并可重试恢复", async () => {
  const fetch = vi.fn()
    .mockRejectedValueOnce(new Error("网络错误"))
    .mockResolvedValueOnce(answerResponse("重试后的回答"));
  vi.stubGlobal("fetch", fetch);
  const wrapper = mountAnswer();
  await flushPromises();
  expect(wrapper.text()).toContain("AI 服务暂不可用");
  expect(wrapper.find(".ai-answer-sources").exists()).toBe(false);
  await wrapper.get("[aria-label='重新生成 AI 回答']").trigger("click");
  await flushPromises();
  expect(wrapper.text()).toContain("重试后的回答");
  expect(fetch).toHaveBeenCalledTimes(2);
});
