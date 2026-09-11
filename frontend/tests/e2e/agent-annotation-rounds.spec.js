import { expect, test } from "@playwright/test";
import { SKILL_ID, teachingPackage } from "./skill-package.js";
// 确定性 tracer 栈：base 29628（vite, agent-tracer-gateway 代理 /api → 29627）。

const REPLACEMENT_MARK = "修订后的段落：教学目标";
const SECOND_REPLACEMENT_MARK = "第二轮修订：教学目标";
const PROVIDER_FAILURE_MARKER = "确定性上游故障";
const SLOW_ROUND_MARKER = "确定性 A 慢速";

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

function caseDocument() {
  return {
    type: "doc",
    content: [
      { type: "paragraph", content: [{ type: "text", text: "第一段保持原样。" }] },
      { type: "paragraph", content: [{ type: "text", text: "第二段：教学目标需要更明确的评价依据。" }] },
    ],
  };
}

async function createCase(page) {
  const response = await page.context().request.post("/api/cases", {
    headers: { "X-CSRF-Token": await csrf(page) },
    data: { title: `R3 ${Date.now()}`, document: caseDocument() },
  });
  expect(response.ok()).toBe(true);
  return response.json();
}

async function publishTeachingSkill(playwright) {
  const admin = await playwright.request.newContext();
  const login = await admin.post(
    "/api/auth/login", { data: { username: "admin", password: "admin123" } },
  );
  const headers = { "X-CSRF-Token": (await login.json()).csrfToken };
  const uploaded = await admin.post("/api/admin/skills/packages", {
    headers,
    multipart: { file: { name: "skill.zip", mimeType: "application/zip", buffer: teachingPackage() } },
  });
  expect(uploaded.ok()).toBe(true);
  const { version } = await uploaded.json();
  const published = await admin.post(`/api/admin/skills/${SKILL_ID}/publish`, {
    headers, data: { versionId: version.id },
  });
  expect(published.ok()).toBe(true);
  await admin.dispose();
}

async function openChat(page, caseId) {
  await page.goto(`/#/workbench/${caseId}`);
  await expect(page.getByLabel("案例标题")).toBeVisible();
  await page.locator(".workspace-actions").getByRole("button", { name: "AI" }).click();
  await expect(page.locator(".assistant-rail")).toHaveClass(/open/);
  await expect(page.getByLabel("向 AI 提问")).toBeEnabled();
}

async function addAnnotation(page) {
  await page.getByRole("button", { name: "批注", exact: true }).click();
  await page.locator(".canvas-editor p").nth(1).selectText();
  await page.getByRole("button", { name: "添加选区批注" }).click();
  await page.getByLabel("批注内容").fill("请依据资料收紧这一段表述。");
  await page.getByRole("button", { name: "添加批注", exact: true }).click();
  await expect(page.locator(".comment-card")).toHaveCount(1);
  return (await page.context().request.get(
    `/api/cases/${await currentCaseId(page)}/annotations`,
  )).json();
}

async function addSecondAnnotation(page) {
  await page.getByRole("button", { name: "批注", exact: true }).click();
  await page.locator(".canvas-editor p").nth(0).selectText();
  await page.getByRole("button", { name: "添加选区批注" }).click();
  await page.getByLabel("批注内容").fill("请保留首段的事实边界。");
  await page.getByRole("button", { name: "添加批注", exact: true }).click();
  await expect(page.locator(".comment-card")).toHaveCount(2);
}

async function currentCaseId(page) {
  return page.url().split("/").pop();
}

async function startAnnotationRound(page, text, annotationIndex = 0) {
  await page.locator(".comment-card").nth(annotationIndex)
    .getByRole("button", { name: "让 AI 修订" }).click();
  await page.getByTestId("skill-picker-toggle").click();
  const option = page.locator(".skill-popover [data-testid='skill-option']").filter({ hasText: SKILL_ID });
  await expect(option).toHaveCount(1, { timeout: 30_000 });
  await option.first().click();
  await expect(page.getByTestId("composer-skill-block")).toContainText(SKILL_ID);
  await page.getByLabel("向 AI 提问").fill(text);
  await page.getByRole("button", { name: "发送", exact: true }).click();
}

async function configureChat(page) {
  const response = await page.context().request.put("/api/ai/settings", {
    headers: { "X-CSRF-Token": await csrf(page) },
    data: {
      mode: "custom", baseUrl: "http://127.0.0.1:29625/v1",
      apiKey: "e2e-api-key", model: "e2e-model-a",
    },
  });
  expect(response.ok()).toBe(true);
}

async function prepareAnnotation(page, playwright) {
  await publishTeachingSkill(playwright);
  await login(page);
  await configureChat(page);
  await waitSearchReady(page);
  const created = await createCase(page);
  await openChat(page, created.id);
  await addAnnotation(page);
  await addSecondAnnotation(page);
  return created;
}

async function waitSearchReady(page) {
  await expect.poll(async () => {
    const response = await page.context().request.get("/api/search?q=科学家精神&pageSize=1");
    return (await response.json()).items?.length || 0;
  }, { timeout: 90_000, intervals: [2_000] }).toBeGreaterThan(0);
}


async function listThreads(page, caseId) {
  const response = await page.context().request.get(`/api/cases/${caseId}/agent/threads`);
  expect(response.ok()).toBe(true);
  return response.json();
}

async function startSlowFirstThread(page) {
  await startAnnotationRound(page, `第一轮：${SLOW_ROUND_MARKER}候选。`);
  await expect(page.locator(".agent-chat-panel"))
    .toHaveAttribute("data-run-status", "active", { timeout: 30_000 });
  await page.getByRole("button", { name: "批注", exact: true }).click();
}

async function startSecondThread(page, caseId) {
  const before = await listThreads(page, caseId);
  await page.locator(".workspace-actions").getByRole("button", { name: "AI" }).click();
  await page.getByTestId("agent-thread-list-open").click();
  await page.getByTestId("agent-thread-create").click();
  await expect(page.getByLabel("向 AI 提问")).toBeEnabled({ timeout: 30_000 });
  await page.getByRole("button", { name: "批注", exact: true }).click();
  const annotations = await page.context().request.get(`/api/cases/${caseId}/annotations`);
  const rows = await annotations.json();
  await startAnnotationRound(page, `第二轮：请继续收紧批注 ${rows[1].id} 的候选。`, 1);
  await expect(page.locator(".agent-chat-panel"))
    .toHaveAttribute("data-run-status", "active", { timeout: 30_000 });
  await page.getByRole("button", { name: "批注", exact: true }).click();
  const after = await listThreads(page, caseId);
  return { first: before[0].id, second: after.find((item) => item.id !== before[0].id).id };
}

async function threadSnapshot(page, caseId, threadId) {
  const response = await page.context().request.get(
    `/api/cases/${caseId}/agent/threads/${threadId}`,
  );
  expect(response.ok()).toBe(true);
  return response.json();
}

async function assertSecondFinishesFirst(page, caseId, threads) {
  await expect.poll(async () => {
    const [first, second] = await Promise.all([
      threadSnapshot(page, caseId, threads.first),
      threadSnapshot(page, caseId, threads.second),
    ]);
    return { firstActive: Boolean(first.activeRun), secondActive: Boolean(second.activeRun) };
  }, { timeout: 120_000, intervals: [500] }).toEqual({ firstActive: true, secondActive: false });
}

async function assertReverseCompletion(page) {
  await expect(page.locator(".comment-card").nth(1).locator(".comment-revisions li"))
    .toHaveCount(1, { timeout: 120_000 });
  await expect(page.locator(".comment-card").nth(1).locator(".comment-revisions"))
    .toContainText(SECOND_REPLACEMENT_MARK);
  await expect(page.locator(".comment-card").nth(0).locator(".comment-revisions li"))
    .toHaveCount(1, { timeout: 120_000 });
  await expect(page.locator(".comment-card").nth(0).locator(".comment-revisions"))
    .toContainText(REPLACEMENT_MARK);
}

test("失败后重试并生成中切批注面板，新修订自动出现", async ({ page, playwright }) => {
  test.setTimeout(240_000);
  await prepareAnnotation(page, playwright);
  await startAnnotationRound(page, `${PROVIDER_FAILURE_MARKER}：先失败再重试。`);
  await expect(page.getByTestId("agent-retry"))
    .toBeVisible({ timeout: 60_000 });
  await page.getByTestId("agent-retry").click();
  await expect(page.locator(".agent-chat-panel"))
    .toHaveAttribute("data-run-status", "active", { timeout: 30_000 });
  // 生成中切批注面板：观察已由重试入口重新登记，工作台刷新不丢
  await page.getByRole("button", { name: "批注", exact: true }).click();
  await expect(page.locator(".comment-revisions li")).toHaveCount(1, { timeout: 120_000 });
  await expect(page.locator(".comment-revisions")).toContainText(REPLACEMENT_MARK);
});
test("两个线程逆序完成，各自批注历史都自动刷新且归属不串", async ({ page, playwright }) => {
  test.setTimeout(240_000);
  const created = await prepareAnnotation(page, playwright);
  await startSlowFirstThread(page);
  const threads = await startSecondThread(page, created.id);
  await assertSecondFinishesFirst(page, created.id, threads);
  await assertReverseCompletion(page);
});
