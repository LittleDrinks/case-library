import { randomUUID } from "node:crypto";
import { expect, test } from "@playwright/test";

function credentials() {
  return {
    username: `issue360-browser-${randomUUID()}`,
    password: `Issue360-${randomUUID()}!a`,
  };
}

async function signIn(page, username, password) {
  await page.goto("/#/login");
  await page.getByLabel("用户名").fill(username);
  await page.getByLabel("密码").fill(password);
  await page.getByRole("button", { name: "登录", exact: true }).click();
}

async function setReasonAndConfirm(page, reason, button) {
  await page.getByLabel("操作理由").fill(reason);
  await page.getByRole("button", { name: button, exact: true }).click();
}

test("本人可查看申请历史，管理员决定与撤销后必须重新人工批准", async ({ page, browser }, testInfo) => {
  const account = credentials();
  const adminContext = await browser.newContext({ baseURL: testInfo.project.use.baseURL });
  const adminPage = await adminContext.newPage();
  await page.setViewportSize({ width: 390, height: 844 });

  await page.goto("/#/register");
  await page.getByLabel("用户名").fill(account.username);
  await page.getByLabel("密码").fill(account.password);
  await page.getByRole("button", { name: "创建账号" }).click();
  await expect(page).toHaveURL(/#\/login\?/);
  await signIn(page, account.username, account.password);
  await page.goto("/#/campus-access");
  await expect(page.getByRole("heading", { name: "尚未申请" })).toBeVisible();

  const auth = await (await page.request.get("/api/auth/session")).json();
  expect(auth.user.campusVerified).toBe(false);
  await page.getByLabel("姓名").fill("合成浏览器申请人甲");
  await page.getByLabel("学工号").fill(`SYN-${randomUUID()}`);
  await page.getByRole("button", { name: "提交申请" }).click();
  await expect(page.getByRole("heading", { name: "等待管理员审核" })).toBeVisible();
  await page.reload();
  await expect(page.getByText("合成浏览器申请人甲")).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);

  await signIn(adminPage, "admin", "admin123");
  await adminPage.goto("/#/admin/campus-access");
  await adminPage.getByLabel("搜索申请人").fill(account.username);
  await adminPage.getByRole("button", { name: "查询" }).click();
  const firstRow = adminPage.locator(".campus-admin-row").filter({ hasText: account.username });
  await firstRow.getByRole("button", { name: "拒绝" }).click();
  await setReasonAndConfirm(adminPage, "合成资料需重新核验", "确认拒绝");
  await expect(adminPage.getByRole("status")).toContainText("已拒绝");

  await page.reload();
  await expect(page.getByRole("heading", { name: "申请被拒绝" })).toBeVisible();
  await expect(page.getByText("合成资料需重新核验")).toBeVisible();
  await page.getByLabel("姓名").fill("合成浏览器申请人乙");
  await page.getByLabel("学工号").fill(`SYN-${randomUUID()}`);
  await page.getByRole("button", { name: "提交申请" }).click();
  await expect(page.getByRole("heading", { name: "等待管理员审核" })).toBeVisible();

  await adminPage.getByLabel("申请状态").selectOption("pending");
  await adminPage.getByRole("button", { name: "查询" }).click();
  const secondRow = adminPage.locator(".campus-admin-row").filter({ hasText: account.username });
  await secondRow.getByRole("button", { name: "批准" }).click();
  await setReasonAndConfirm(adminPage, "合成身份已核验", "确认批准");
  await page.reload();
  await expect(page.getByRole("heading", { name: "已获校内访问资格" })).toBeVisible();

  await adminPage.getByLabel("申请状态").selectOption("approved");
  await adminPage.getByRole("button", { name: "查询" }).click();
  const approvedRow = adminPage.locator(".campus-admin-row").filter({ hasText: account.username });
  await approvedRow.getByRole("button", { name: "撤销资格" }).click();
  await setReasonAndConfirm(adminPage, "合成资格需要重新核验", "确认撤销");
  await page.reload();
  await expect(page.getByRole("heading", { name: "校内资格已撤销" })).toBeVisible();

  await page.getByLabel("姓名").fill("合成浏览器申请人丙");
  await page.getByLabel("学工号").fill(`SYN-${randomUUID()}`);
  await page.getByRole("button", { name: "提交申请" }).click();
  await expect(page.getByRole("heading", { name: "等待管理员审核" })).toBeVisible();
  await page.reload();
  await expect(page.getByRole("heading", { name: "等待管理员审核" })).toBeVisible();

  await adminPage.getByLabel("申请状态").selectOption("pending");
  await adminPage.getByRole("button", { name: "查询" }).click();
  const thirdRow = adminPage.locator(".campus-admin-row").filter({ hasText: account.username });
  const staleAdminContext = await browser.newContext({ baseURL: testInfo.project.use.baseURL });
  const staleAdminPage = await staleAdminContext.newPage();
  await signIn(staleAdminPage, "admin", "admin123");
  await staleAdminPage.goto("/#/admin/campus-access");
  await staleAdminPage.getByLabel("搜索申请人").fill(account.username);
  await staleAdminPage.getByLabel("申请状态").selectOption("pending");
  await staleAdminPage.getByRole("button", { name: "查询" }).click();
  const staleThirdRow = staleAdminPage.locator(".campus-admin-row").filter({ hasText: account.username });

  await thirdRow.getByRole("button", { name: "批准" }).click();
  await setReasonAndConfirm(adminPage, "合成资料再次通过人工核验", "确认批准");
  await staleThirdRow.getByRole("button", { name: "拒绝" }).click();
  await setReasonAndConfirm(staleAdminPage, "合成过期拒绝尝试", "确认拒绝");
  await expect(staleAdminPage.getByRole("alert")).toContainText("申请已处理，不能重复决定");
  await page.reload();
  await expect(page.getByRole("heading", { name: "已获校内访问资格" })).toBeVisible();
  await expect(page.getByText("合成资格需要重新核验")).toBeVisible();

  await staleAdminContext.close();
  await adminContext.close();
});

test("旧系统授权分页、列表失败重试与撤销使用当前服务端状态", async ({ page }) => {
  const prefix = "issue360-legacy-browser";
  let failFirstFilteredRequest = true;

  await signIn(page, "admin", "admin123");
  await page.goto("/#/admin/campus-access");
  await page.route("**/api/admin/campus-access-legacy-grants?*", async (route) => {
    const requestUrl = new URL(route.request().url());
    if (failFirstFilteredRequest && requestUrl.searchParams.get("q") === prefix) {
      failFirstFilteredRequest = false;
      await route.fulfill({
        status: 503,
        contentType: "application/json",
        body: JSON.stringify({ detail: "合成旧授权列表暂时不可用" }),
      });
      return;
    }
    await route.continue();
  });

  await page.getByLabel("搜索申请人").fill(prefix);
  await page.getByRole("button", { name: "查询", exact: true }).click();
  const legacy = page.locator(".campus-admin-legacy");
  await expect(legacy.getByRole("alert")).toContainText("合成旧授权列表暂时不可用");
  await legacy.getByRole("button", { name: "重试" }).click();
  await expect(legacy).toContainText("共 51 个账号");
  await expect(legacy.getByText("第 1 / 2 页")).toBeVisible();

  await legacy.getByRole("button", { name: "下一页旧系统授权" }).click();
  await expect(legacy.getByText("第 2 / 2 页")).toBeVisible();
  const targetUsername = `${prefix}-051`;
  const target = legacy.locator(".campus-admin-row").filter({ hasText: targetUsername });
  await expect(target).toContainText("旧系统授权");
  await target.getByRole("button", { name: "撤销资格" }).click();

  const action = page.locator(".campus-admin-action");
  await expect(action).toContainText("无历史申请或自填身份资料");
  await action.getByLabel("操作理由").fill("合成浏览器确认旧授权撤销");
  await action.getByRole("button", { name: "确认撤销" }).click();
  await expect(page.getByRole("status")).toContainText(`${targetUsername} 的旧系统校内资格`);
  await expect(legacy).toContainText("共 50 个账号");
  await expect(legacy.getByText("第 1 / 1 页")).toBeVisible();

  const current = await page.request.get(
    `/api/admin/campus-access-legacy-grants?q=${encodeURIComponent(targetUsername)}`,
  );
  expect(current.status()).toBe(200);
  expect((await current.json()).items).toEqual([]);

  const operations = await page.request.get("/api/admin/account-operations?page=1&pageSize=100");
  expect(operations.status()).toBe(200);
  expect((await operations.json()).items).toContainEqual(expect.objectContaining({
    action: "campus_access_legacy_revoke",
    targetId: expect.stringMatching(/^u-issue360-legacy-browser-051$/),
    reason: "合成浏览器确认旧授权撤销",
    result: "success",
  }));
});
