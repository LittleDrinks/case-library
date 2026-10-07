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
  await thirdRow.getByRole("button", { name: "批准" }).click();
  await setReasonAndConfirm(adminPage, "合成资料再次通过人工核验", "确认批准");
  await page.reload();
  await expect(page.getByRole("heading", { name: "已获校内访问资格" })).toBeVisible();
  await expect(page.getByText("合成资格需要重新核验")).toBeVisible();

  await adminContext.close();
});
