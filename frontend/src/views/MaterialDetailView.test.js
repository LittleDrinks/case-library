import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, expect, test, vi } from "vitest";
import MaterialDetailView from "./MaterialDetailView.vue";
import { api } from "../api.js";

const route = {
  params: { id: "material-1" },
  query: { from: "materials", caseId: "case-1", q: "科学家", authority: "original" },
};
vi.mock("vue-router", () => ({ useRoute: () => route }));
vi.mock("../api.js", () => ({ api: { getMaterial: vi.fn() } }));

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
  api.getMaterial.mockResolvedValue(material);
});

test("详情页展示受权限保护的元数据、原始网页和下载入口", async () => {
  const wrapper = mount(MaterialDetailView, {
    global: { stubs: { SiteHeader: true, RouterLink: true, MaterialDownloadAction: true } },
  });
  await flushPromises();

  expect(api.getMaterial).toHaveBeenCalledWith("material-1");
  expect(wrapper.get("h1").text()).toBe("科学家精神");
  expect(wrapper.text()).toContain("内容摘录");
  expect(wrapper.text()).toContain("校内访问");
  expect(wrapper.get(".material-source-link").attributes("href"))
    .toBe("https://example.com/material");
});
