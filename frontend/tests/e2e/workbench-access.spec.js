import { expect, test } from "@playwright/test";

async function login(page, username, password) {
  await page.goto("/#/login");
  await page.getByLabel("用户名").fill(username);
  await page.getByLabel("密码").fill(password);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page).toHaveURL(/#\/$/);
}

async function logout(page) {
  await page.getByRole("button", { name: "退出登录" }).click();
  await expect(page).toHaveURL(/#\/login$/);
}

async function createCase(request, title) {
  const auth = await (await request.get("/api/auth/session")).json();
  const response = await request.post("/api/cases", {
    headers: { "X-CSRF-Token": auth.csrfToken }, data: { title },
  });
  expect(response.ok()).toBe(true);
  return response.json();
}

test("普通非作者不会挂载画布，且返回历史不会回到工作台", async ({ page }) => {
  await login(page, "user", "user123");
  await page.goto("/#/");
  await page.evaluate(() => { window.location.hash = "#/workbench/c-02"; });

  await expect(page).toHaveURL(/#\/cases\/c-02$/);
  await expect(page.getByRole("link", { name: "进入工作台" })).toHaveCount(0);
  await expect(page.locator(".canvas-workspace, .assistant-rail, .workspace-header")).toHaveCount(0);
  await page.goBack();
  await expect(page).toHaveURL(/#\/$/);
});

test("作者已发布案例仍可进入工作台，非作者管理员改入审核路由", async ({ page }) => {
  await login(page, "admin", "admin123");
  await page.goto("/#/workbench/c-02");

  await expect(page.locator(".canvas-workspace")).toBeVisible();
  await page.goto("/#/workbench/c-pending-1");
  await expect(page).toHaveURL(/#\/admin\/review\/c-pending-1$/);
  await expect(page.locator(".workspace-crumb")).toContainText("审核管理");
});

test("非公开案例的工作台 URL 只显示通用不可访问提示", async ({ page }) => {
  await login(page, "admin", "admin123");
  const created = await createCase(page.context().request, `私密重定向 ${Date.now()}`);
  await logout(page);
  await login(page, "user", "user123");
  await page.goto(`/#/workbench/${created.id}`);

  await expect(page).toHaveURL(/#\/my-cases$/);
  await expect(page.getByRole("alert")).toHaveText("案例不可访问");
  await expect(page.locator(".canvas-workspace, .assistant-rail, .workspace-header")).toHaveCount(0);
});
