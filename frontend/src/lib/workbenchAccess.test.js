import { expect, it } from "vitest";
import { ApiError } from "../api.js";
import { resolveWorkbenchAccess } from "./workbenchAccess.js";

const author = { id: "author", role: "user" };
const administrator = { id: "admin", role: "admin" };
const publicCase = { id: "case-1", publicationStatus: "public" };

it("作者可在路由挂载前进入自己的工作台", async () => {
  const target = await resolveWorkbenchAccess("case-1", author, async () => ({ ownerId: "author" }));

  expect(target).toBeNull();
});

it("普通非作者访问公开案例时替换为公开详情", async () => {
  const target = await resolveWorkbenchAccess("case-1", author, async () => publicCase);

  expect(target).toEqual({ name: "case-public", params: { id: "case-1" }, replace: true });
});

it("普通非作者访问不可见案例时替换为我的案例", async () => {
  const target = await resolveWorkbenchAccess("case-1", author, async () => {
    throw new ApiError(new Response("", { status: 404 }), { detail: "案例不存在" });
  });

  expect(target).toEqual({ name: "my-cases", replace: true });
});

it("非作者管理员进入同一案例的审核路由", async () => {
  const target = await resolveWorkbenchAccess("case-1", administrator, async () => ({ ownerId: "author" }));

  expect(target).toEqual({ name: "case-review", params: { id: "case-1" }, replace: true });
});
