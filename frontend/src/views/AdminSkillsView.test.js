import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, expect, it, vi } from "vitest";
import AdminSkillsView from "./AdminSkillsView.vue";
import { api } from "../api.js";

vi.mock("../api.js", () => ({
  api: {
    listAdminSkills: vi.fn(), uploadSkillPackage: vi.fn(), publishSkillVersion: vi.fn(),
  },
}));
vi.mock("../session.js", () => ({
  session: { csrfToken: "csrf", user: { id: "admin-1", role: "admin" } },
}));

const skillList = [{
  id: "skill-1",
  name: "思政案例生成",
  description: "按模板生成教学案例",
  publishedVersionId: "ver-1",
  versions: [
    { id: "ver-1", version: "v1", packageSha256: "15479fd46995e9c13a05de822e93d35c31c5003eb5d741b3b8a510988063e542", createdAt: "2026-09-01T08:00:00Z" },
    { id: "ver-2", version: "v2", packageSha256: "aa79fd46995e9c13a05de822e93d35c31c5003eb5d741b3b8a510988063e542bb", createdAt: "2026-09-05T08:00:00Z" },
  ],
}];

const uploadResult = {
  skill: { id: "skill-1", name: "思政案例生成", description: "按模板生成教学案例" },
  version: { id: "ver-2", version: "v1", packageSha256: "15479fd46995e9c13a05de822e93d35c31c5003eb5d741b3b8a510988063e542", fileCount: 5, size: 2048 },
};

function mountView() {
  return mount(AdminSkillsView, {
    global: { stubs: { SiteHeader: true, RouterLink: true } },
  });
}

async function uploadPackage(wrapper) {
  const input = wrapper.get('input[aria-label="选择 Skill 包"]');
  const file = new File(["zip-bytes"], "skill.zip", { type: "application/zip" });
  Object.defineProperty(input.element, "files", { value: [file], configurable: true });
  await input.trigger("change");
  await wrapper.get('form[aria-label="上传 Skill 包"]').trigger("submit");
  await flushPromises();
  return file;
}

beforeEach(() => {
  vi.clearAllMocks();
  api.listAdminSkills.mockResolvedValue(structuredClone(skillList));
});

it("lists skills with versions and marks the published one", async () => {
  const wrapper = mountView();
  await flushPromises();

  expect(wrapper.text()).toContain("思政案例生成");
  expect(wrapper.text()).toContain("已发布");
  expect(wrapper.get('[data-testid="skill-version-published"]').text()).toContain("当前发布");
  expect(wrapper.text()).toContain("v2");
});

it("publishes an unpublished version through the publish command", async () => {
  api.publishSkillVersion.mockResolvedValue({});
  const wrapper = mountView();
  await flushPromises();

  await wrapper.get('[data-testid="skill-publish-ver-2"]').trigger("click");
  await flushPromises();

  expect(api.publishSkillVersion).toHaveBeenCalledWith("skill-1", "ver-2", "csrf");
  expect(api.listAdminSkills).toHaveBeenCalledTimes(2);
});

it("shows the empty state when no skill has been uploaded", async () => {
  api.listAdminSkills.mockResolvedValue([]);
  const wrapper = mountView();
  await flushPromises();

  expect(wrapper.text()).toContain("暂无 Skill 包");
});

it("shows the load failure and retries on demand", async () => {
  api.listAdminSkills.mockRejectedValueOnce(new Error("网络错误"));
  const wrapper = mountView();
  await flushPromises();

  expect(wrapper.get('[role="alert"]').text()).toContain("网络错误");
  await wrapper.get('[role="alert"] button').trigger("click");
  await flushPromises();
  expect(wrapper.text()).toContain("思政案例生成");
});

it("uploads a package, shows the recognized metadata and publishes directly", async () => {
  api.uploadSkillPackage.mockResolvedValue(structuredClone(uploadResult));
  api.publishSkillVersion.mockResolvedValue({});
  const wrapper = mountView();
  await flushPromises();

  const file = await uploadPackage(wrapper);
  expect(api.uploadSkillPackage).toHaveBeenCalledWith(file, "csrf");
  expect(wrapper.text()).toContain("识别结果");
  expect(wrapper.text()).toContain("v1");
  expect(wrapper.text()).toContain("15479fd46995");
  expect(wrapper.text()).toContain("2.0 KB");

  await wrapper.get('[data-testid="skill-publish-uploaded"]').trigger("click");
  await flushPromises();
  expect(api.publishSkillVersion).toHaveBeenCalledWith("skill-1", "ver-2", "csrf");
});

it("shows the server detail when the package metadata is invalid", async () => {
  api.uploadSkillPackage.mockRejectedValue(new Error("Skill 元数据无效：缺少 name"));
  const wrapper = mountView();
  await flushPromises();

  await uploadPackage(wrapper);
  expect(wrapper.get('[role="alert"]').text()).toContain("Skill 元数据无效：缺少 name");
});
