import { randomUUID } from "node:crypto";
import { expect, test } from "@playwright/test";

function accountCredentials() {
  return {
    username: `issue357-browser-${randomUUID()}`,
    temporaryPassword: `Issue357-${randomUUID()}!a`,
  };
}

async function signIn(page, username, password) {
  await page.goto("/#/login");
  await page.getByLabel("用户名").fill(username);
  await page.getByLabel("密码").fill(password);
  await page.getByRole("button", { name: "登录", exact: true }).click();
}

async function setTemporaryPassword(page, username, password, reason) {
  const row = page.locator(".account-row").filter({ hasText: username });
  await row.getByRole("button", { name: "重置临时密码" }).click();
  const form = page.locator(".account-action-form");
  await form.getByLabel("新临时密码").fill(password);
  await form.getByLabel("操作理由").fill(reason);
  await form.getByRole("button", { name: "确认" }).click();
}

async function forceLogout(page, username) {
  const row = page.locator(".account-row").filter({ hasText: username });
  await row.getByRole("button", { name: "强制退出" }).click();
  const form = page.locator(".account-action-form");
  await form.getByLabel("操作理由").fill("合成浏览器强制退出验收");
  await form.getByRole("button", { name: "确认" }).click();
}

test("管理员可通过页面开户、恢复密码、撤销会话并查阅持久记录", async ({ page, browser }) => {
  const adminPassword = "admin123";
  const first = accountCredentials();
  const changedPassword = `Issue357-Changed-${randomUUID()}!a`;
  const resetPassword = `Issue357-Reset-${randomUUID()}!a`;
  const recoveredPassword = `Issue357-Recovered-${randomUUID()}!a`;
  await page.setViewportSize({ width: 390, height: 844 });
  await signIn(page, "admin", adminPassword);
  await page.goto("/#/admin/accounts");
  await expect(page.getByRole("heading", { name: "账号管理" })).toBeVisible();

  await page.getByLabel("用户名", { exact: true }).fill(first.username);
  await page.getByLabel("临时密码", { exact: true }).fill(first.temporaryPassword);
  await page.locator(".account-open-form").getByLabel("操作理由").fill("合成浏览器开户验收");
  await page.locator(".account-open-form").getByRole("button", { name: "开户" }).click();
  await expect(page.getByRole("status")).toContainText(first.username);
  await page.getByLabel("搜索用户名").fill(first.username);
  await page.getByRole("button", { name: "搜索账号" }).click();
  await expect(page.locator(".account-row").filter({ hasText: first.username })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);

  const firstUser = await browser.newPage();
  await signIn(firstUser, first.username, first.temporaryPassword);
  await expect(firstUser).toHaveURL(/#\/change-password$/);
  await firstUser.goto("/#/my-cases");
  await expect(firstUser).toHaveURL(/#\/change-password$/);
  await firstUser.getByLabel("当前密码").fill(first.temporaryPassword);
  await firstUser.getByLabel("新密码", { exact: true }).fill(changedPassword);
  await firstUser.getByLabel("确认新密码").fill(changedPassword);
  await firstUser.getByRole("button", { name: "保存新密码" }).click();
  await expect(firstUser).toHaveURL(/#\/login/);
  expect((await firstUser.request.get("/api/auth/session")).status()).toBe(401);
  await signIn(firstUser, first.username, changedPassword);
  await expect(firstUser).toHaveURL(/#\/$/);
  const ownerId = (await (await firstUser.request.get("/api/auth/session")).json()).user.id;
  await firstUser.goto("/#/my-cases");
  await expect(firstUser.getByRole("heading", { name: "我的案例" })).toBeVisible();

  const secondSession = await browser.newPage();
  await signIn(secondSession, first.username, changedPassword);
  await expect(secondSession).toHaveURL(/#\/$/);
  await setTemporaryPassword(page, first.username, resetPassword, "合成浏览器密码恢复验收");
  await expect(page.getByRole("status")).toContainText("新的临时密码");
  expect((await secondSession.request.get("/api/auth/session")).status()).toBe(401);

  await firstUser.reload();
  await expect(firstUser).toHaveURL(/#\/login/);
  await signIn(firstUser, first.username, resetPassword);
  await expect(firstUser).toHaveURL(/#\/change-password$/);
  await expect((await firstUser.request.get("/api/auth/session")).status()).toBe(200);
  const resetSession = await (await firstUser.request.get("/api/auth/session")).json();
  expect(resetSession.user.id).toBe(ownerId);
  expect(resetSession.user.mustChangePassword).toBe(true);
  await firstUser.getByLabel("当前密码").fill(resetPassword);
  await firstUser.getByLabel("新密码", { exact: true }).fill(recoveredPassword);
  await firstUser.getByLabel("确认新密码").fill(recoveredPassword);
  await firstUser.getByRole("button", { name: "保存新密码" }).click();
  await expect(firstUser).toHaveURL(/#\/login/);
  expect((await firstUser.request.get("/api/auth/session")).status()).toBe(401);
  await signIn(firstUser, first.username, recoveredPassword);
  await expect(firstUser).toHaveURL(/#\/$/);
  await firstUser.goto("/#/my-cases");
  await expect(firstUser.getByRole("heading", { name: "我的案例" })).toBeVisible();

  const forceSession = await browser.newPage();
  await signIn(forceSession, first.username, recoveredPassword);
  await expect(forceSession).toHaveURL(/#\/$/);
  await forceLogout(page, first.username);
  await expect(page.getByRole("status")).toContainText("撤销 2 个会话");
  expect((await firstUser.request.get("/api/auth/session")).status()).toBe(401);
  expect((await forceSession.request.get("/api/auth/session")).status()).toBe(401);

  await page.getByRole("tab", { name: "操作记录" }).click();
  await expect(page.getByText("合成浏览器强制退出验收")).toBeVisible();
  await page.reload();
  await page.getByRole("tab", { name: "操作记录" }).click();
  await expect(page.getByText("合成浏览器强制退出验收")).toBeVisible();
  await expect(page.locator(".account-operation-row").filter({ hasText: first.username }).filter({ hasText: "后台开户" })).toBeVisible();
  const operationText = await page.locator(".account-operation-list").innerText();
  for (const secret of [first.temporaryPassword, changedPassword, resetPassword, recoveredPassword]) {
    expect(operationText.includes(secret), "操作记录不能包含密码").toBe(false);
  }

  await firstUser.close();
  await secondSession.close();
  await forceSession.close();
});

test("账号搜索和重复开户失败会显示服务端错误", async ({ page }) => {
  const duplicatePassword = `Issue357-Duplicate-${randomUUID()}!a`;
  await page.setViewportSize({ width: 390, height: 844 });
  await signIn(page, "admin", "admin123");
  await page.goto("/#/admin/accounts");
  const openForm = page.locator(".account-open-form");
  await openForm.getByLabel("用户名", { exact: true }).fill("admin");
  await expect(openForm.getByLabel("用户名", { exact: true })).toHaveValue("admin");
  await openForm.getByLabel("临时密码", { exact: true }).fill(duplicatePassword);
  await openForm.getByLabel("操作理由").fill("合成重复开户验收");
  await page.locator(".account-open-form").getByRole("button", { name: "开户" }).click();
  await expect(page.getByRole("alert")).toHaveText("用户名已存在");
  await page.getByLabel("搜索用户名").fill("ADMIN");
  await page.getByRole("button", { name: "搜索账号" }).click();
  await expect(page.locator(".account-row")).toHaveCount(1);
  await expect(page.locator(".account-row")).toContainText("admin");
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
});

test("账号管理清楚拒绝无效用户名和理由且不产生写入", async ({ page, browser }) => {
  const target = accountCredentials();
  const unused = accountCredentials();
  const resetPassword = `Issue357-Unused-${randomUUID()}!a`;
  const tooLongReason = "r".repeat(501);
  await page.setViewportSize({ width: 390, height: 844 });
  await signIn(page, "admin", "admin123");
  await page.goto("/#/admin/accounts");
  await expect(page.getByRole("heading", { name: "账号管理" })).toBeVisible();
  const opened = await page.evaluate(async account => {
    const adminSession = await fetch("/api/auth/session").then(response => response.json());
    const response = await fetch("/api/admin/accounts", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": adminSession.csrfToken,
      },
      body: JSON.stringify({
        username: account.username,
        temporaryPassword: account.temporaryPassword,
        reason: "合成空白理由回归",
      }),
    });
    return response.status;
  }, target);
  expect(opened).toBe(201);
  await page.reload();
  await page.getByLabel("搜索用户名").fill(target.username);
  await page.getByRole("button", { name: "搜索账号" }).click();
  await expect(page.locator(".account-row").filter({ hasText: target.username })).toBeVisible();
  const targetSession = await browser.newPage();
  await signIn(targetSession, target.username, target.temporaryPassword);
  const operationResponse = await page.request.get("/api/admin/account-operations");
  const initialOperations = (await operationResponse.json()).total;

  const openForm = page.locator(".account-open-form");
  await page.getByLabel("用户名", { exact: true }).fill("   ");
  await page.getByLabel("临时密码", { exact: true }).fill(unused.temporaryPassword);
  await openForm.getByLabel("操作理由").fill("合成空白用户名验证");
  await openForm.getByRole("button", { name: "开户" }).click();
  await expect(page.getByRole("alert")).toHaveText("用户名不能为空");
  await page.getByLabel("用户名", { exact: true }).fill(unused.username);
  await openForm.getByLabel("操作理由").fill(tooLongReason);
  await openForm.getByRole("button", { name: "开户" }).click();
  await expect(page.getByRole("alert")).toHaveText("操作理由不能超过 500 个字符");
  const untouchedOperations = await page.request.get("/api/admin/account-operations");
  expect((await untouchedOperations.json()).total).toBe(initialOperations);
  await openForm.getByLabel("操作理由").fill("   ");
  await openForm.getByRole("button", { name: "开户" }).click();
  await expect(page.getByRole("alert")).toHaveText("操作理由不能为空");
  const unusedListing = await page.request.get(`/api/admin/accounts?q=${encodeURIComponent(unused.username)}`);
  expect((await unusedListing.json()).total).toBe(0);

  const accountRow = page.locator(".account-row").filter({ hasText: target.username });
  await accountRow.getByRole("button", { name: "重置临时密码" }).click();
  const actionForm = page.locator(".account-action-form");
  await actionForm.getByLabel("新临时密码").fill(resetPassword);
  await actionForm.getByLabel("操作理由").fill(tooLongReason);
  await actionForm.getByRole("button", { name: "确认" }).click();
  await expect(page.getByRole("alert")).toHaveText("操作理由不能超过 500 个字符");
  expect((await (await page.request.get("/api/admin/account-operations")).json()).total).toBe(initialOperations);
  expect(await targetSession.evaluate(async () => (
    await fetch("/api/auth/session").then(response => response.status)
  ))).toBe(200);
  await actionForm.getByLabel("操作理由").fill("   ");
  await actionForm.getByRole("button", { name: "确认" }).click();
  await expect(page.getByRole("alert")).toHaveText("操作理由不能为空");
  await expect(targetSession).toHaveURL(/#\/change-password$/);
  expect(await targetSession.evaluate(async () => (
    await fetch("/api/auth/session").then(response => response.status)
  ))).toBe(200);
  const resetLoginStatus = await targetSession.evaluate(async credentials => (
    await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(credentials),
    }).then(response => response.status)
  ), { username: target.username, password: resetPassword });
  expect(resetLoginStatus).toBe(401);
  await actionForm.getByRole("button", { name: "取消" }).click();

  await accountRow.getByRole("button", { name: "强制退出" }).click();
  await page.locator(".account-action-form").getByLabel("操作理由").fill("   ");
  await page.locator(".account-action-form").getByRole("button", { name: "确认" }).click();
  await expect(page.getByRole("alert")).toHaveText("操作理由不能为空");
  expect(await targetSession.evaluate(async () => (
    await fetch("/api/auth/session").then(response => response.status)
  ))).toBe(200);
  expect((await (await page.request.get("/api/admin/account-operations")).json()).total).toBe(initialOperations);
  await targetSession.close();
});
