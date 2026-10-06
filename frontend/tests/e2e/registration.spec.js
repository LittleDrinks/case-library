import { randomUUID } from "node:crypto";
import { expect, test } from "@playwright/test";

function credentials() {
  return {
    username: `issue356-${randomUUID()}`,
    password: `Issue356-${randomUUID()}!a`,
  };
}

async function register(page, username, password) {
  await page.goto("/#/register");
  await page.getByLabel("用户名").fill(username);
  await page.getByLabel("密码").fill(password);
  await page.getByRole("button", { name: "创建账号" }).click();
}

test("访客注册登录后可创建私人草稿、投稿并刷新确认作者归属", async ({ page }) => {
  const account = credentials();
  const title = `首次投稿 ${randomUUID()}`;
  await register(page, account.username, account.password);
  await expect(page).toHaveURL(/#\/login\?/);
  await expect(page.getByRole("status")).toContainText("账号创建成功");

  await page.getByLabel("密码").fill(account.password);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page).toHaveURL(/#\/$/);

  const authResponse = await page.context().request.get("/api/auth/session");
  expect(authResponse.ok()).toBe(true);
  const ownerId = (await authResponse.json()).user.id;
  await page.goto("/#/my-cases");
  await page.getByRole("button", { name: "新建案例" }).click();
  await expect(page.getByLabel("案例标题")).toHaveValue("未命名案例");
  await page.getByLabel("案例标题").fill(title);
  await expect(page.locator(".save-state")).toHaveText("已保存", { timeout: 10000 });

  const createdResponse = await page.context().request.get(
    "/api/cases?scope=mine",
  );
  expect(createdResponse.ok()).toBe(true);
  const mine = await createdResponse.json();
  const draft = mine.find((item) => item.title === title);
  expect(draft).toMatchObject({
    ownerId,
    workflowStatus: "draft",
    publicationStatus: "none",
  });

  await page.getByRole("button", { name: "提交审核", exact: true }).click();
  await expect(page.locator(".case-status")).toHaveText("待审");
  await page.reload();
  await expect(page.getByLabel("案例标题")).toHaveValue(title);
  await expect(page.locator(".case-status")).toHaveText("待审");

  const persistedResponse = await page.context().request.get(`/api/cases/${draft.id}`);
  expect(persistedResponse.ok()).toBe(true);
  expect(await persistedResponse.json()).toMatchObject({
    id: draft.id,
    ownerId,
    title,
    workflowStatus: "pending",
    publicationStatus: "none",
  });
});

test("注册页面明确反馈重复用户名和弱密码", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const account = credentials();

  await register(page, "   ", account.password);
  await expect(page.getByRole("alert")).toHaveText("请输入用户名");

  await register(page, account.username, account.password);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  await expect(page).toHaveURL(/#\/login\?/);

  await register(page, account.username, account.password);
  await expect(page.getByRole("alert")).toHaveText("用户名已存在");

  await page.getByLabel("用户名").fill(`issue356-${randomUUID()}`);
  await page.getByLabel("密码").fill("short");
  await page.getByRole("button", { name: "创建账号" }).click();
  await expect(page.getByRole("alert")).toHaveText("密码至少 12 个字符");

  await page.getByLabel("用户名").fill(`issue356-${randomUUID()}`);
  await page.getByLabel("密码").fill("x".repeat(73));
  await page.getByRole("button", { name: "创建账号" }).click();
  await expect(page.getByRole("alert")).toHaveText("密码不能超过 72 字节");
});
