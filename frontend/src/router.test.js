import { beforeEach, expect, it, vi } from "vitest";

const state = vi.hoisted(() => ({
  api: { getCase: vi.fn() },
  session: { user: null },
  restoreSession: vi.fn(),
}));

vi.mock("./api.js", () => ({ api: state.api }));
vi.mock("./session.js", () => ({ session: state.session, restoreSession: state.restoreSession }));

let router;

beforeEach(async () => {
  vi.clearAllMocks();
  state.session.user = null;
  state.restoreSession.mockResolvedValue(null);
  window.history.replaceState({}, "", "/#/");
  window.scrollTo = vi.fn();
  vi.resetModules();
  ({ router } = await import("./router.js"));
  await router.push("/");
});

it("匿名访问工作台时保留登录后的 redirect", async () => {
  await router.push("/workbench/case-1");

  expect(router.currentRoute.value).toMatchObject({
    name: "login", query: { redirect: "/workbench/case-1" },
  });
  expect(state.api.getCase).not.toHaveBeenCalled();
});
