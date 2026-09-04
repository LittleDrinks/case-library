import { expect, test } from "@playwright/test";

const ANSWER = "隔离模型回答：已依据当前可见资源完成分析。";
const FIRST_QUESTION = "默认对话的第一个问题";
const SECOND_QUESTION = "第二个对话的问题";
const RENAMED = "资料梳理线程";

async function login(page, username = "user", password = "user123") {
  await page.goto("/#/login");
  await page.getByLabel("用户名").fill(username);
  await page.getByLabel("密码").fill(password);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page).toHaveURL(/#\/$/);
}

async function csrf(page) {
  const response = await page.context().request.get("/api/auth/session");
  return (await response.json()).csrfToken;
}

async function createCase(page, title) {
  const document = {
    type: "doc",
    content: [{ type: "paragraph", content: [{ type: "text", text: "线程测试正文" }] }],
  };
  const response = await page.context().request.post("/api/cases", {
    headers: { "X-CSRF-Token": await csrf(page) },
    data: { title, document },
  });
  expect(response.ok()).toBe(true);
  return response.json();
}

async function configureChat(page) {
  const response = await page.context().request.put("/api/ai/settings", {
    headers: { "X-CSRF-Token": await csrf(page) },
    data: {
      mode: "custom", baseUrl: "http://ai-provider:8080/v1",
      apiKey: "e2e-api-key", model: "e2e-model-a",
    },
  });
  expect(response.ok()).toBe(true);
}

async function openChat(page, caseId) {
  await page.goto(`/#/workbench/${caseId}`);
  await expect(page.getByLabel("案例标题")).toBeVisible();
  await page.locator(".workspace-actions").getByRole("button", { name: "AI" }).click();
  await expect(page.locator(".assistant-rail")).toHaveClass(/open/);
  await expect(page.getByLabel("向 AI 提问")).toBeEnabled();
}

async function sendChat(page, text) {
  await page.getByLabel("向 AI 提问").fill(text);
  await page.getByRole("button", { name: "发送", exact: true }).click();
  const assistant = page.locator(".ai-message.assistant").last();
  await expect(assistant).toContainText(ANSWER, { timeout: 15000 });
}

async function threadList(page, caseId) {
  const response = await page.context().request.get(`/api/cases/${caseId}/agent/threads`);
  expect(response.ok()).toBe(true);
  return response.json();
}

async function threadSnapshot(page, caseId, threadId) {
  const response = await page.context().request.get(
    `/api/cases/${caseId}/agent/threads/${threadId}`,
  );
  expect(response.ok()).toBe(true);
  return response.json();
}

async function openThreadList(page) {
  await page.getByTestId("agent-thread-list-open").click();
  await expect(page.getByTestId("agent-thread-list")).toBeVisible();
}

async function renameCurrentRow(page, title) {
  await page.getByTestId("agent-thread-rename").first().click();
  await page.getByTestId("agent-thread-rename-input").fill(title);
  await page.getByTestId("agent-thread-rename-confirm").click();
  await expect(page.getByTestId("agent-thread-open").first()).toContainText(title);
}

function userTexts(snapshot) {
  return snapshot.messages
    .filter((message) => message.role === "user")
    .map((message) => message.parts.find((part) => part.type === "text")?.text);
}

async function assertIsolatedViaApi(page, caseId) {
  const list = await threadList(page, caseId);
  expect(list).toHaveLength(2);
  const first = await threadSnapshot(page, caseId, list.find((row) => row.isDefault).id);
  const second = await threadSnapshot(page, caseId, list.find((row) => !row.isDefault).id);
  expect(userTexts(first)).toEqual([FIRST_QUESTION]);
  expect(userTexts(second)).toEqual([SECOND_QUESTION]);
  expect(second.title).toBe(RENAMED);
  expect(first.latestRun.id).not.toBe(second.latestRun.id);
}

async function assertCrossCaseHidden(page, caseId, threadId) {
  const other = await createCase(page, `Other ${Date.now()}`);
  const response = await page.context().request.get(
    `/api/cases/${other.id}/agent/threads/${threadId}`,
  );
  expect(response.status()).toBe(404);
}

async function seedTwoThreads(page) {
  await login(page);
  await configureChat(page);
  const created = await createCase(page, `Threads ${Date.now()}`);
  await openChat(page, created.id);
  await sendChat(page, FIRST_QUESTION);
  await expect(page.getByTestId("agent-thread-list-open")).toContainText(FIRST_QUESTION);
  await openThreadList(page);
  await expect(page.getByTestId("agent-thread-open")).toHaveCount(1);
  await page.getByTestId("agent-thread-create").click();
  await expect(page.getByLabel("向 AI 提问")).toBeEnabled();
  await expect(page.locator(".ai-message")).toHaveCount(0);
  await expect(page.getByTestId("agent-thread-list-open")).toContainText("未命名对话");
  await sendChat(page, SECOND_QUESTION);
  return created;
}

async function renameAndSwitchBack(page) {
  await openThreadList(page);
  await expect(page.getByTestId("agent-thread-open")).toHaveCount(2);
  await renameCurrentRow(page, RENAMED);
  await page.getByTestId("agent-thread-open").filter({ hasText: FIRST_QUESTION }).click();
  await expect(page.locator(".ai-message.user")).toContainText(FIRST_QUESTION);
  await expect(page.locator(".agent-chat-panel")).not.toContainText(SECOND_QUESTION);
}

async function reloadRestoresLastThread(page, caseId) {
  await page.reload();
  await openChat(page, caseId);
  await expect(page.getByTestId("agent-thread-list-open")).toContainText(FIRST_QUESTION);
  await expect(page.locator(".ai-message.user")).toContainText(FIRST_QUESTION);
}

async function assertCrossUserBlocked(page, caseId) {
  const adminContext = await page.context().browser().newContext();
  const loginResponse = await adminContext.request.post("/api/auth/login", {
    data: { username: "admin", password: "admin123" },
  });
  expect(loginResponse.ok()).toBe(true);
  const list = await adminContext.request.get(`/api/cases/${caseId}/agent/threads`);
  expect(list.status()).toBe(403);
  await adminContext.close();
}

test("命名 Thread：创建、重命名、切换、刷新恢复、跨用户阻断与状态隔离", async ({ page }) => {
  const created = await seedTwoThreads(page);
  await renameAndSwitchBack(page);
  await assertIsolatedViaApi(page, created.id);
  const [firstRow] = await threadList(page, created.id);
  await assertCrossCaseHidden(page, created.id, firstRow.id);
  await reloadRestoresLastThread(page, created.id);
  await assertCrossUserBlocked(page, created.id);
});
