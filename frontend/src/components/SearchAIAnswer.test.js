import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, expect, test, vi } from "vitest";
import { ref } from "vue";
import SearchAIAnswer from "./SearchAIAnswer.vue";

const run = vi.fn();
const clear = vi.fn();

vi.mock("../composables/useAIStream.js", () => ({
  useAIStream: () => ({
    state: ref("idle"), text: ref(""), error: ref(""), run, clear,
  }),
}));

const resources = [{ id: "one", kind: "case", title: "资源一" }];

function render(query, items = resources) {
  return mount(SearchAIAnswer, {
    props: { query, items }, global: { stubs: { RouterLink: true } },
  });
}

beforeEach(() => vi.clearAllMocks());

test("空白查询不启动 AI 流", async () => {
  render("   ");
  await flushPromises();

  expect(run).not.toHaveBeenCalled();
  expect(clear).toHaveBeenCalledWith("idle");
});

test("每个新结果集只重新判定一次", async () => {
  const wrapper = render("如何开展思政课");
  await flushPromises();
  await wrapper.setProps({ items: [{ id: "two", kind: "case", title: "资源二" }] });
  await flushPromises();

  expect(run).toHaveBeenCalledTimes(2);
  expect(run.mock.calls[1][0][0].content).toContain("资源二");
});
