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

test("零结果显示不可生成状态且不启动 AI 流", async () => {
  const wrapper = render("如何开展思政课", []);
  await flushPromises();

  expect(wrapper.text()).toContain("当前结果不足以生成摘要。");
  expect(run).not.toHaveBeenCalled();
  expect(clear).toHaveBeenCalledWith("idle");
});

test("仅新结果版本重新判定 AI", async () => {
  const wrapper = render("如何开展思政课");
  await flushPromises();
  await wrapper.setProps({ items: [{ id: "two", kind: "case", title: "资源二" }] });
  await flushPromises();
  expect(run).toHaveBeenCalledTimes(1);
  await wrapper.setProps({ resultVersion: 1 });
  await flushPromises();

  expect(run).toHaveBeenCalledTimes(2);
  expect(run.mock.calls[1][0][0].content).toContain("资源二");
});
