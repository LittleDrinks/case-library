import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, expect, it, vi } from "vitest";
import CampusAccessView from "./CampusAccessView.vue";
import { api } from "../api.js";

vi.mock("../api.js", () => ({
  api: {
    campusAccessStatus: vi.fn(),
    submitCampusAccessApplication: vi.fn(),
  },
  formatApiError: (error, fallback) => error?.message || fallback,
}));
vi.mock("../session.js", () => ({
  session: { csrfToken: "csrf-user", user: { id: "user-1", role: "user" } },
}));

const application = {
  id: "ca-1",
  applicantName: "合成申请人",
  studentNumber: "SYN-360-001",
  identitySource: "self_reported",
  status: "pending",
  submittedAt: "2026-10-07T09:00:00Z",
  history: [],
};

function mountView() {
  return mount(CampusAccessView, {
    global: { stubs: { SiteHeader: true, RouterLink: true } },
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  api.campusAccessStatus.mockResolvedValue({
    campusVerified: false,
    grantSource: null,
    currentStatus: "not_applied",
    applications: [],
  });
});

it("submits self-reported identity and shows the persisted pending status", async () => {
  api.submitCampusAccessApplication.mockResolvedValue(application);
  api.campusAccessStatus
    .mockResolvedValueOnce({ campusVerified: false, grantSource: null, currentStatus: "not_applied", applications: [] })
    .mockResolvedValueOnce({ campusVerified: false, grantSource: null, currentStatus: "pending", applications: [application] });
  const wrapper = mountView();
  await flushPromises();

  await wrapper.get('input[name="applicantName"]').setValue("合成申请人");
  await wrapper.get('input[name="studentNumber"]').setValue("SYN-360-001");
  await wrapper.get("form").trigger("submit");
  await flushPromises();

  expect(api.submitCampusAccessApplication).toHaveBeenCalledWith(
    { applicantName: "合成申请人", studentNumber: "SYN-360-001" },
    "csrf-user",
  );
  expect(wrapper.text()).toContain("等待管理员审核");
  expect(wrapper.text()).toContain("合成申请人");
  expect(wrapper.find("form").exists()).toBe(false);
});

it("identifies a revoked legacy grant without inventing an application", async () => {
  api.campusAccessStatus.mockResolvedValue({
    campusVerified: false,
    grantSource: "legacy",
    currentStatus: "revoked",
    applications: [],
  });
  const wrapper = mountView();
  await flushPromises();

  expect(wrapper.text()).toContain("已撤销");
  expect(wrapper.text()).toContain("上次授权来源：旧系统");
  expect(wrapper.text()).toContain("暂无申请记录");
});
