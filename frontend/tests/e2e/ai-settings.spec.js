import { expect, test } from "@playwright/test";

const E2E_PROVIDER = "http://ai-provider:8080/v1";
const E2E_API_KEY = "e2e-api-key";
const E2E_ANSWER = "隔离模型回答：已依据当前可见资源完成分析。";

async function login(page, username = "user", password = "user123") {
  await page.goto("/#/login");
  await page.getByLabel("用户名").fill(username);
  await page.getByLabel("密码").fill(password);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page).toHaveURL(/#\/$/);
}

async function csrf(page) {
  return (await (await page.context().request.get("/api/auth/session")).json()).csrfToken;
}

async function saveUserSettings(page, data) {
  const response = await page.context().request.put("/api/ai/settings", {
    headers: { "X-CSRF-Token": await csrf(page) }, data,
  });
  expect(response.ok()).toBe(true);
}

async function saveAdminSettings(page, fallbackModel) {
  const response = await page.context().request.put("/api/admin/ai/settings", {
    headers: { "X-CSRF-Token": await csrf(page) }, data: { fallbackModel },
  });
  expect(response.ok()).toBe(true);
}

async function openFallbackSettings(page) {
  await page.getByRole("link", { name: "AI 模型设置" }).click();
  await page.getByRole("link", { name: "平台兜底模型" }).click();
  return page.getByLabel("兜底模型");
}

async function selectFallback(page, select, value) {
  await select.selectOption(value);
  await page.getByRole("button", { name: "保存平台设置" }).click();
  await expect(select).toHaveValue(value);
}

async function saveCustomModel(page, secret) {
  await page.getByRole("link", { name: "AI 模型设置" }).click();
  await page.getByLabel("自定义模型服务").check();
  await page.getByLabel("Base URL").fill("https://models.example/v1");
  await page.getByLabel("API Key").fill(secret);
  await page.getByLabel("手动设置模型").fill("manual-model");
  await page.getByRole("button", { name: "保存个人设置" }).click();
  await expect(page.getByRole("status")).toContainText("个人 AI 设置已保存");
}

async function expectSecretHidden(page, secret) {
  await expect(page.getByLabel("API Key")).toHaveValue("");
  await page.reload();
  await expect(page.getByLabel("API Key")).toHaveAttribute("placeholder", /已保存/);
  await expect(page.getByLabel("API Key")).toHaveValue("");
  await expect(page.getByText(secret)).toHaveCount(0);
}

async function configureE2EProvider(page) {
  await page.getByRole("link", { name: "AI 模型设置" }).click();
  await page.getByLabel("自定义模型服务").check();
  await page.getByLabel("Base URL").fill(E2E_PROVIDER);
  await page.getByLabel("API Key").fill(E2E_API_KEY);
  await page.getByRole("button", { name: "获取可用模型" }).click();
  const models = page.getByLabel("可用模型");
  await expect(models.locator("option")).toHaveText(["e2e-model-a", "e2e-model-b"]);
  await models.selectOption("e2e-model-a");
  await page.getByRole("button", { name: "保存个人设置" }).click();
  await expect(page.getByRole("status")).toContainText("个人 AI 设置已保存");
}

async function expectSearchAnswer(page) {
  await page.goto("/#/search?q=如何弘扬科学家精神");
  const answer = page.getByRole("region", { name: "AI 回答" });
  await expect(answer).toContainText(E2E_ANSWER);
  await expect(answer.locator(".stream-caret")).toHaveCount(0);
}

async function expectWorkbenchAnswer(page) {
  await page.goto("/#/workbench/c-draft-1");
  await expect(page.locator(".ai-status")).toContainText("e2e-model-a");
  await page.getByLabel("向 AI 提问").fill("给出一个课堂导入建议");
  await page.getByRole("button", { name: "发送", exact: true }).click();
  const answer = page.locator(".ai-message.assistant").last();
  await expect(answer).toContainText(E2E_ANSWER);
  await expect(answer.locator(".spin")).toHaveCount(0);
}

test("未配置 AI 时工作台提供设置入口且正文保持不变", async ({ page }) => {
  await login(page);
  await saveUserSettings(page, { mode: "automatic" });
  await page.goto("/#/workbench/c-draft-1");
  const title = await page.getByLabel("案例标题").inputValue();

  await expect(page.getByLabel("向 AI 提问")).toHaveAttribute("placeholder", "请先配置 AI 模型");
  await expect(page.getByRole("link", { name: "配置 AI 模型" })).toBeVisible();
  await expect(page.getByLabel("向 AI 提问")).toBeDisabled();
  await expect(page.getByLabel("案例标题")).toHaveValue(title);
});

test("管理员兜底模型只允许从环境模型列表选择", async ({ page }) => {
  await login(page, "admin", "admin123");
  await saveAdminSettings(page, null);
  const select = await openFallbackSettings(page);
  await expect(select.locator("option")).toHaveText([
    "使用环境默认模型", "e2e-model-a", "e2e-model-b",
  ]);
  await selectFallback(page, select, "e2e-model-b");
  await expect(page.getByRole("status")).toContainText("平台 AI 设置已保存");
  await expect(page.locator('input[name="fallbackModel"]')).toHaveCount(0);
  await selectFallback(page, select, "");
});

test("教师保存自定义模型后页面只显示密钥已保存状态", async ({ page }) => {
  const secret = `e2e-secret-${Date.now()}`;
  await login(page);
  try {
    await saveCustomModel(page, secret);
    await expectSecretHidden(page, secret);
  } finally {
    await saveUserSettings(page, { mode: "automatic" });
  }
});

test("教师自定义模型后可完成两处真实 AI 对话", async ({ page }) => {
  await login(page);
  try {
    await configureE2EProvider(page);
    await expectSearchAnswer(page);
    await expectWorkbenchAnswer(page);
  } finally {
    await saveUserSettings(page, { mode: "automatic" });
  }
});

test("上游失败时工作台显示明确错误", async ({ page }) => {
  await login(page);
  try {
    await configureE2EProvider(page);
    await page.goto("/#/workbench/c-draft-1");
    await page.getByLabel("向 AI 提问").fill("上游中断测试");
    await page.getByRole("button", { name: "发送", exact: true }).click();
    const panel = page.locator(".agent-chat-panel");
    await expect(panel.getByRole("alert")).toHaveText("AI 服务暂不可用");
    await expect(panel.locator(".spin")).toHaveCount(0);
  } finally {
    await saveUserSettings(page, { mode: "automatic" });
  }
});

test("390px 模型设置页没有水平溢出", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await login(page);
  await page.getByRole("link", { name: "AI 模型设置" }).click();

  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  await expect(page.getByRole("heading", { name: "AI 模型设置" })).toBeVisible();
});
