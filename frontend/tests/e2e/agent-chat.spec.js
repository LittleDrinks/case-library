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

async function browserChatProjection(page) {
  const messages = await page.locator(".agent-chat-panel .ai-message").evaluateAll((items) => (
    items.map((item) => ({
      role: item.classList.contains("user") ? "user" : "assistant",
      text: item.querySelector("p")?.textContent || "",
    }))
  ));
  const panel = page.locator(".agent-chat-panel");
  return {
    messages,
    run: {
      eventSeq: await panel.getAttribute("data-event-seq"),
      id: await panel.getAttribute("data-run-id"),
      status: await panel.getAttribute("data-run-status"),
      busy: await page.locator(".ai-status").getAttribute("aria-busy"),
    },
  };
}

async function reloadAndAssertChat(page, caseId, persisted) {
  await page.reload();
  await openChat(page, caseId);
  await expectPersistedChat(page);
  await expect.poll(() => browserChatProjection(page)).toEqual({
    messages: persisted.messages.map((message) => ({
      role: message.role,
      text: message.parts.filter((part) => part.type === "text").map((part) => part.text).join(""),
    })),
    run: {
      eventSeq: String(persisted.eventSeq),
      id: persisted.latestRun.id,
      status: persisted.latestRun.status,
      busy: "false",
    },
  });
  await expect.poll(() => chatSnapshot(page, caseId)).toMatchObject(persisted);
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
  expect(snapshot.eventSeq).toBe(4);
  const persisted = {
    messages: snapshot.messages,
    latestRun: snapshot.latestRun,
    eventSeq: snapshot.eventSeq,
  };
  await reloadAndAssertChat(page, created.id, persisted);
});
