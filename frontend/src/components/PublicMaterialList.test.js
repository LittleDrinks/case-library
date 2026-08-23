import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, expect, test, vi } from "vitest";
import { api } from "../api.js";
import PublicMaterialList from "./PublicMaterialList.vue";

vi.mock("../api.js", () => ({
  api: {
    listCaseMaterials: vi.fn(),
    materialContentUrl: (id) => `/api/materials/${id}/content`,
  },
}));

beforeEach(() => {
  api.listCaseMaterials.mockResolvedValue([
    {
      id: "file-1", title: "教学资料", filename: "教学资料.docx",
      contentAvailable: true, hasFile: true,
    },
    {
      id: "web-1", title: "网页资料", contentAvailable: true,
      sourceUrl: "https://example.com/article",
    },
    {
      id: "private-1", title: "受限资料", contentAvailable: false,
      hasFile: true, sourceUrl: "https://example.com/private",
    },
  ]);
});

test("公开案例素材保留文件下载、外部来源和权限提示", async () => {
  const wrapper = mount(PublicMaterialList, {
    props: { caseId: "case-1", versionId: "version-1" },
  });
  await flushPromises();

  expect(wrapper.get("[aria-label='下载教学资料']").attributes("href"))
    .toBe("/api/materials/file-1/content");
  expect(wrapper.get("[aria-label='查看网页资料来源']").attributes("href"))
    .toBe("https://example.com/article");
  expect(wrapper.get("[aria-label='受限资料内容受限']").attributes("disabled"))
    .toBeDefined();
  expect(wrapper.text()).toContain("内容按权限开放");
  expect(wrapper.find("[aria-label='查看受限资料来源']").exists()).toBe(false);
});
