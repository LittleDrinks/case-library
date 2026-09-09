import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { api } from "../api.js";
import AddSourceToCase from "./AddSourceToCase.vue";

vi.mock("../api.js", () => ({
  api: {
    listDrafts: vi.fn(),
    createCase: vi.fn(),
    getCase: vi.fn(),
    addCaseSource: vi.fn(),
  },
}));
vi.mock("../session.js", () => ({
  session: { csrfToken: "csrf", user: { id: "teacher-1" } },
}));

const draftPage = (titles, total = titles.length) => ({
  items: titles.map(([id, title]) => ({
    id, title, updatedAt: "2025-09-09T06:00:00+00:00",
  })),
  total, page: 1, pageSize: 20,
});
const firstPage = draftPage([
  ["draft-1", "进行中的案例"],
  ["draft-2", ""],
]);

function render() {
  return mount(AddSourceToCase, {
    props: { sourceCaseId: "case-9", versionId: "ver-3", sourceTitle: "来源案例" },
    global: { stubs: { Teleport: true, RouterLink: true } },
  });
}

async function openDialog(wrapper) {
  await wrapper.get(".source-collect").trigger("click");
  await flushPromises();
}

function buttonByText(wrapper, text) {
  const button = wrapper.findAll("button").find((item) => item.text().includes(text));
  expect(button, `缺少按钮「${text}」`).toBeTruthy();
  return button;
}

beforeEach(() => {
  vi.clearAllMocks();
  api.listDrafts.mockResolvedValue(firstPage);
  api.getCase.mockResolvedValue({ id: "draft-1", revision: 5 });
  api.addCaseSource.mockResolvedValue({});
  api.createCase.mockResolvedValue({ id: "draft-new", revision: 0 });
});

afterEach(() => vi.useRealTimers());

test("加入已有草稿时固定版本并携带修订号", async () => {
  const wrapper = render();
  await openDialog(wrapper);
  expect(api.listDrafts).toHaveBeenCalledWith("", 1, 20);
  expect(wrapper.text()).toContain("进行中的案例");
  expect(wrapper.get("input[value='draft-1']").element.checked).toBe(true);
  await wrapper.get("button.primary").trigger("submit");
  await flushPromises();
  expect(api.getCase).toHaveBeenCalledWith("draft-1");
  expect(api.addCaseSource).toHaveBeenCalledWith("draft-1", {
    sourceCaseId: "case-9", versionId: "ver-3", revision: 5,
  }, "csrf");
  expect(wrapper.text()).toContain("已将「来源案例」的固定版本加入资料区来源");
});

test("确认按钮固定显示所选目标草稿", async () => {
  const wrapper = render();
  await openDialog(wrapper);
  expect(wrapper.get("button.primary").text()).toContain("确认加入「进行中的案例」");
});

test("标题搜索防抖后按首页重新查询并重置页码", async () => {
  vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
  const wrapper = render();
  await openDialog(wrapper);
  await wrapper.get("input[type='search']").setValue("辩证");
  expect(api.listDrafts).toHaveBeenCalledTimes(1);
  await vi.advanceTimersByTimeAsync(250);
  expect(api.listDrafts).toHaveBeenLastCalledWith("辩证", 1, 20);
});

test("有界分页翻页并处理同名与未命名草稿", async () => {
  api.listDrafts.mockResolvedValue(
    draftPage([["a", "同名案例"], ["b", "同名案例"], ["c", ""]], 45),
  );
  const wrapper = render();
  await openDialog(wrapper);
  expect(wrapper.text()).toContain("共 45 个可编辑草稿");
  expect(wrapper.text()).toContain("更新于");
  const prev = buttonByText(wrapper, "上一页");
  const next = buttonByText(wrapper, "下一页");
  expect(prev.attributes("disabled")).toBeDefined();
  await next.trigger("click");
  await flushPromises();
  expect(api.listDrafts).toHaveBeenLastCalledWith("", 2, 20);
  expect(wrapper.text()).toContain("第 2 / 3 页");
});

test("空列表与无匹配提示", async () => {
  api.listDrafts.mockResolvedValue(draftPage([]));
  const wrapper = render();
  await openDialog(wrapper);
  expect(wrapper.text()).toContain("还没有可编辑的本人草稿");
});

test("选择新建草稿时先创建再加入来源", async () => {
  const wrapper = render();
  await openDialog(wrapper);
  await wrapper.get("input[value='__new__']").setValue();
  await wrapper.get("button.primary").trigger("submit");
  await flushPromises();
  expect(api.createCase).toHaveBeenCalledWith({ title: "未命名案例" }, "csrf");
  expect(api.addCaseSource).toHaveBeenCalledWith("draft-new", {
    sourceCaseId: "case-9", versionId: "ver-3", revision: 0,
  }, "csrf");
});

test("新建草稿允许输入名称并显示在确认按钮", async () => {
  const wrapper = render();
  await openDialog(wrapper);
  await wrapper.get("input[value='__new__']").setValue();
  await wrapper.get("input[aria-label='新草稿名称']").setValue("我的新课");
  expect(wrapper.get("button.primary").text()).toContain("确认加入「我的新课」");
});

test("空列表也可命名新建草稿", async () => {
  api.listDrafts.mockResolvedValue(draftPage([]));
  const wrapper = render();
  await openDialog(wrapper);
  await wrapper.get("input[aria-label='新草稿名称']").setValue("从零新建");
  expect(wrapper.get("button.primary").text()).toContain("确认加入「从零新建」");
  await wrapper.get("button.primary").trigger("submit");
  await flushPromises();
  expect(api.createCase).toHaveBeenCalledWith({ title: "从零新建" }, "csrf");
  expect(api.addCaseSource).toHaveBeenCalledWith("draft-new", {
    sourceCaseId: "case-9", versionId: "ver-3", revision: 0,
  }, "csrf");
});

test("跨页与搜索后仍显示已选目标", async () => {
  api.listDrafts.mockImplementation((_q, page) => Promise.resolve(
    page === 1 ? draftPage([["draft-1", "甲页草稿"]], 25) : draftPage([["draft-9", "乙页草稿"]], 25),
  ));
  const wrapper = render();
  await openDialog(wrapper);
  await buttonByText(wrapper, "下一页").trigger("click");
  await flushPromises();
  expect(wrapper.text()).toContain("乙页草稿");
  expect(wrapper.get("button.primary").text()).toContain("确认加入「甲页草稿」");
});

test("搜索竞态：过期响应不覆盖新结果", async () => {
  let resolveStale;
  api.listDrafts.mockImplementationOnce(
    () => new Promise((resolve) => { resolveStale = resolve; }),
  );
  vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
  const wrapper = render();
  await openDialog(wrapper);
  await wrapper.get("input[type='search']").setValue("旧词");
  await vi.advanceTimersByTimeAsync(250);
  await wrapper.get("input[type='search']").setValue("新词");
  await vi.advanceTimersByTimeAsync(250);
  resolveStale(draftPage([]));
  await flushPromises();
  expect(wrapper.text()).toContain("进行中的案例");
  expect(wrapper.text()).not.toContain("没有匹配标题");
});

test("关闭即取消待执行搜索，重开清空搜索词", async () => {
  vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
  const wrapper = render();
  await openDialog(wrapper);
  await wrapper.get("input[type='search']").setValue("旧词");
  await wrapper.get("button[aria-label='关闭']").trigger("click");
  await vi.advanceTimersByTimeAsync(250);
  const callsAfterClose = api.listDrafts.mock.calls.length;
  await wrapper.get(".source-collect").trigger("click");
  await flushPromises();
  expect(api.listDrafts).toHaveBeenLastCalledWith("", 1, 20);
  await vi.advanceTimersByTimeAsync(250);
  expect(api.listDrafts.mock.calls.length).toBe(callsAfterClose + 1);
});

test("重复加入时展示不重复提示", async () => {
  api.addCaseSource.mockRejectedValue({ status: 409, message: "conflict" });
  const wrapper = render();
  await openDialog(wrapper);
  await wrapper.get("button.primary").trigger("submit");
  await flushPromises();
  expect(wrapper.get("[role='alert']").text()).toContain("不会重复添加");
});

test("单选圆点与标题同排且整行可选、同名键盘分组", async () => {
  const wrapper = render();
  await openDialog(wrapper);
  const radios = wrapper.findAll("input[type='radio']");
  expect(radios.length).toBeGreaterThan(1);
  for (const radio of radios) {
    expect(radio.attributes("name")).toBe("collect-target");
    expect(radio.element.closest("label")).toBeTruthy();
  }
});
