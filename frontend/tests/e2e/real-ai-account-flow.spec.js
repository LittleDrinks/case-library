import { randomUUID } from "node:crypto";
import { chmodSync, mkdirSync, readFileSync, renameSync, writeFileSync } from "node:fs";
import { dirname } from "node:path";
import { expect, test } from "@playwright/test";
import { openAiTab } from "./agent-panel.js";

const STAGES = [
  "signup_login",
  "private_draft",
  "personal_ai_settings",
  "provider_generation",
  "run_history",
  "private_access",
  "admin_review_publish",
  "anonymous_public_read",
];

function reportState() {
  return {
    sourceHash: process.env.REAL_AI_SOURCE_HASH || null,
    runtimeBuild: {
      appImageId: process.env.REAL_AI_APP_IMAGE_ID || null,
      testImageId: process.env.REAL_AI_TEST_IMAGE_ID || null,
      frontendImageId: process.env.REAL_AI_FRONTEND_IMAGE_ID || null,
      backendTestImageId: process.env.REAL_AI_BACKEND_TEST_IMAGE_ID || null,
      appSourceHash: process.env.REAL_AI_APP_SOURCE_HASH || null,
      testSourceHash: process.env.REAL_AI_TEST_SOURCE_HASH || null,
      frontendDistHash: process.env.REAL_AI_FRONTEND_DIST_HASH || null,
      buildManifestHash: process.env.REAL_AI_BUILD_MANIFEST_HASH || null,
    },
    syntheticIds: { userId: null, caseId: null, threadId: null, runId: null },
    cleanupIdentity: null,
    model: null,
    resultSummary: { providerResponseCharacters: null },
    runStatus: null,
    permissions: {
      campusVerified: null,
      privateDraftAnonymousStatus: null,
      publishedAnonymousStatus: null,
    },
    verified: [],
    failed: [],
    notRun: [...STAGES],
    testStatus: "not_run",
    cleanup: "pending_scoped_cleanup",
  };
}

function saveReport(report) {
  const reportPath = process.env.REAL_AI_REPORT_PATH;
  if (!reportPath) throw new Error("REAL_AI_REPORT_PATH_REQUIRED");
  mkdirSync(dirname(reportPath), { recursive: true, mode: 0o700 });
  const temporaryPath = `${reportPath}.tmp`;
  writeFileSync(temporaryPath, JSON.stringify(report, null, 2), { mode: 0o600 });
  chmodSync(temporaryPath, 0o600);
  renameSync(temporaryPath, reportPath);
}

function readAdminCredentials() {
  const credentials = JSON.parse(
    readFileSync("/run/secrets/real_ai_admin_credentials", "utf8"),
  );
  if (
    typeof credentials.username !== "string" || !credentials.username.trim()
    || typeof credentials.password !== "string" || !credentials.password
  ) {
    throw new Error("REAL_AI_ADMIN_CREDENTIALS_INVALID");
  }
  return credentials;
}

async function login(page, username, password) {
  await page.goto("/#/login");
  await page.getByLabel("用户名").fill(username);
  await page.getByLabel("密码").fill(password);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page).not.toHaveURL(/#\/login(?:\?|$)/);
}

async function session(page) {
  const response = await page.context().request.get("/api/auth/session");
  expect(response.ok()).toBe(true);
  return response.json();
}

async function publicCase(page, caseId) {
  return page.context().request.get(`/api/cases/${encodeURIComponent(caseId)}`);
}

function chooseModel(modelIds, preferred) {
  const chatCandidate = (model) => (
    !/(^|[-_])(r1|reasoner|reasoning|think)([-_]|$)/i.test(model)
    && /(deepseek-v3|qwen.*(plus|max)|gpt|chat)/i.test(model)
  );
  return modelIds.find((model) => model.toLowerCase() === preferred.toLowerCase())
    || modelIds.find(chatCandidate)
    || null;
}

function safeFailureCode(error) {
  if (error?.name === "TimeoutError") return "timeout";
  if (error?.name === "AssertionError") return "assertion_failed";
  return "operation_failed";
}

test("普通账号使用个人真实 AI 完成私稿、审核发布和匿名阅读", async ({ page, browser }) => {
  test.setTimeout(180_000);
  const report = reportState();
  let currentStage = STAGES[0];

  try {
    saveReport(report);
    const username = `realai361-${randomUUID()}`;
    const password = `Aa1!${randomUUID()}Z`;
    report.cleanupIdentity = { username };
    saveReport(report);
    await page.goto("/#/register");
    await page.getByLabel("用户名").fill(username);
    await page.getByLabel("密码").fill(password);
    const registrationResponse = page.waitForResponse((response) => (
      response.request().method() === "POST"
      && new URL(response.url()).pathname === "/api/auth/register"
    ));
    await page.getByRole("button", { name: "创建账号", exact: true }).click();
    const registeredUser = await (await registrationResponse).json();
    report.syntheticIds.userId = registeredUser.id;
    saveReport(report);
    await expect(page).toHaveURL(/#\/login/);
    await expect(page.getByRole("status")).toContainText("账号创建成功");
    await login(page, username, password);
    const signedIn = await session(page);
    expect(signedIn.user.role).toBe("user");
    expect(signedIn.user.campusVerified).toBe(false);
    expect(signedIn.user.id).toBe(registeredUser.id);
    report.permissions.campusVerified = false;
    report.verified.push(currentStage);
    report.notRun.shift();

    currentStage = STAGES[1];
    await page.goto("/#/my-cases");
    const createCaseResponse = page.waitForResponse((response) => (
      response.request().method() === "POST"
      && new URL(response.url()).pathname === "/api/cases"
    ));
    await page.getByRole("button", { name: "新建案例" }).click();
    const createdCase = await (await createCaseResponse).json();
    report.syntheticIds.caseId = createdCase.id;
    saveReport(report);
    await expect(page).toHaveURL(/#\/workbench\//);
    const caseId = new URL(page.url()).hash.split("/").at(-1);
    expect(caseId).toBe(createdCase.id);
    const title = `合成 AI 教学草稿 ${randomUUID().slice(0, 8)}`;
    const body = `合成材料说明：普通账号围绕公共主题整理教学案例，流程编号 ${randomUUID().slice(0, 8)}。`;
    await page.getByLabel("案例标题").fill(title);
    await page.locator(".ProseMirror").fill(body);
    await expect(page.locator(".save-state")).toHaveText("已保存", { timeout: 15_000 });
    const savedDraftResponse = await page.context().request.get(`/api/cases/${encodeURIComponent(caseId)}`);
    expect(savedDraftResponse.ok()).toBe(true);
    const savedDraft = await savedDraftResponse.json();
    expect(savedDraft).toMatchObject({
      id: caseId,
      ownerId: signedIn.user.id,
      title,
      workflowStatus: "draft",
      publicationStatus: "none",
    });
    const anonymous = await browser.newContext({
      baseURL: process.env.PLAYWRIGHT_BASE_URL,
    });
    const privateResponse = await anonymous.request.get(`/api/cases/${encodeURIComponent(caseId)}`);
    expect(privateResponse.status()).toBe(404);
    report.permissions.privateDraftAnonymousStatus = privateResponse.status();
    report.verified.push(currentStage);
    report.notRun.shift();

    currentStage = STAGES[2];
    const automaticSettingsResponse = await page.context().request.get("/api/ai/settings");
    expect(automaticSettingsResponse.ok()).toBe(true);
    expect(await automaticSettingsResponse.json()).toMatchObject({
      mode: "automatic",
      configured: false,
      effectiveModel: null,
    });
    await page.getByRole("link", { name: "AI 模型设置" }).click();
    await page.getByLabel("自定义模型服务").check();
    await page.getByLabel("Base URL").fill(process.env.REAL_AI_PROVIDER_BASE_URL);
    const apiKey = readFileSync("/run/secrets/real_ai_provider_key", "utf8").trim();
    expect(apiKey.length).toBeGreaterThan(0);
    await page.getByLabel("API Key").fill(apiKey);
    await page.getByRole("button", { name: "获取可用模型" }).click();
    const models = page.getByLabel("可用模型");
    await expect(models.locator("option").first()).toBeAttached({ timeout: 30_000 });
    const modelIds = await models.locator("option").evaluateAll((options) => (
      options.map((option) => option.value).filter(Boolean)
    ));
    const selectedModel = chooseModel(
      modelIds,
      process.env.REAL_AI_PREFERRED_MODEL || "deepseek-v3",
    );
    expect(selectedModel).not.toBeNull();
    await models.selectOption(selectedModel);
    await page.getByRole("button", { name: "保存个人设置" }).click();
    await expect(page.getByRole("status")).toContainText("个人 AI 设置已保存");
    const savedSettingsResponse = await page.context().request.get("/api/ai/settings");
    expect(savedSettingsResponse.ok()).toBe(true);
    expect(await savedSettingsResponse.json()).toMatchObject({
      mode: "custom",
      configured: true,
      hasApiKey: true,
      effectiveSource: "custom",
      effectiveModel: selectedModel,
    });
    report.model = selectedModel;
    report.verified.push(currentStage);
    report.notRun.shift();

    currentStage = STAGES[3];
    await page.goto(`/#/workbench/${encodeURIComponent(caseId)}`);
    await openAiTab(page);
    const question = "请根据当前草稿，简要概括它的教学主题和课堂用途。";
    await page.getByLabel("向 AI 提问").fill(question);
    const streamResponse = page.waitForResponse((response) => (
      response.request().method() === "POST"
      && new URL(response.url()).pathname.endsWith("/stream")
    ));
    await page.getByRole("button", { name: "发送", exact: true }).click();
    expect((await streamResponse).ok()).toBe(true);
    const panel = page.locator(".agent-chat-panel");
    await expect(panel).toHaveAttribute("data-run-status", "completed", { timeout: 120_000 });
    const answer = page.locator(".ai-message.assistant [data-testid='agent-answer']").last();
    await expect(answer).toBeVisible();
    const answerText = (await answer.innerText()).trim();
    expect(answerText.length).toBeGreaterThan(0);
    const runId = await panel.getAttribute("data-run-id");
    expect(runId).toBeTruthy();
    const threadResponse = await page.context().request.get(`/api/cases/${encodeURIComponent(caseId)}/agent/thread`);
    expect(threadResponse.ok()).toBe(true);
    const thread = await threadResponse.json();
    expect(thread.latestRun).toMatchObject({ id: runId, status: "completed" });
    expect(thread.activeRun).toBeNull();
    expect(thread.messages.some((message) => (
      message.role === "assistant"
      && message.parts.some((part) => part.type === "text" && part.text?.trim())
    ))).toBe(true);
    report.syntheticIds.threadId = thread.id;
    report.syntheticIds.runId = runId;
    saveReport(report);
    report.resultSummary.providerResponseCharacters = answerText.length;
    report.runStatus = thread.latestRun.status;
    report.verified.push(currentStage);
    report.notRun.shift();

    currentStage = STAGES[4];
    await page.reload();
    await expect(page.locator(".agent-chat-panel")).toHaveAttribute("data-run-status", "completed", { timeout: 30_000 });
    await expect(page.locator(".ai-message.assistant [data-testid='agent-answer']").last()).toBeVisible();
    const refreshedThreadResponse = await page.context().request.get(`/api/cases/${encodeURIComponent(caseId)}/agent/thread`);
    expect(refreshedThreadResponse.ok()).toBe(true);
    const refreshedThread = await refreshedThreadResponse.json();
    expect(refreshedThread.latestRun).toMatchObject({ id: runId, status: "completed" });
    report.verified.push(currentStage);
    report.notRun.shift();

    currentStage = STAGES[5];
    const privateHistoryResponse = await anonymous.request.get(`/api/cases/${encodeURIComponent(caseId)}/history`);
    expect(privateHistoryResponse.status()).toBe(401);
    report.verified.push(currentStage);
    report.notRun.shift();

    currentStage = STAGES[6];
    await page.getByRole("button", { name: "提交审核", exact: true }).click();
    await expect(page.locator(".case-status")).toHaveText("待审");
    const frozenCaseResponse = await page.context().request.get(`/api/cases/${encodeURIComponent(caseId)}`);
    expect(frozenCaseResponse.ok()).toBe(true);
    const frozenCase = await frozenCaseResponse.json();
    expect(frozenCase.submittedVersionId).toBeTruthy();
    const adminContext = await browser.newContext({
      baseURL: process.env.PLAYWRIGHT_BASE_URL,
    });
    const adminPage = await adminContext.newPage();
    const admin = readAdminCredentials();
    await login(adminPage, admin.username, admin.password);
    await adminPage.goto(`/#/admin/review/${encodeURIComponent(caseId)}`);
    await expect(adminPage.getByLabel("案例标题")).toHaveValue(title);
    await adminPage.getByRole("button", { name: "开始审核", exact: true }).click();
    await expect(adminPage.locator(".case-status")).toHaveText("审核中");
    await adminPage.getByRole("button", { name: "通过发布", exact: true }).click();
    await expect(adminPage.locator(".case-status")).toHaveText("已发布");
    const publishedResponse = await publicCase(anonymous, caseId);
    expect(publishedResponse.ok()).toBe(true);
    const published = await publishedResponse.json();
    expect(published).toMatchObject({
      id: caseId,
      title,
      workflowStatus: "published",
      publicationStatus: "public",
      publishedVersionId: frozenCase.submittedVersionId,
    });
    report.verified.push(currentStage);
    report.notRun.shift();

    currentStage = STAGES[7];
    const readerPage = await anonymous.newPage();
    await readerPage.goto(`/#/cases/${encodeURIComponent(caseId)}`);
    await expect(readerPage.getByLabel("案例标题")).toHaveValue(title);
    await expect(readerPage.locator(".canvas-editor")).toHaveText(body);
    report.permissions.publishedAnonymousStatus = publishedResponse.status();
    report.verified.push(currentStage);
    report.notRun.shift();
    await anonymous.close();
    await adminContext.close();
    report.testStatus = "passed";
  } catch (error) {
    report.failed = [{ stage: currentStage, code: safeFailureCode(error) }];
    report.notRun = STAGES.slice(STAGES.indexOf(currentStage) + 1);
    report.testStatus = "failed";
    throw new Error(`REAL_AI_ACCOUNT_FLOW_FAILED:${currentStage}`);
  } finally {
    saveReport(report);
  }
});
