import { flushPromises, mount } from "@vue/test-utils";
import { reactive } from "vue";
import { beforeEach, expect, it, vi } from "vitest";
import MyCasesView from "./MyCasesView.vue";
import { api } from "../api.js";
import { caseUnavailableNotice } from "../lib/workbenchAccess.js";

vi.mock("../api.js", () => ({ api: { createCase: vi.fn(), listCases: vi.fn() } }));
const route = reactive({ query: {} });
vi.mock("vue-router", () => ({
  useRoute: () => route, useRouter: () => ({ push: vi.fn() }),
}));

const cases = [
  { id: "draft", workflowStatus: "draft" }, { id: "pending", workflowStatus: "pending" },
  { id: "reviewing", workflowStatus: "reviewing" },
  { id: "hidden", workflowStatus: "published", publicationStatus: "hidden" },
];
const stubs = {
  SiteHeader: true,
  CaseCard: { props: ["destination"], template: "<div class=\"case-card\" :data-destination=\"destination.name\" />" },
};

beforeEach(() => {
  vi.clearAllMocks();
  route.query = {};
  api.listCases.mockResolvedValue(cases);
});

it("我的案例为每种作者状态提供工作台入口", async () => {
  const wrapper = mount(MyCasesView, { global: { stubs } });
  await flushPromises();

  expect(wrapper.findAll(".case-card")).toHaveLength(cases.length);
  expect(wrapper.findAll(".case-card").every((card) => card.attributes("data-destination") === "workbench")).toBe(true);
});

it("已挂载页面立即显示通用访问提示且新访问不保留", async () => {
  const wrapper = mount(MyCasesView, { global: { stubs } });
  await flushPromises();
  route.query = { notice: caseUnavailableNotice };
  await wrapper.vm.$nextTick();

  expect(wrapper.get("[role=alert]").text()).toBe("案例不可访问");
  route.query = {};
  await wrapper.vm.$nextTick();
  expect(wrapper.find(".catalog-notice").exists()).toBe(false);
});
