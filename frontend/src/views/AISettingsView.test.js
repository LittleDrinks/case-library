import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, expect, it, vi } from "vitest";
import AdminAISettingsView from "./AdminAISettingsView.vue";
import AISettingsView from "./AISettingsView.vue";
import { api } from "../api.js";
import { session } from "../session.js";

vi.mock("../api.js", () => ({
  api: {
    aiSettings: vi.fn(), saveAISettings: vi.fn(), discoverAIModels: vi.fn(),
    adminAISettings: vi.fn(), saveAdminAISettings: vi.fn(),
  },
}));

const stubs = { SiteHeader: true, RouterLink: true };
const automatic = {
  mode: "automatic", baseUrl: null, model: null, hasApiKey: false,
  configured: false, effectiveSource: null, effectiveModel: null,
};

beforeEach(() => {
  vi.clearAllMocks();
  session.user = { id: "u-user-demo", role: "user" };
  session.csrfToken = "csrf";
});

function prepareUserMocks() {
  api.aiSettings.mockResolvedValue(automatic);
  api.discoverAIModels.mockResolvedValue({ models: ["model-a", "model-b"] });
  api.saveAISettings.mockResolvedValue({
    mode: "custom", baseUrl: "https://models.example/v1", model: "model-b",
    hasApiKey: true, configured: true, effectiveSource: "custom", effectiveModel: "model-b",
  });
}

async function saveCustomSettings() {
  const wrapper = mount(AISettingsView, { global: { stubs } });
  await flushPromises();
  await wrapper.get('[aria-label="自定义模型服务"]').setValue(true);
  await wrapper.get('input[type="url"]').setValue("https://models.example/v1");
  await wrapper.get('input[type="password"]').setValue("personal-secret");
  await wrapper.get(".secondary-button").trigger("click");
  await flushPromises();
  await wrapper.get("select").setValue("model-b");
  await wrapper.get("form").trigger("submit");
  await flushPromises();
  return wrapper;
}

function expectCustomSettings(wrapper) {
  expect(api.discoverAIModels).toHaveBeenCalledWith(
    { baseUrl: "https://models.example/v1", apiKey: "personal-secret" }, "csrf",
  );
  expect(api.saveAISettings).toHaveBeenCalledWith({
    mode: "custom", baseUrl: "https://models.example/v1",
    apiKey: "personal-secret", model: "model-b",
  }, "csrf");
  expect(wrapper.get('input[type="password"]').element.value).toBe("");
  expect(wrapper.text()).not.toContain("personal-secret");
}

it("教师获取模型后保存自定义设置且密钥立即清空", async () => {
  prepareUserMocks();
  expectCustomSettings(await saveCustomSettings());
});

function existingCustom() {
  return {
    mode: "custom", baseUrl: "https://models.example/v1", model: "model-a",
    hasApiKey: true, configured: true, effectiveSource: "custom", effectiveModel: "model-a",
  };
}

async function mountExistingCustom() {
  api.aiSettings.mockResolvedValue(existingCustom());
  api.saveAISettings.mockResolvedValue(existingCustom());
  const wrapper = mount(AISettingsView, { global: { stubs } });
  await flushPromises();
  return wrapper;
}

it("Base URL 变化时要求新密钥并阻止旧密钥跨主机复用", async () => {
  const wrapper = await mountExistingCustom();
  await wrapper.get('input[type="url"]').setValue("https://other.example/v1/");

  expect(wrapper.get('input[type="password"]').attributes("required")).toBeDefined();
  await wrapper.get("form").trigger("submit");

  expect(api.saveAISettings).not.toHaveBeenCalled();
  expect(wrapper.get('[role="alert"]').text()).toContain("必须填写新的 API Key");
});

it("同一规范化 Base URL 可留空复用密钥", async () => {
  const wrapper = await mountExistingCustom();
  await wrapper.get('input[type="url"]').setValue(" https://models.example/v1/ ");
  await wrapper.get("form").trigger("submit");
  await flushPromises();

  expect(api.saveAISettings).toHaveBeenCalledWith({
    mode: "custom", baseUrl: "https://models.example/v1",
    apiKey: "", model: "model-a",
  }, "csrf");
});

it("新 Base URL 与新密钥可一起保存", async () => {
  const wrapper = await mountExistingCustom();
  await wrapper.get('input[type="url"]').setValue(" https://other.example/v1/ ");
  await wrapper.get('input[type="password"]').setValue("replacement-key");
  await wrapper.get("form").trigger("submit");
  await flushPromises();

  expect(api.saveAISettings).toHaveBeenCalledWith({
    mode: "custom", baseUrl: "https://other.example/v1",
    apiKey: "replacement-key", model: "model-a",
  }, "csrf");
});

function prepareAdminMocks() {
  session.user = { id: "u-admin-demo", role: "admin" };
  api.adminAISettings.mockResolvedValue({
    fallbackModel: null, availableModels: ["model-a", "model-b"], configured: false,
  });
  api.saveAdminAISettings.mockResolvedValue({
    fallbackModel: "model-b", availableModels: ["model-a", "model-b"], configured: false,
  });
}

async function saveFallback() {
  const wrapper = mount(AdminAISettingsView, { global: { stubs } });
  await flushPromises();
  expect(wrapper.get("select").findAll("option").map((option) => option.element.value))
    .toEqual(["", "model-a", "model-b"]);
  await wrapper.get("select").setValue("model-b");
  await wrapper.get("form").trigger("submit");
  await flushPromises();
  return wrapper;
}

it("管理员只能从服务器给出的列表保存兜底模型", async () => {
  prepareAdminMocks();
  const wrapper = await saveFallback();
  expect(api.saveAdminAISettings).toHaveBeenCalledWith({ fallbackModel: "model-b" }, "csrf");
  expect(wrapper.find('input[name="fallbackModel"]').exists()).toBe(false);
});
