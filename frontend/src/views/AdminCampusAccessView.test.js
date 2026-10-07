import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, expect, it, vi } from "vitest";
import AdminCampusAccessView from "./AdminCampusAccessView.vue";
import { api } from "../api.js";

vi.mock("../api.js", () => ({
  api: {
    listCampusAccessApplications: vi.fn(),
    listLegacyCampusGrants: vi.fn(),
    decideCampusAccessApplication: vi.fn(),
    revokeCampusAccessApplication: vi.fn(),
    revokeLegacyCampusGrant: vi.fn(),
  },
  formatApiError: (error, fallback) => error?.message || fallback,
}));
vi.mock("../session.js", () => ({
  session: { csrfToken: "csrf-admin", user: { id: "admin-1", role: "admin" } },
}));

const application = {
  id: "ca-1",
  userId: "user-1",
  username: "synthetic-user",
  applicantName: "合成申请人",
  studentNumber: "SYN-360-001",
  identitySource: "self_reported",
  status: "pending",
  submittedAt: "2026-10-07T09:00:00Z",
  history: [],
};

function mountView() {
  return mount(AdminCampusAccessView, {
    global: { stubs: { SiteHeader: true, RouterLink: true } },
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  api.listCampusAccessApplications.mockResolvedValue({
    items: [structuredClone(application)], total: 1, page: 1, pageSize: 50,
  });
  api.listLegacyCampusGrants.mockResolvedValue({ items: [], total: 0, page: 1, pageSize: 50 });
});

it("requires an operation reason and approves the selected pending application", async () => {
  const wrapper = mountView();
  await flushPromises();

  expect(wrapper.text()).toContain("合成申请人");
  await wrapper.get(".campus-admin-approve").trigger("click");
  await wrapper.get(".campus-admin-action form").trigger("submit");
  await flushPromises();
  expect(wrapper.get('[role="alert"]').text()).toContain("操作理由不能为空");

  api.listCampusAccessApplications.mockResolvedValueOnce({
    items: [structuredClone(application)], total: 1, page: 1, pageSize: 50,
  }).mockResolvedValueOnce({ items: [], total: 0, page: 1, pageSize: 50 });
  await wrapper.get("#campus-admin-reason").setValue("合成身份核验通过");
  await wrapper.get(".campus-admin-action form").trigger("submit");
  await flushPromises();

  expect(api.decideCampusAccessApplication).toHaveBeenCalledWith(
    "ca-1", "approved", "合成身份核验通过", "csrf-admin",
  );
  expect(wrapper.text()).toContain("已批准 synthetic-user");
});

it("shows legacy grants without application identity and requires a reason to revoke", async () => {
  api.listLegacyCampusGrants.mockResolvedValue({
    items: [{ userId: "legacy-user-1", username: "legacy-admin", role: "admin", grantSource: "legacy" }],
    total: 1, page: 1, pageSize: 50,
  });
  const wrapper = mountView();
  await flushPromises();

  expect(wrapper.text()).toContain("旧系统授权");
  await wrapper.get(".campus-admin-legacy .campus-admin-reject").trigger("click");
  expect(wrapper.text()).toContain("无历史申请或自填身份资料");
  await wrapper.get(".campus-admin-action form").trigger("submit");
  await flushPromises();
  expect(wrapper.get('[role="alert"]').text()).toContain("操作理由不能为空");

  api.listLegacyCampusGrants.mockResolvedValue({ items: [], total: 0, page: 1, pageSize: 50 });
  await wrapper.get("#campus-admin-reason").setValue("合成旧系统授权复核撤销");
  await wrapper.get(".campus-admin-action form").trigger("submit");
  await flushPromises();

  expect(api.revokeLegacyCampusGrant).toHaveBeenCalledWith(
    "legacy-user-1", "合成旧系统授权复核撤销", "csrf-admin",
  );
});

it("pages through legacy grants", async () => {
  api.listLegacyCampusGrants
    .mockResolvedValueOnce({
      items: [{ userId: "legacy-user-1", username: "legacy-one", role: "user", grantSource: "legacy" }],
      total: 51, page: 1, pageSize: 50,
    })
    .mockResolvedValueOnce({
      items: [{ userId: "legacy-user-51", username: "legacy-last", role: "user", grantSource: "legacy" }],
      total: 51, page: 2, pageSize: 50,
    });
  const wrapper = mountView();
  await flushPromises();

  await wrapper.get('[aria-label="下一页旧系统授权"]').trigger("click");
  await flushPromises();

  expect(api.listLegacyCampusGrants).toHaveBeenLastCalledWith("", 2, 50);
  expect(wrapper.text()).toContain("legacy-last");
  expect(wrapper.get('[aria-label="上一页旧系统授权"]').attributes("disabled")).toBeUndefined();
  expect(wrapper.get('[aria-label="下一页旧系统授权"]').attributes("disabled")).toBeDefined();
});

it("retries legacy grants with the current numeric page after a load failure", async () => {
  api.listLegacyCampusGrants
    .mockRejectedValueOnce(new Error("合成列表暂不可用"))
    .mockResolvedValueOnce({
      items: [{ userId: "legacy-user-1", username: "legacy-restored", role: "user", grantSource: "legacy" }],
      total: 1, page: 1, pageSize: 50,
    });
  const wrapper = mountView();
  await flushPromises();

  expect(wrapper.text()).toContain("合成列表暂不可用");
  await wrapper.get(".campus-admin-legacy .error-state button").trigger("click");
  await flushPromises();

  expect(api.listLegacyCampusGrants).toHaveBeenLastCalledWith("", 1, 50);
  expect(wrapper.text()).toContain("legacy-restored");
});
