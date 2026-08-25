import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, expect, test, vi } from "vitest";
import { defineComponent } from "vue";
import { api } from "../api.js";
import { session } from "../session.js";
import { useAIStream } from "./useAIStream.js";

vi.mock("../api.js", () => ({
  api: { aiSettings: vi.fn(), streamAI: vi.fn() },
}));

const Probe = defineComponent({
  setup: useAIStream,
  template: "<span>{{ state }}|{{ text }}|{{ error }}</span>",
});

beforeEach(() => {
  vi.clearAllMocks();
  session.user = { id: "teacher" };
  session.csrfToken = "csrf";
  api.aiSettings.mockResolvedValue({ configured: true });
});

function deferredStreams() {
  const streams = [];
  api.streamAI.mockImplementation((_messages, _csrf, handlers) => new Promise((resolve) => {
    streams.push({ handlers, resolve });
  }));
  return streams;
}

function completeStreams(streams) {
  streams[0].handlers.onToken("过期回答");
  streams[0].handlers.onDone();
  streams[1].handlers.onToken("当前回答");
  streams[1].handlers.onDone();
  streams.forEach((stream) => stream.resolve());
}

function delayedFailure() {
  let reject;
  const promise = new Promise((_resolve, fail) => { reject = fail; });
  return { promise, reject };
}

function delayedSettings() {
  let resolve;
  const promise = new Promise((done) => { resolve = done; });
  return { promise, resolve };
}

test("新请求淘汰旧流的延迟响应", async () => {
  const streams = deferredStreams();
  const wrapper = mount(Probe);
  const first = wrapper.vm.run([{ role: "user", content: "旧结果" }]);
  await flushPromises();
  const second = wrapper.vm.run([{ role: "user", content: "新结果" }]);
  await flushPromises();

  completeStreams(streams);
  await Promise.all([first, second]);

  expect(wrapper.text()).toBe("complete|当前回答|");
});

test("过期配置失败不会覆盖已清除的状态", async () => {
  const settings = delayedFailure();
  api.aiSettings.mockReturnValue(settings.promise);
  const wrapper = mount(Probe);
  const running = wrapper.vm.run([{ role: "user", content: "旧结果" }]);
  await flushPromises();
  wrapper.vm.clear();
  settings.reject(new Error("旧配置失败"));
  await running;

  expect(wrapper.text()).toBe("idle||");
});

test("新请求淘汰旧的未配置结果", async () => {
  const settings = delayedSettings();
  const streams = deferredStreams();
  api.aiSettings.mockImplementationOnce(() => settings.promise).mockResolvedValueOnce({ configured: true });
  const wrapper = mount(Probe);
  const first = wrapper.vm.run([{ role: "user", content: "旧结果" }]);
  await flushPromises();
  const second = wrapper.vm.run([{ role: "user", content: "新结果" }]);
  await flushPromises();
  settings.resolve({ configured: false });
  await flushPromises();

  expect(wrapper.text()).toBe("streaming||");
  streams[0].resolve();
  await Promise.all([first, second]);
});
