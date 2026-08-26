import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, expect, test, vi } from "vitest";
import NewCaseView from "./NewCaseView.vue";
import { api } from "../api.js";

const push = vi.fn();
const catalog = {
  stages: [{ id: "grad", name: "硕博公共思政" }, { id: "ug", name: "本科思政" }],
  caseTypes: [{ id: "ct-figure", name: "人物传记类", description: "人物经历" }],
  templates: [
    {
      id: "tpl-general-v1", version: 1, name: "通用案例结构",
      stageIds: ["grad", "ug"], typeIds: ["ct-figure"], sectionTitles: ["（一）建设目标"],
    },
    {
      id: "tpl-grad-v1", version: 1, name: "硕博模板",
      stageIds: ["grad"], typeIds: ["ct-figure"], sectionTitles: ["一、研究说明"],
    },
  ],
};

vi.mock("vue-router", () => ({ useRouter: () => ({ push }) }));
vi.mock("../api.js", () => ({ api: { caseCreationCatalog: vi.fn(), createCase: vi.fn() } }));
vi.mock("../session.js", () => ({ session: { csrfToken: "csrf" } }));

function render() {
  return mount(NewCaseView, { global: { stubs: { SiteHeader: true } } });
}

async function choose(wrapper, stage = "本科思政") {
  await wrapper.get(`[role="radio"][aria-label="${stage}"]`).trigger("click");
  await wrapper.get(".type-options button").trigger("click");
  await wrapper.get(".template-options button").trigger("click");
}

beforeEach(() => {
  vi.clearAllMocks();
  api.caseCreationCatalog.mockResolvedValue(catalog);
  api.createCase.mockResolvedValue({ id: "case-1" });
});

test("级联选择只展示兼容模板，改变上游会清空下游", async () => {
  const wrapper = render();
  await flushPromises();
  await choose(wrapper);
  expect(wrapper.text()).toContain("通用案例结构");
  expect(wrapper.text()).not.toContain("硕博模板");
  await wrapper.get('[role="radio"][aria-label="硕博公共思政"]').trigger("click");
  expect(wrapper.find(".template-options").exists()).toBe(false);
  expect(wrapper.get('[type="submit"]').attributes("disabled")).toBeDefined();
});

test("模板未选中时不创建，选中后只提交三个稳定 ID", async () => {
  const wrapper = render();
  await flushPromises();
  await wrapper.get('[role="radio"][aria-label="本科思政"]').trigger("click");
  await wrapper.get(".type-options button").trigger("click");
  await wrapper.get("form").trigger("submit");
  expect(api.createCase).not.toHaveBeenCalled();
  await wrapper.get(".template-options button").trigger("click");
  await wrapper.get("form").trigger("submit");
  await flushPromises();
  expect(api.createCase).toHaveBeenCalledWith({
    stageId: "ug", typeId: "ct-figure", templateId: "tpl-general-v1",
  }, "csrf");
  expect(push).toHaveBeenCalledWith({ name: "workbench", params: { id: "case-1" } });
});

test("创建失败时保留选择并显示服务端错误", async () => {
  api.createCase.mockRejectedValue(new Error("模板不可用"));
  const wrapper = render();
  await flushPromises();
  await choose(wrapper);
  await wrapper.get("form").trigger("submit");
  await flushPromises();
  expect(wrapper.get('[role="alert"]').text()).toContain("模板不可用");
  expect(wrapper.get(".template-options button").attributes("aria-pressed")).toBe("true");
});
