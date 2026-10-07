import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, expect, it, vi } from "vitest";
import AdminAccountsView from "./AdminAccountsView.vue";

const { apiMocks, refreshSession, routerReplace } = vi.hoisted(() => ({
  apiMocks: {
    listManagedAccounts: vi.fn(),
    listAccountOperations: vi.fn(),
    openManagedAccount: vi.fn(),
    resetManagedAccountPassword: vi.fn(),
    forceLogoutManagedAccount: vi.fn(),
    setManagedAccountStatus: vi.fn(),
    setManagedAccountRole: vi.fn(),
  },
  refreshSession: vi.fn(),
  routerReplace: vi.fn(),
}));

vi.mock("../api.js", () => ({
  api: apiMocks,
  formatApiError: (error, fallback) => error?.message || fallback,
}));
vi.mock("../session.js", () => ({
  refreshSession,
  session: { csrfToken: "csrf", user: { id: "admin-1", role: "admin" } },
}));
vi.mock("vue-router", () => ({
  useRouter: () => ({ replace: routerReplace }),
}));

function mountView() {
  return mount(AdminAccountsView, {
    global: { stubs: { SiteHeader: true, RouterLink: true } },
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  apiMocks.listManagedAccounts.mockResolvedValue({
    items: [], total: 0, page: 1, pageSize: 25,
  });
  apiMocks.listAccountOperations.mockResolvedValue({
    items: [], total: 0, page: 1, pageSize: 25,
  });
  refreshSession.mockResolvedValue({ role: "admin", mustChangePassword: false });
});

it("shows the session refresh failure instead of a stale authorization error", async () => {
  apiMocks.listManagedAccounts.mockRejectedValueOnce(
    Object.assign(new Error("管理访问已拒绝"), { status: 403 }),
  );
  refreshSession.mockRejectedValueOnce(new Error("当前会话状态暂时不可用"));

  const wrapper = mountView();
  await flushPromises();

  expect(wrapper.get('[role="alert"]').text()).toContain("当前会话状态暂时不可用");
  expect(wrapper.get('[role="alert"]').text()).not.toContain("管理访问已拒绝");
});
