import { expect, it } from "vitest";
import { ApiError } from "../api.js";
import { caseUnavailableNotice, resolveWorkbenchAccess } from "./workbenchAccess.js";

const author = { id: "author", role: "user" };
const administrator = { id: "admin", role: "admin" };
const publicCase = { id: "case-1", publicationStatus: "public" };
const authorCases = [
  ["草稿", { workflowStatus: "draft", publicationStatus: "none" }],
  ["待审", { workflowStatus: "pending", publicationStatus: "none" }],
  ["审核中", { workflowStatus: "reviewing", publicationStatus: "none" }],
  ["已隐藏", { workflowStatus: "published", publicationStatus: "hidden" }],
];

it.each(authorCases)("作者可进入%s案例的工作台", async (_, caseRecord) => {
  const target = await resolveWorkbenchAccess("case-1", author, async () => ({
    ownerId: "author", ...caseRecord,
  }));

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

  expect(target).toEqual({
    name: "my-cases", query: { notice: caseUnavailableNotice }, replace: true,
  });
});

it("非作者管理员进入同一案例的审核路由", async () => {
  const target = await resolveWorkbenchAccess("case-1", administrator, async () => ({ ownerId: "author" }));

  expect(target).toEqual({ name: "case-review", params: { id: "case-1" }, replace: true });
});
