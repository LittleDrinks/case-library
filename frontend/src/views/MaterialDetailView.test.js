import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, expect, test, vi } from "vitest";
import MaterialDetailView from "./MaterialDetailView.vue";
import { api } from "../api.js";

const route = {
  params: { id: "material-1" },
  query: { from: "materials", caseId: "case-1", q: "科学家", authority: "original" },
  fullPath: "/materials/material-1?from=materials&caseId=case-1",
};
const { session } = vi.hoisted(() => ({ session: { user: null } }));
vi.mock("vue-router", () => ({ useRoute: () => route }));
vi.mock("../api.js", () => ({ api: { getMaterial: vi.fn() } }));
vi.mock("../session.js", () => ({ session }));

const RouterLinkStub = {
  name: "RouterLink",
  props: { to: { type: [Object, String], required: true } },
  template: "<a :data-route=\"JSON.stringify(to)\"><slot /></a>",
};

const material = {
  id: "material-1", title: "科学家精神", summary: "素材摘要", excerpt: "内容摘录",
  source: "中国政府网", sourceUrl: "https://example.com/material", materialType: "政策文件",
  authority: "original", accessLevel: "campus", contentAvailable: true,
  hasFile: true, downloadAvailable: true, filename: "科学家.txt", size: 42,
  collectedAt: "2026-08-20", publishedAt: "2026-08-21", updatedAt: "2026-08-22",
  tags: ["科学家精神"],
};

beforeEach(() => {
  vi.clearAllMocks();
  session.user = null;
  route.query = { from: "materials", caseId: "case-1", q: "科学家", authority: "original" };
  route.fullPath = "/materials/material-1?from=materials&caseId=case-1";
  api.getMaterial.mockResolvedValue(material);
});

function render() {
  return mount(MaterialDetailView, {
    global: { stubs: { SiteHeader: true, RouterLink: RouterLinkStub, MaterialDownloadAction: true } },
  });
}

test("详情页展示受权限保护的元数据、原始网页和下载入口", async () => {
  const wrapper = render();
  await flushPromises();

  expect(api.getMaterial).toHaveBeenCalledWith("material-1");
  expect(wrapper.get("h1").text()).toBe("科学家精神");
  expect(wrapper.text()).toContain("内容摘录");
  expect(wrapper.text()).toContain("校内访问");
  expect(wrapper.get(".material-source-link").attributes("href"))
    .toBe("https://example.com/material");
});

test("摘录渲染 Markdown 并转义不安全 HTML", async () => {
  api.getMaterial.mockResolvedValue({ ...material, excerpt: "## 小节\n\n- **要点**\n\n<script>alert(1)</script>" });
  const wrapper = render();
  await flushPromises();
  expect(wrapper.get(".markdown-body h2").text()).toBe("小节");
  expect(wrapper.get(".markdown-body li strong").text()).toBe("要点");
  expect(wrapper.find(".markdown-body script").exists()).toBe(false);
});

test("未登录访问受限来源显示登录返回引导且不显示素材数据", async () => {
  route.query = {};
  route.fullPath = "/materials/material-1";
  api.getMaterial.mockRejectedValueOnce(Object.assign(new Error("素材不存在"), { status: 404 }));
  const wrapper = render();
  await flushPromises();

  expect(wrapper.text()).toContain("登录后继续访问");
  expect(wrapper.text()).toContain("返回资源检索");
  expect(wrapper.text()).not.toContain(material.summary);
  expect(wrapper.text()).not.toContain(material.excerpt);
  const loginLink = wrapper.findAllComponents(RouterLinkStub)
    .find((link) => link.text().includes("登录"));
  expect(loginLink.props("to")).toEqual({
    name: "login", query: { redirect: route.fullPath },
  });
});

test("已登录但无权访问时只显示不可访问引导", async () => {
  route.query = {};
  route.fullPath = "/materials/material-1";
  session.user = { id: "teacher-2" };
  api.getMaterial.mockRejectedValueOnce(Object.assign(new Error("素材不存在"), { status: 404 }));
  const wrapper = render();
  await flushPromises();

  expect(wrapper.text()).toContain("当前账号无权查看");
  expect(wrapper.text()).toContain("返回资源检索");
  expect(wrapper.text()).not.toContain("登录后继续访问");
  expect(wrapper.text()).not.toContain(material.summary);
  expect(wrapper.text()).not.toContain(material.excerpt);
});
