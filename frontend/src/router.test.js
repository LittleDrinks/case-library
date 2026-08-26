import { beforeEach, expect, it, vi } from "vitest";
import { caseUnavailableNotice } from "./lib/workbenchAccess.js";

const state = vi.hoisted(() => ({
  api: { getCase: vi.fn() },
  session: { user: null },
  restoreSession: vi.fn(),
}));
const authorCases = [
  ["草稿", { workflowStatus: "draft", publicationStatus: "none" }],
  ["待审", { workflowStatus: "pending", publicationStatus: "none" }],
  ["审核中", { workflowStatus: "reviewing", publicationStatus: "none" }],
  ["已隐藏", { workflowStatus: "published", publicationStatus: "hidden" }],
];

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

it("已完成改密的用户访问改密页时回到首页", async () => {
  state.session.user = { id: "author", role: "user", mustChangePassword: false };

  await router.push("/change-password");

  expect(router.currentRoute.value).toMatchObject({ name: "home" });
});

it("登录后重新评估工作台访问", async () => {
  await router.push("/workbench/case-1");
  state.session.user = { id: "reader", role: "user" };
  state.api.getCase.mockResolvedValue({ ownerId: "author" });

  await router.replace(router.currentRoute.value.query.redirect);

  expect(router.currentRoute.value).toMatchObject({ name: "case-public", params: { id: "case-1" } });
});

it("普通非作者直接进入公开案例时替换为公开详情", async () => {
  state.session.user = { id: "reader", role: "user" };
  state.api.getCase.mockResolvedValue({ ownerId: "author" });

  await router.push("/workbench/case-1");

  expect(router.currentRoute.value).toMatchObject({ name: "case-public", params: { id: "case-1" } });
});

it.each(["none", "hidden", "missing"])("普通非作者直接进入 %s 案例时显示通用提示", async () => {
  state.session.user = { id: "reader", role: "user" };
  state.api.getCase.mockRejectedValue(notFound());

  await router.push("/workbench/case-1");

  expect(router.currentRoute.value).toMatchObject({
    name: "my-cases", query: { notice: caseUnavailableNotice },
  });
});

it("非作者管理员直接进入审核路由", async () => {
  state.session.user = { id: "admin", role: "admin" };
  state.api.getCase.mockResolvedValue({ ownerId: "author" });

  await router.push("/workbench/case-1");

  expect(router.currentRoute.value).toMatchObject({ name: "case-review", params: { id: "case-1" } });
});

it.each(authorCases)("作者直接进入%s案例的工作台", async (_, caseRecord) => {
  state.session.user = { id: "author", role: "user" };
  state.api.getCase.mockResolvedValue({ ownerId: "author", ...caseRecord });

  await router.push("/workbench/case-1");

  expect(router.currentRoute.value).toMatchObject({ name: "workbench", params: { id: "case-1" } });
});

function notFound() {
  return { status: 404, message: "案例不存在" };
}
