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
  template: "<span>{{ text }}</span>",
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

test("新请求淘汰旧流的延迟响应", async () => {
  const streams = deferredStreams();
  const wrapper = mount(Probe);
  const first = wrapper.vm.run([{ role: "user", content: "旧结果" }]);
  await flushPromises();
  const second = wrapper.vm.run([{ role: "user", content: "新结果" }]);
  await flushPromises();

  completeStreams(streams);
  await Promise.all([first, second]);

  expect(wrapper.text()).toBe("当前回答");
});
