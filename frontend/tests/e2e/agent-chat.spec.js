import { expect, test } from "@playwright/test";

const ANSWER = "隔离 FunctionModel 回答：已依据当前案例完成分析。";

async function login(page) {
  await page.goto("/#/login");
  await page.getByLabel("用户名").fill("user");
  await page.getByLabel("密码").fill("user123");
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page).toHaveURL(/#\/$/);
}

async function csrf(page) {
  const response = await page.context().request.get("/api/auth/session");
  return (await response.json()).csrfToken;
}

function caseDocument(text) {
  return {
    type: "doc",
    content: [{ type: "paragraph", content: [{ type: "text", text }] }],
  };
}

async function createCase(page) {
  const response = await page.context().request.post("/api/cases", {
    headers: { "X-CSRF-Token": await csrf(page) },
    data: {
      title: `Chat seam ${Date.now()}`,
      document: caseDocument("当前案例测试正文"),
    },
  });
  expect(response.ok()).toBe(true);
  return response.json();
}

async function configureChat(page) {
  const response = await page.context().request.put("/api/ai/settings", {
    headers: { "X-CSRF-Token": await csrf(page) },
    data: {
      mode: "custom", baseUrl: "https://models.example/v1",
      apiKey: "function-model-key", model: "function-model",
    },
  });
  expect(response.ok()).toBe(true);
}

async function openChat(page, caseId) {
  await page.goto(`/#/workbench/${caseId}`);
  await expect(page.getByLabel("案例标题")).toBeVisible();
  await page.locator(".workspace-actions").getByRole("button", { name: "AI" }).click();
  await expect(page.locator(".assistant-rail")).toHaveClass(/open/);
  await page.getByRole("button", { name: "对话", exact: true }).click();
  await expect(page.getByLabel("向 AI 提问")).toBeEnabled();
}

async function sendChat(page, text) {
  const streamResponse = page.waitForResponse((response) => (
    response.request().method() === "POST" && new URL(response.url()).pathname.endsWith("/stream")
  ));
  await page.getByLabel("向 AI 提问").fill(text);
  await page.getByRole("button", { name: "发送", exact: true }).click();
  await expect(page.locator(".ai-message.assistant").last()).toContainText(ANSWER, { timeout: 15000 });
  return streamMessageId(await (await streamResponse).body());
}

function streamMessageId(body) {
  const line = body.toString().split("\n").find((item) => item.startsWith('data: {"type":"start"'));
  return JSON.parse(line.slice(6)).messageId;
}

async function chatSnapshot(page, caseId) {
  const response = await page.context().request.get(`/api/cases/${caseId}/agent/thread`);
  expect(response.ok()).toBe(true);
  return response.json();
}

async function expectPersistedChat(page) {
  await expect(page.locator(".ai-message.assistant").last()).toContainText(ANSWER, { timeout: 5000 });
}

test("deterministic Chat stream persists the server-owned thread across reload", async ({ page }) => {
  await login(page);
  await configureChat(page);
  const created = await createCase(page);
  await openChat(page, created.id);
  const streamId = await sendChat(page, "当前问题");
  const snapshot = await chatSnapshot(page, created.id);
  const assistant = snapshot.messages.at(-1);
  expect(streamId).toBe(assistant.id);
  expect(assistant.id).toBe(snapshot.latestRun.assistantMessageId);
  await page.reload();
  await openChat(page, created.id);
  await expectPersistedChat(page);
});
