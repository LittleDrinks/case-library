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
  await beginAccountAction(page, username, "reset");
  const form = page.locator(".account-action-form");
  await form.getByLabel("新临时密码").fill(password);
  await form.getByLabel("操作理由").fill(reason);
  await form.getByRole("button", { name: "确认重置" }).click();
}

async function forceLogout(page, username) {
  await beginAccountAction(page, username, "logout");
  const form = page.locator(".account-action-form");
  await form.getByLabel("操作理由").fill("合成浏览器强制退出验收");
  await form.getByRole("button", { name: "确认强制退出" }).click();
}

async function beginAccountAction(page, username, action) {
  const row = page.locator(".account-row").filter({ hasText: username });
  await row.getByLabel(`管理账号 ${username}`).selectOption(action);
}

async function submitAccountAction(page, username, action, reason) {
  await beginAccountAction(page, username, action);
  const form = page.locator(".account-action-form");
  await form.getByLabel("操作理由").fill(reason);
  const labels = {
    disable: "确认停用",
    restore: "确认恢复",
    grantAdmin: "授予管理员",
    revokeAdmin: "撤销管理员",
  };
  await form.getByRole("button", { name: labels[action] }).click();
}

async function createCase(request, title) {
  const auth = await (await request.get("/api/auth/session")).json();
  const response = await request.post("/api/cases", {
    headers: { "X-CSRF-Token": auth.csrfToken },
    data: { title },
  });
  expect(response.ok()).toBe(true);
  return response.json();
}

async function lifecycle(request, caseId, command, submittedVersionId) {
  const auth = await (await request.get("/api/auth/session")).json();
  const current = await (await request.get(`/api/cases/${caseId}`)).json();
  const response = await request.post(`/api/cases/${caseId}/lifecycle`, {
    headers: { "X-CSRF-Token": auth.csrfToken },
    data: { command, revision: current.revision, submittedVersionId },
  });
  expect(response.ok()).toBe(true);
  return response.json();
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

  await beginAccountAction(page, target.username, "reset");
  const actionForm = page.locator(".account-action-form");
  await actionForm.getByLabel("新临时密码").fill(resetPassword);
  await actionForm.getByLabel("操作理由").fill(tooLongReason);
  await actionForm.getByRole("button", { name: "确认重置" }).click();
  await expect(page.getByRole("alert")).toHaveText("操作理由不能超过 500 个字符");
  expect((await (await page.request.get("/api/admin/account-operations")).json()).total).toBe(initialOperations);
  expect(await targetSession.evaluate(async () => (
    await fetch("/api/auth/session").then(response => response.status)
  ))).toBe(200);
  await actionForm.getByLabel("操作理由").fill("   ");
  await actionForm.getByRole("button", { name: "确认重置" }).click();
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

  await beginAccountAction(page, target.username, "logout");
  await page.locator(".account-action-form").getByLabel("操作理由").fill("   ");
  await page.locator(".account-action-form").getByRole("button", { name: "确认强制退出" }).click();
  await expect(page.getByRole("alert")).toHaveText("操作理由不能为空");
  expect(await targetSession.evaluate(async () => (
    await fetch("/api/auth/session").then(response => response.status)
  ))).toBe(200);
  expect((await (await page.request.get("/api/admin/account-operations")).json()).total).toBe(initialOperations);
  await targetSession.close();
});

test("后台停用恢复和角色操作保留作者版本引用并更新现有会话", async ({ page, browser }) => {
  const account = accountCredentials();
  const password = `Issue359-Changed-${randomUUID()}!a`;
  const title = `停用恢复保留内容 ${randomUUID()}`;
  const sourceTitle = `停用恢复引用来源 ${randomUUID()}`;
  await page.setViewportSize({ width: 390, height: 844 });
  await signIn(page, "admin", "admin123");
  await page.goto("/#/admin/accounts");
  await page.getByLabel("用户名", { exact: true }).fill(account.username);
  await page.getByLabel("临时密码", { exact: true }).fill(account.temporaryPassword);
  await page.locator(".account-open-form").getByLabel("操作理由").fill("合成停用恢复开户验收");
  await page.locator(".account-open-form").getByRole("button", { name: "开户" }).click();
  await expect(page.getByRole("status")).toContainText(account.username);

  const author = await browser.newPage();
  await signIn(author, account.username, account.temporaryPassword);
  await expect(author).toHaveURL(/#\/change-password$/);
  await author.getByLabel("当前密码").fill(account.temporaryPassword);
  await author.getByLabel("新密码", { exact: true }).fill(password);
  await author.getByLabel("确认新密码").fill(password);
  await author.getByRole("button", { name: "保存新密码" }).click();
  await expect(author).toHaveURL(/#\/login/);
  await signIn(author, account.username, password);
  const authorRequest = author.context().request;
  const authorId = (await (await authorRequest.get("/api/auth/session")).json()).user.id;

  const source = await createCase(page.context().request, sourceTitle);
  const submission = await lifecycle(page.context().request, source.id, "submit");
  await lifecycle(page.context().request, source.id, "start");
  await lifecycle(page.context().request, source.id, "approve", submission.version.id);

  const createdCase = await createCase(authorRequest, title);
  const authorSession = await (await authorRequest.get("/api/auth/session")).json();
  const mounted = await authorRequest.post(`/api/cases/${createdCase.id}/case-sources`, {
    headers: { "X-CSRF-Token": authorSession.csrfToken },
    data: {
      sourceCaseId: source.id,
      versionId: submission.version.id,
      revision: createdCase.revision,
    },
  });
  expect(mounted.ok()).toBe(true);
  const currentCase = await (await authorRequest.get(`/api/cases/${createdCase.id}`)).json();
  const versionResponse = await authorRequest.post(`/api/cases/${createdCase.id}/versions`, {
    headers: { "X-CSRF-Token": authorSession.csrfToken },
    data: { title: "停用前含引用版本", revision: currentCase.revision },
  });
  expect(versionResponse.ok()).toBe(true);
  const version = await versionResponse.json();
  expect(version.caseSources).toEqual(expect.arrayContaining([
    expect.objectContaining({
      id: (await mounted.json()).id,
      sourceCaseId: source.id,
      versionId: submission.version.id,
    }),
  ]));

  await page.getByLabel("搜索用户名").fill(account.username);
  await page.getByRole("button", { name: "搜索账号" }).click();
  await submitAccountAction(page, account.username, "disable", "合成停用保留验收");
  await expect(page.getByRole("status")).toContainText("已停用");
  expect((await authorRequest.get("/api/auth/session")).status()).toBe(401);
  expect((await authorRequest.get("/api/cases?scope=mine")).status()).toBe(401);
  const blocked = await page.request.post("/api/auth/login", {
    data: { username: account.username, password },
  });
  expect(blocked.status()).toBe(401);

  await submitAccountAction(page, account.username, "restore", "合成恢复保留验收");
  await expect(page.getByRole("status")).toContainText("已恢复");
  expect((await authorRequest.get("/api/auth/session")).status()).toBe(401);
  const recovered = await browser.newPage();
  await signIn(recovered, account.username, password);
  const recoveredRequest = recovered.context().request;
  const restoredSession = await (await recoveredRequest.get("/api/auth/session")).json();
  expect(restoredSession.user).toMatchObject({ id: authorId, role: "user", campusVerified: false });
  const mine = await (await recoveredRequest.get("/api/cases?scope=mine")).json();
  expect(mine).toContainEqual(expect.objectContaining({ id: createdCase.id, ownerId: authorId, title }));
  const history = await (await recoveredRequest.get(`/api/cases/${createdCase.id}/history`)).json();
  expect(history.versions).toContainEqual(expect.objectContaining({
    id: version.id,
    createdBy: authorId,
    caseSources: expect.arrayContaining([expect.objectContaining({
      id: (await mounted.json()).id,
      sourceCaseId: source.id,
      versionId: submission.version.id,
    })]),
  }));

  await page.getByLabel(`管理账号 ${account.username}`).selectOption("grantAdmin");
  const grantForm = page.locator(".account-action-form");
  await grantForm.getByLabel("操作理由").fill("合成授予角色验收");
  await grantForm.getByRole("button", { name: "授予管理员" }).click();
  expect((await (await recoveredRequest.get("/api/auth/session")).json()).user.role).toBe("admin");
  await recovered.reload();
  await recovered.goto("/#/admin/accounts");
  await expect(recovered.getByRole("heading", { name: "账号管理" })).toBeVisible();

  await submitAccountAction(page, account.username, "revokeAdmin", "合成撤销角色验收");
  await recovered.getByRole("button", { name: "刷新账号" }).click();
  await expect(recovered.getByRole("alert")).toContainText("当前角色：普通用户");
  expect((await (await recoveredRequest.get("/api/auth/session")).json()).user.role).toBe("user");
  expect((await recoveredRequest.get("/api/admin/accounts")).status()).toBe(403);

  await page.getByRole("tab", { name: "操作记录" }).click();
  for (const reason of [
    "合成停用保留验收",
    "合成恢复保留验收",
    "合成授予角色验收",
    "合成撤销角色验收",
  ]) {
    await expect(page.locator(".account-operation-list")).toContainText(reason);
  }
  const operationText = await page.locator(".account-operation-list").innerText();
  expect(operationText).not.toContain(password);
  expect(operationText).not.toContain("password_hash");
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  await author.close();
  await recovered.close();
});
