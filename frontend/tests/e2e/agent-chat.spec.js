import { expect, test } from "@playwright/test";

const ANSWER = "隔离模型回答：已依据当前可见资源完成分析。";
const PROVIDER_BASE_URL = process.env.E2E_PROVIDER_BASE_URL || "http://ai-provider:8080/v1";

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
      mode: "custom", baseUrl: PROVIDER_BASE_URL,
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
  const streamResponse = page.waitForResponse((response) => (
    response.request().method() === "POST" && new URL(response.url()).pathname.endsWith("/stream")
  ));
  await page.getByLabel("向 AI 提问").fill(text);
  await page.getByRole("button", { name: "发送", exact: true }).click();
  await expect(page.locator(".ai-message.assistant").last()).toContainText(ANSWER, { timeout: 15000 });
  await streamResponse;
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

function projectionOf(persisted) {
  return {
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
  };
}

async function expectProjectionMatches(page, caseId) {
  const persisted = await chatSnapshot(page, caseId);
  await expect.poll(() => browserChatProjection(page)).toEqual(projectionOf(persisted));
  return persisted;
}

async function expectCompletedProjection(page, caseId) {
  await expectPersistedChat(page);
  await expect.poll(async () => (await chatSnapshot(page, caseId)).latestRun.status)
    .toBe("completed");
  return expectProjectionMatches(page, caseId);
}

async function reloadAndAssertChat(page, caseId, persisted) {
  await page.reload();
  await openChat(page, caseId);
  await expectPersistedChat(page);
  await expect.poll(() => browserChatProjection(page)).toEqual(projectionOf(persisted));
  await expect.poll(() => chatSnapshot(page, caseId)).toMatchObject(persisted);
}

async function assertSavedAiVersion(page, caseId) {
  const history = await (await page.context().request.get(`/api/cases/${caseId}/history`)).json();
  expect(history.versions).toHaveLength(1);
  expect(history.versions[0].kind).toBe("ai");
  const snapshot = await chatSnapshot(page, caseId);
  const tool = snapshot.messages.flatMap((message) => message.parts)
    .find((part) => part.type === "tool-propose_document");
  expect(tool.output.status).toBe("created");
  expect(tool.output.versionId).toBe(history.versions[0].id);
  expect(snapshot.artifacts).toEqual([]);
  return history.versions[0];
}

async function openAiVersion(page, version) {
  await page.getByLabel("版本历史").click();
  await expect(page.getByText(`AI版本 v${version.number} · ${version.title}`)).toBeVisible();
  await page.getByRole("button", { name: `查看历史版本 AI版本 v${version.number} · ${version.title}` }).click();
  await expect(page.getByText(`AI生成版本 v${version.number} · 只读`)).toBeVisible();
  await expect(page.locator(".version-paper .canvas-editor")).toHaveAttribute("contenteditable", "false");
}

async function overwriteAiVersion(page, version) {
  await page.locator(".version-paper-actions .version-restore").click();
  await expect(page.locator(".overwrite-warning")).toContainText(`AI版本 v${version.number} · ${version.title}`);
  await page.getByRole("button", { name: "确认恢复", exact: true }).click();
  await expect(page.getByLabel("案例标题")).toHaveValue(version.title);
  await expect(page.locator(".canvas-editor").first()).toContainText("AI生成正文");
}

test("deterministic Chat stream persists the server-owned thread across reload", async ({ page }) => {
  await login(page);
  await configureChat(page);
  const created = await createCase(page);
  await openChat(page, created.id);
  await sendChat(page, "当前问题");
  const snapshot = await expectCompletedProjection(page, created.id);
  const assistant = snapshot.messages.at(-1);
  expect(assistant.id).toBe(snapshot.latestRun.assistantMessageId);
  expect(snapshot.eventSeq).toBe(4);
  const persisted = {
    messages: snapshot.messages,
    latestRun: snapshot.latestRun,
    eventSeq: snapshot.eventSeq,
  };
  await reloadAndAssertChat(page, created.id, persisted);
});

test("完整生成通过真实 Run 保存 AI 版本并可只读打开、恢复和刷新", async ({ page }) => {
  await login(page);
  await configureChat(page);
  const created = await createCase(page);
  await openChat(page, created.id);
  await sendChat(page, "请完整生成全文");
  const version = await assertSavedAiVersion(page, created.id);
  await openAiVersion(page, version);
  await overwriteAiVersion(page, version);
  await page.reload();
  await expect(page.getByLabel("案例标题")).toHaveValue(version.title);
  const history = await (await page.context().request.get(`/api/cases/${created.id}/history`)).json();
  expect(history.versions[0].id).toBe(version.id);
});

async function selectDraftRange(page, text) {
  const target = page.locator(".canvas-editor p", { hasText: text }).first();
  await expect(target).toBeVisible();
  await target.selectText();
  await expect.poll(() => page.evaluate(() => window.getSelection()?.toString() || ""))
    .toContain(text);
}

async function undoCount(page) {
  return page.getByTestId("agent-undo-write").count();
}

async function unauthorizedWriteKeepsDraft(page, created) {
  await selectDraftRange(page, "AI生成正文");
  await sendChat(page, "帮我把这段话写入正文试试");
  await expect(page.locator(".canvas-editor").first()).toContainText("AI生成正文");
  expect(await undoCount(page)).toBe(0);
  const history = await (await page.context().request.get(`/api/cases/${created.id}/history`)).json();
  expect(history.versions).toHaveLength(1);
  return history;
}

async function authorizedWriteAndUndo(page, created, version) {
  await selectDraftRange(page, "AI生成正文");
  await sendChat(page, "请直接写入替换选中文字");
  await expect(page.locator(".canvas-editor").first()).toContainText("直接写入替换的新正文");
  await expect(page.getByTestId("agent-undo-write")).toBeVisible();
  await page.getByTestId("agent-undo-write").click();
  await expect(page.getByTestId("agent-write-undone")).toBeVisible();
  await expect(page.locator(".canvas-editor").first()).toContainText("AI生成正文");
  const history = await (await page.context().request.get(`/api/cases/${created.id}/history`)).json();
  expect(history.versions).toHaveLength(1);
  expect(history.versions[0].id).toBe(version.id);
  expect(history.versions[0].kind).toBe("ai");
}

test("显式直接写入需授权且撤销保留独立 AI 版本", async ({ page }) => {
  await login(page);
  await configureChat(page);
  const created = await createCase(page);
  await openChat(page, created.id);
  await sendChat(page, "请完整生成全文");
  const version = await assertSavedAiVersion(page, created.id);
  await openAiVersion(page, version);
  await overwriteAiVersion(page, version);
  await page.reload();
  await expect(page.getByLabel("案例标题")).toHaveValue(version.title);

  await unauthorizedWriteKeepsDraft(page, created);
  await authorizedWriteAndUndo(page, created, version);
});

async function submitMessage(page, text) {
  await page.getByLabel("向 AI 提问").fill(text);
  await page.getByRole("button", { name: "发送", exact: true }).click();
}

async function sendAndWaitActive(page, caseId, text) {
  const streamResponse = page.waitForResponse((response) => (
    response.request().method() === "POST" && new URL(response.url()).pathname.endsWith("/stream")
  ));
  await submitMessage(page, text);
  await streamResponse;
  await expect.poll(async () => (await chatSnapshot(page, caseId)).activeRun).toBeTruthy();
}

test("stop command cancels the active run without waiting for the provider", async ({ page }) => {
  await login(page);
  await configureChat(page);
  const created = await createCase(page);
  await openChat(page, created.id);
  await sendAndWaitActive(page, created.id, "取消测试");
  const cancelResponse = page.waitForResponse((response) => (
    response.request().method() === "POST" && response.url().includes("/cancel")
  ));
  await page.getByTestId("agent-stop").click();
  expect((await cancelResponse).status()).toBe(200);
  await expect.poll(async () => (await chatSnapshot(page, created.id)).latestRun?.status)
    .toBe("cancelled");
  await expect(page.getByTestId("agent-run-status")).toContainText("运行已取消");
  await expect(page.getByTestId("agent-stop")).toHaveCount(0);
  await expect(page.getByLabel("向 AI 提问")).toBeEnabled();
});

test("failed message can be retried as a new run that references the original", async ({ page }) => {
  await login(page);
  await configureChat(page);
  const created = await createCase(page);
  await openChat(page, created.id);
  const text = "重试测试这条消息第一次会失败";
  await submitMessage(page, text);
  await expect.poll(async () => (await chatSnapshot(page, created.id)).latestRun?.status)
    .toBe("failed");
  await expect(page.getByTestId("agent-run-status").getByRole("alert")).toBeVisible();
  await page.getByTestId("agent-retry").click();
  const persisted = await expectCompletedProjection(page, created.id);
  const users = persisted.messages.filter((message) => message.role === "user");
  expect(users.map((message) => message.parts[0].text)).toEqual([text]);
  expect(persisted.latestRun.userMessageId).toBe(users[0].id);
  expect(persisted.latestRun.status).toBe("completed");
});

test("page refresh mid-run resumes the server-owned run to terminal", async ({ page }) => {
  await login(page);
  await configureChat(page);
  const created = await createCase(page);
  await openChat(page, created.id);
  await sendAndWaitActive(page, created.id, "慢速测试");
  await page.reload();
  await openChat(page, created.id);
  const persisted = await expectCompletedProjection(page, created.id);
  expect(persisted.activeRun).toBeNull();
  await expect.poll(() => browserChatProjection(page)).toMatchObject({
    messages: [{ role: "user" }, { role: "assistant", text: ANSWER }],
    run: { status: "completed", busy: "false" },
  });
});

test("connection loss mid-run recovers through the same transport without duplication", async ({ page }) => {
  await login(page);
  await configureChat(page);
  const created = await createCase(page);
  await openChat(page, created.id);
  await sendAndWaitActive(page, created.id, "慢速测试");
  // Aborts the browser-side stream only; the server keeps executing the run.
  await page.evaluate(() => window.stop());
  await page.evaluate(() => window.dispatchEvent(new Event("online")));
  const persisted = await expectCompletedProjection(page, created.id);
  expect(persisted.activeRun).toBeNull();
});
