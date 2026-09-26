import { expect, test } from "@playwright/test";
import { getSchema } from "@tiptap/core";
import StarterKit from "@tiptap/starter-kit";
import { Transform } from "@tiptap/pm/transform";

const ANSWER = "隔离模型回答：已依据当前可见资源完成分析。";
const ORIGINAL_TEXT = "当前案例测试正文";
const PROPOSED_TEXT = "通过建议应用的新正文";
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

function paragraphBlock(text) {
  return { type: "paragraph", content: [{ type: "text", text }] };
}

async function createCase(page, text = ORIGINAL_TEXT) {
  const response = await page.context().request.post("/api/cases", {
    headers: { "X-CSRF-Token": await csrf(page) },
    data: {
      title: `Chat seam ${Date.now()}`,
      document: caseDocument(text),
    },
  });
  expect(response.ok()).toBe(true);
  return response.json();
}

async function createBlankCase(page) {
  const response = await page.context().request.post("/api/cases", {
    headers: { "X-CSRF-Token": await csrf(page) },
    data: {
      title: `Blank draft seam ${Date.now()}`,
      document: { type: "doc", content: [] },
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
  await openChatPanel(page);
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

async function sendGenerationAndWaitForPersistence(page, caseId, text) {
  const streamResponse = page.waitForResponse((response) => (
    response.request().method() === "POST" && new URL(response.url()).pathname.endsWith("/stream")
  ));
  await page.getByLabel("向 AI 提问").fill(text);
  await page.getByRole("button", { name: "发送", exact: true }).click();
  await streamResponse;
  await expect.poll(async () => {
    const snapshot = await chatSnapshot(page, caseId);
    const persistedAnswer = snapshot.messages.some((message) => (
      message.role === "assistant"
      && message.parts.some((part) => part.type === "text" && part.text?.includes(ANSWER))
    ));
    return { activeRun: snapshot.activeRun, status: snapshot.latestRun?.status, persistedAnswer };
  }, { timeout: 15_000 }).toEqual({ activeRun: null, status: "completed", persistedAnswer: true });
}

async function openChatPanel(page) {
  if (!await page.getByLabel("向 AI 提问").isVisible()) {
    await page.locator(".assistant-tabs").getByRole("button", { name: "AI", exact: true }).click();
  }
  await expect(page.locator(".assistant-rail")).not.toHaveClass(/collapsed/);
  await expect(page.getByLabel("向 AI 提问")).toBeEnabled();
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

async function caseRecord(page, caseId) {
  const response = await page.context().request.get(`/api/cases/${caseId}`);
  expect(response.ok()).toBe(true);
  return response.json();
}

async function caseHistory(page, caseId) {
  const response = await page.context().request.get(`/api/cases/${caseId}/history`);
  expect(response.ok()).toBe(true);
  return response.json();
}

function documentText(value) {
  if (!value || typeof value !== "object") return "";
  return `${value.text || ""}${(value.content || []).map(documentText).join("")}`;
}

function versionIdentity(history) {
  return history.versions.map(({ id, number, kind }) => ({ id, number, kind }));
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

test("空白稿整篇初稿由真实 Run 写入当前稿并可撤销", async ({ page }) => {
  await login(page);
  await configureChat(page);
  const created = await createBlankCase(page);
  await openChat(page, created.id);
  await sendGenerationAndWaitForPersistence(page, created.id, "请完整生成全文");
  const snapshot = await chatSnapshot(page, created.id);
  const write = snapshot.messages.flatMap((message) => message.parts)
    .find((part) => part.type === "tool-write_document");
  expect(write.input).not.toHaveProperty("scope");
  expect(write.output.status).toBe("written");
  expect(write.output.versionStatus).toBe("created");
  expect(snapshot.artifacts).toEqual([]);
  await expect(page.locator(".canvas-editor").first()).toContainText("AI生成正文");
  const historyAfterWrite = await caseHistory(page, created.id);
  expect(historyAfterWrite.versions).toHaveLength(1);
  expect(historyAfterWrite.versions[0]).toMatchObject({ id: write.output.versionId, kind: "ai" });

  await page.getByRole("button", { name: "返回当前教师稿" }).click();
  await expect(page.locator(".canvas-editor").first()).toContainText("AI生成正文");
  await page.getByTestId("agent-undo-write").click();
  await expect(page.getByTestId("agent-write-undone")).toBeVisible();
  await expect.poll(async () => documentText((await caseRecord(page, created.id)).document))
    .toBe("");
  expect(versionIdentity(await caseHistory(page, created.id)))
    .toEqual(versionIdentity(historyAfterWrite));
});

async function selectDraftRange(page, text) {
  const target = page.locator(".canvas-editor p", { hasText: text }).first();
  await expect(target).toBeVisible();
  await target.selectText();
  await expect.poll(() => page.evaluate(() => window.getSelection()?.toString() || ""))
    .toContain(text);
}

async function waitSelectionAttached(page, quote) {
  const chip = page.getByTestId("composer-selection");
  await expect(chip).toBeVisible();
  await expect(chip).toHaveAttribute("title", quote);
}

async function proposeRevisionApplyAndUndo(page, created, message, selected) {
  if (selected) {
    await selectDraftRange(page, ORIGINAL_TEXT);
    await waitSelectionAttached(page, ORIGINAL_TEXT);
  }
  await sendChat(page, message);
  const snapshot = await chatSnapshot(page, created.id);
  const revision = snapshot.messages.flatMap((item) => item.parts)
    .find((part) => part.type === "tool-propose_revision");
  expect(revision, "已有正文修改必须先生成修订建议").toBeDefined();
  expect(revision.input).toMatchObject({
    start: 1,
    end: ORIGINAL_TEXT.length + 1,
    replacement: PROPOSED_TEXT,
  });
  expect(revision.input.reason).toBeTruthy();
  expect(snapshot.messages.flatMap((item) => item.parts).map((part) => part.type))
    .not.toContain("tool-write_document");
  expect(snapshot.messages.flatMap((item) => item.parts).map((part) => part.type))
    .not.toContain("tool-propose_document");
  const artifact = snapshot.artifacts.find(({ id }) => id === revision.output.artifactId);
  expect(artifact).toMatchObject({
    status: "pending",
    target: { quote: ORIGINAL_TEXT },
    replacement: PROPOSED_TEXT,
  });

  const card = page.locator(
    `[data-testid="revision-suggestion"][data-artifact-id="${revision.output.artifactId}"]`,
  );
  await expect(card).toHaveAttribute("data-artifact-status", "pending");
  await expect(page.locator(".canvas-editor").first()).toContainText(ORIGINAL_TEXT);
  await card.locator(".revision-suggestion-head").click();
  await expect(card.locator(".revision-suggestion-location")).toHaveText(ORIGINAL_TEXT);
  await expect(page.locator(".revision-preview-old").first()).toContainText(ORIGINAL_TEXT);
  await expect(page.locator(".revision-preview-new").first()).toContainText(PROPOSED_TEXT);
  await expect(page.locator(".canvas-editor").first()).toContainText(ORIGINAL_TEXT);

  await card.getByTestId("agent-accept").click();
  await expect(card).toHaveAttribute("data-artifact-status", "accepted");
  await expect.poll(async () => documentText((await caseRecord(page, created.id)).document))
    .toContain(PROPOSED_TEXT);
  const historyAfterApply = await caseHistory(page, created.id);
  expect(historyAfterApply.versions).toHaveLength(1);
  expect(historyAfterApply.versions[0].kind).toBe("ai");

  await page.getByTestId("agent-undo-revision").click();
  await expect(page.getByTestId("agent-write-undone")).toBeVisible();
  await expect.poll(async () => documentText((await caseRecord(page, created.id)).document))
    .toBe(ORIGINAL_TEXT);
  expect(versionIdentity(await caseHistory(page, created.id)))
    .toEqual(versionIdentity(historyAfterApply));
}

for (const scenario of [
  { message: "帮我把这段话写入正文试试", selected: false },
  { message: "请为选中文字提出修改建议", selected: true },
]) {
  test(`已有正文请求「${scenario.message}」先预览修订，应用后可撤销`, async ({ page }) => {
    await login(page);
    await configureChat(page);
    const created = await createCase(page);
    await openChat(page, created.id);
    await proposeRevisionApplyAndUndo(page, created, scenario.message, scenario.selected);
  });
}

test("历史建议遇到重复替换正文时明确提示无法定位", async ({ page }) => {
  await login(page);
  await configureChat(page);
  const created = await createCase(page);
  await openChat(page, created.id);
  await sendChat(page, "请直接修改并给出长理由");
  const snapshot = await chatSnapshot(page, created.id);
  const revision = snapshot.messages.flatMap((item) => item.parts)
    .find((part) => part.type === "tool-propose_revision");
  const card = page.locator(
    `[data-testid="revision-suggestion"][data-artifact-id="${revision.output.artifactId}"]`,
  );
  await card.locator(".revision-suggestion-head").click();
  await card.getByTestId("agent-accept").click();
  await expect(card).toHaveAttribute("data-artifact-status", "accepted");

  const current = await caseRecord(page, created.id);
  const schema = getSchema([StarterKit]);
  const transform = new Transform(schema.nodeFromJSON(current.document));
  transform.insert(0, [
    schema.nodeFromJSON(paragraphBlock(PROPOSED_TEXT)),
    schema.nodeFromJSON(paragraphBlock("插入的间隔段落")),
  ]);
  const response = await page.context().request.patch(`/api/cases/${created.id}`, {
    headers: { "X-CSRF-Token": await csrf(page) },
    data: {
      revision: current.revision,
      document: transform.doc.toJSON(),
      steps: transform.steps.map((step) => step.toJSON()),
    },
  });
  expect(response.ok()).toBe(true);
  await page.reload();
  await openChatPanel(page);
  const historicalCard = page.locator(
    `[data-testid="revision-suggestion"][data-artifact-id="${revision.output.artifactId}"]`,
  );
  await page.evaluate(() => {
    window.historicalParagraphScrolls = [];
    const original = Element.prototype.scrollIntoView;
    Element.prototype.scrollIntoView = function scrollIntoView(options) {
      if (this.matches(".canvas-editor p")) window.historicalParagraphScrolls.push(this.textContent);
      return original.call(this, options);
    };
  });

  await historicalCard.locator(".revision-suggestion-head").click();
  await expect(historicalCard.getByRole("alert"))
    .toContainText("正文中没有唯一匹配位置，无法定位这条历史建议");
  expect(await page.evaluate(() => window.historicalParagraphScrolls)).toEqual([]);
});

test("长建议理由可在卡片内滚动到底部使用修改操作", async ({ page }) => {
  await login(page);
  await configureChat(page);
  const created = await createCase(page);
  await openChat(page, created.id);
  await sendChat(page, "请直接修改并给出长理由");
  await expect.poll(async () => (await chatSnapshot(page, created.id)).latestRun?.status)
    .toBe("completed");

  const snapshot = await chatSnapshot(page, created.id);
  const revision = snapshot.messages.flatMap((item) => item.parts)
    .find((part) => part.type === "tool-propose_revision");
  const card = page.locator(
    `[data-testid="revision-suggestion"][data-artifact-id="${revision.output.artifactId}"]`,
  );
  await card.locator(".revision-suggestion-head").click();

  const details = card.locator(".revision-suggestion-details");
  const scroll = await details.evaluate((element) => {
    element.scrollTop = element.scrollHeight;
    const button = element.querySelector('[data-testid="agent-accept"]');
    const container = element.getBoundingClientRect();
    const action = button.getBoundingClientRect();
    return {
      scrollHeight: element.scrollHeight,
      clientHeight: element.clientHeight,
      overflowY: getComputedStyle(element).overflowY,
      actionTop: action.top,
      actionBottom: action.bottom,
      containerTop: container.top,
      containerBottom: container.bottom,
    };
  });
  expect(scroll.scrollHeight).toBeGreaterThan(scroll.clientHeight);
  expect(scroll.overflowY).toBe("auto");
  expect(scroll.actionTop).toBeGreaterThanOrEqual(scroll.containerTop);
  expect(scroll.actionBottom).toBeLessThanOrEqual(scroll.containerBottom);

  await card.getByTestId("agent-accept").click();
  await expect(card).toHaveAttribute("data-artifact-status", "accepted");
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
