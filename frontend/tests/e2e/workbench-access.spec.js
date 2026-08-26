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

async function openAdminCase(page, rowName, linkName, caseId) {
  const row = page.getByRole("article", { name: rowName });
  const link = row.getByRole("link", { name: linkName, exact: true });
  await expect(row).toHaveCount(1);
  await expect(link).toHaveAttribute("href", `#/admin/review/${caseId}`);
  await link.click();
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

test("匿名用户登录后重新评估原工作台 URL", async ({ page }) => {
  await page.goto("/#/workbench/c-02");
  await expect(page).toHaveURL(/#\/login\?redirect=\/workbench\/c-02$/);
  await page.getByLabel("用户名").fill("user");
  await page.getByLabel("密码").fill("user123");
  await page.getByRole("button", { name: "登录", exact: true }).click();

  await expect(page).toHaveURL(/#\/cases\/c-02$/);
});

test("作者已发布案例仍可进入工作台，非作者管理员改入审核路由", async ({ page }) => {
  await login(page, "admin", "admin123");
  await page.goto("/#/workbench/c-02");

  await expect(page.locator(".canvas-workspace")).toBeVisible();
  await page.goto("/#/workbench/c-pending-1");
  await expect(page).toHaveURL(/#\/admin\/review\/c-pending-1$/);
  await expect(page.locator(".workspace-crumb")).toContainText("审核管理");
});

test("管理员从管理后台进入审核和发布管理", async ({ page }) => {
  await login(page, "admin", "admin123");
  await page.goto("/#/admin");
  await openAdminCase(page, /待审核：生成式人工智能进课堂/, "审核", "c-pending-1");
  await expect(page).toHaveURL(/#\/admin\/review\/c-pending-1$/);
  await page.goto("/#/admin");
  await openAdminCase(page, /已发布：钱伟长图书馆/, "发布管理", "c-02");

  await expect(page).toHaveURL(/#\/admin\/review\/c-02$/);
});

test("非公开案例的工作台 URL 在已挂载列表显示通用提示且不残留", async ({ page }) => {
  await login(page, "admin", "admin123");
  const created = await createCase(page.context().request, `私密重定向 ${Date.now()}`);
  await logout(page);
  await login(page, "user", "user123");
  await page.goto("/#/my-cases");
  await page.evaluate((id) => { window.location.hash = `#/workbench/${id}`; }, created.id);

  await expect(page).toHaveURL(/#\/my-cases\?notice=case-unavailable$/);
  await expect(page.getByRole("alert")).toHaveText("案例不可访问");
  await expect(page.locator(".canvas-workspace, .assistant-rail, .workspace-header")).toHaveCount(0);
  await page.goto("/#/");
  await page.getByRole("link", { name: "我的案例", exact: true }).click();
  await expect(page.locator(".catalog-notice")).toHaveCount(0);
});
