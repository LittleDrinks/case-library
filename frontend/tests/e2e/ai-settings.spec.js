import { expect, test } from "@playwright/test";

const E2E_PROVIDER = "http://ai-provider:8080/v1";
const E2E_API_KEY = "e2e-api-key";
const E2E_ANSWER = "隔离模型回答：已依据当前可见资源完成分析。";
const CANDIDATE_TEXT = "候选修订正文：教学目标、课堂任务与评价依据保持一致。";
const SECOND_CANDIDATE_TEXT = "第二条候选正文：课堂任务、评价量规与教学目标逐项对应。";

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

function candidateDocument(marker) {
  return {
    type: "doc",
    content: [
      { type: "heading", attrs: { level: 1 }, content: [{ type: "text", text: "一、教学说明" }] },
      { type: "paragraph", content: [{ type: "text", text: marker }] },
    ],
  };
}

async function createCandidateCase(page, marker) {
  const response = await page.context().request.post("/api/cases", {
    headers: { "X-CSRF-Token": await csrf(page) },
    data: { title: `候选修订 ${Date.now()}`, document: candidateDocument(marker) },
  });
  expect(response.ok()).toBe(true);
  return response.json();
}

function documentText(node) {
  if (node?.text) return node.text;
  return (node?.content || []).map(documentText).join("\n");
}

async function selectParagraph(page, marker) {
  const paragraph = page.locator(".canvas-editor p", { hasText: marker });
  await paragraph.evaluate((node) => {
    node.closest(".ProseMirror").focus();
    const range = document.createRange();
    range.selectNodeContents(node);
    const selection = window.getSelection();
    selection.removeAllRanges();
    selection.addRange(range);
    document.dispatchEvent(new Event("selectionchange", { bubbles: true }));
  });
  await expect(page.getByRole("button", { name: "改写选区" })).toBeEnabled();
}

async function requestCandidate(page, target, instruction, expected = CANDIDATE_TEXT) {
  await page.getByRole("button", { name: target }).click();
  await page.getByLabel("向 AI 提问").fill(instruction);
  await page.getByRole("button", { name: "发送", exact: true }).click();
  const candidate = page.getByRole("region", { name: "待确认修订" }).last();
  await expect(candidate).toContainText("修改理由");
  const inline = page.locator(".candidate-inline-preview").last();
  await expect(inline).toContainText(expected);
  await expect(inline).toContainText("修改理由");
  await expect(page.locator(".candidate-inline-removed").last()).toBeVisible();
  return candidate;
}

function deferred() {
  let resolve;
  const promise = new Promise((done) => { resolve = done; });
  return { promise, resolve };
}

async function holdSnapshot(page, caseId) {
  const started = deferred();
  const release = deferred();
  let count = 0;
  await page.route(`**/api/cases/${caseId}/lifecycle`, async (route) => {
    if (route.request().postDataJSON()?.command !== "snapshot") return route.continue();
    count += 1;
    started.resolve();
    await release.promise;
    await route.continue();
  });
  return { started: started.promise, release: release.resolve, count: () => count };
}

async function acceptFirstCandidate(page, caseId) {
  const candidate = await requestCandidate(page, "改写本节", "明确教学目标与任务关系");
  await candidate.getByRole("button", { name: "替换本节" }).click();
  const held = await holdSnapshot(page, caseId);
  await candidate.getByRole("button", { name: "接受修订" }).click();
  await held.started;
  await expectCandidateLock(page, candidate, held.release);
  await expectSavedCandidate(page, caseId, candidate, CANDIDATE_TEXT);
  return { candidate, held };
}

async function expectCandidateLock(page, candidate, release) {
  try {
    await expect(page.getByLabel("案例标题")).toHaveAttribute("readonly", "");
    await expect(page.locator(".canvas-editor")).toHaveAttribute("contenteditable", "false");
    await expect(candidate.getByRole("button", { name: "接受修订" })).toBeDisabled();
    await expect(page.locator(".candidate-inline-preview")).toHaveCount(0);
  } finally { release(); }
}

async function expectSavedCandidate(page, caseId, candidate, expected) {
  await expect(candidate).toContainText("已接受");
  await expect(page.locator(".canvas-editor")).toContainText(expected);
  await expect(page.locator(".save-state")).toHaveText("已保存");
  const saved = await (await page.context().request.get(`/api/cases/${caseId}`)).json();
  expect(documentText(saved.document)).toContain(expected);
}

async function acceptSecondCandidate(page, caseId, held) {
  const second = await requestCandidate(
    page, "改写本节", "生成第二条修订", SECOND_CANDIDATE_TEXT,
  );
  await second.getByRole("button", { name: "替换本节" }).click();
  await second.getByRole("button", { name: "接受修订" }).click();
  await expectSavedCandidate(page, caseId, second, SECOND_CANDIDATE_TEXT);
  expect(held.count()).toBe(1);
  return second;
}

async function rollbackBatch(page, caseId, marker, candidates) {
  page.once("dialog", (dialog) => dialog.accept());
  await candidates.at(-1).getByRole("button", { name: "回滚本批" }).click();
  await expect(page.locator(".canvas-editor")).toContainText(marker);
  await Promise.all(candidates.map((candidate) => expect(candidate).toContainText("已回滚")));
  const restored = await (await page.context().request.get(`/api/cases/${caseId}`)).json();
  expect(documentText(restored.document)).toContain(marker);
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

async function configureCandidateProvider(page) {
  await saveUserSettings(page, {
    mode: "custom", baseUrl: E2E_PROVIDER,
    apiKey: E2E_API_KEY, model: "e2e-model-a",
  });
}

async function expectSearchAnswer(page) {
  await page.goto("/#/search?q=如何弘扬科学家精神");
  const answer = page.getByRole("region", { name: "AI 回答" });
  await expect(answer).toContainText(E2E_ANSWER);
  await expect(answer.locator(".stream-caret")).toHaveCount(0);
}

function watchRequests(page, path) {
  const requests = [];
  page.on("request", (request) => {
    if (request.url().includes(path)) requests.push(request.url());
  });
  return requests;
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

async function withCandidateProvider(page, scenario) {
  await login(page);
  try {
    await configureCandidateProvider(page);
    await scenario(page);
  } finally {
    await saveUserSettings(page, { mode: "automatic" });
  }
}

async function openCandidateCase(page, prefix) {
  const marker = `${prefix} ${Date.now()}`;
  const created = await createCandidateCase(page, marker);
  await page.goto(`/#/workbench/${created.id}`);
  return { marker, created };
}

async function expectPersistedText(page, caseId, text) {
  const current = await (await page.context().request.get(`/api/cases/${caseId}`)).json();
  expect(documentText(current.document)).toContain(text);
}

async function appendToParagraph(page, text, addition) {
  await page.locator(".canvas-editor p", { hasText: text }).click();
  await page.keyboard.press("End");
  await page.keyboard.type(addition);
}

async function rejectCandidateScenario(page) {
  const { marker, created } = await openCandidateCase(page, "选区拒绝原文");
  await selectParagraph(page, marker);
  const candidate = await requestCandidate(page, "改写选区", "压缩这段表述");
  await candidate.getByRole("button", { name: "拒绝修订" }).click();
  await expect(candidate).toContainText("已拒绝");
  await expect(page.locator(".candidate-inline-preview")).toHaveCount(0);
  await expect(page.locator(".canvas-editor")).toContainText(marker);
  await expectPersistedText(page, created.id, marker);
}

async function rollbackCandidateScenario(page) {
  const { marker, created } = await openCandidateCase(page, "批前正文");
  const { candidate, held } = await acceptFirstCandidate(page, created.id);
  const second = await acceptSecondCandidate(page, created.id, held);
  await rollbackBatch(page, created.id, marker, [candidate, second]);
}

async function invalidatePendingScenario(page) {
  const { marker } = await openCandidateCase(page, "待确认正文");
  const candidate = await requestCandidate(page, "改写本节", "精简本节");
  await appendToParagraph(page, marker, " 教师补充");
  await expect(candidate).toContainText("正文已变化，请重新生成");
  await expect(candidate.getByRole("button", { name: "接受修订" })).toHaveCount(0);
  await expect(page.locator(".candidate-inline-preview")).toHaveCount(0);
}

async function expireRollbackScenario(page) {
  const { created } = await openCandidateCase(page, "批次过期");
  const { candidate } = await acceptFirstCandidate(page, created.id);
  await appendToParagraph(page, CANDIDATE_TEXT, " 教师定稿");
  await expect(page.locator(".save-state")).toHaveText("已保存");
  await expect(candidate).toContainText("回滚已过期");
  await expect(candidate.getByRole("button", { name: "回滚本批" })).toHaveCount(0);
  await expectPersistedText(page, created.id, "教师定稿");
}

async function losePatchResponse(route) {
  if (route.request().method() !== "PATCH") return route.continue();
  const response = await route.fetch();
  expect(response.ok()).toBe(true);
  await route.fulfill({
    status: 503, contentType: "application/json", body: '{"detail":"响应中断"}',
  });
}

async function failCaseRequest(route) {
  await route.fulfill({
    status: 503, contentType: "application/json", body: '{"detail":"服务暂不可用"}',
  });
}

async function acceptLostResponseScenario(page) {
  const { created } = await openCandidateCase(page, "响应丢失");
  const candidate = await requestCandidate(page, "改写本节", "模拟响应丢失");
  const path = `**/api/cases/${created.id}`;
  await page.route(path, losePatchResponse);
  try {
    await candidate.getByRole("button", { name: "接受修订" }).click();
    await expect(candidate).toContainText("已接受");
    await expect(page.locator(".canvas-editor")).toContainText(CANDIDATE_TEXT);
    await expectPersistedText(page, created.id, CANDIDATE_TEXT);
  } finally {
    await page.unroute(path);
  }
}

async function expectFailedCandidateRecovery(page, candidate, marker) {
  await expect(page.locator(".ai-message.assistant").last().getByRole("alert")).toBeVisible();
  await expect(candidate).not.toContainText("已接受");
  await expect(page.locator(".canvas-editor")).toContainText(marker);
  await expect(page.locator(".canvas-editor")).toHaveAttribute("contenteditable", "false");
}

async function failCandidateRecoveryScenario(page) {
  const { marker, created } = await openCandidateCase(page, "修订恢复");
  const candidate = await requestCandidate(page, "改写本节", "模拟保存失败");
  const path = `**/api/cases/${created.id}`;
  await page.route(path, failCaseRequest);
  try {
    await candidate.getByRole("button", { name: "接受修订" }).click();
    await expectFailedCandidateRecovery(page, candidate, marker);
  } finally {
    await page.unroute(path);
  }
  await page.getByRole("button", { name: "重新载入" }).click();
  await expect(page.locator(".canvas-editor")).toHaveAttribute("contenteditable", "true");
}

test("未配置 AI 时工作台提供设置入口且正文保持不变", async ({ page }) => {
  await login(page);
  await saveUserSettings(page, { mode: "automatic" });
  await page.goto("/#/workbench/c-draft-1");
  const title = await page.getByLabel("案例标题").inputValue();

  await expect(page.getByText("AI 服务尚未配置")).toBeVisible();
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
    const chatRequests = watchRequests(page, "/api/ai/chat");
    const settingsRequests = watchRequests(page, "/api/ai/settings");
    await expectSearchAnswer(page);
    expect(chatRequests).toHaveLength(1);
    expect(settingsRequests).toHaveLength(1);
    await expectWorkbenchAnswer(page);
  } finally {
    await saveUserSettings(page, { mode: "automatic" });
  }
});

test("AI 选区候选被拒绝后不修改正文", async ({ page }) => (
  withCandidateProvider(page, rejectCandidateScenario)
));

test("连续接受 AI 候选只建一个批前快照、持久化并可整批回滚", async ({ page }) => (
  withCandidateProvider(page, rollbackCandidateScenario)
));

test("待确认修订在教师修改正文后失效", async ({ page }) => (
  withCandidateProvider(page, invalidatePendingScenario)
));

test("AI 批次后手工修改会令旧卡回滚过期", async ({ page }) => (
  withCandidateProvider(page, expireRollbackScenario)
));

test("AI 修订响应丢失时按服务端正文判定为已接受", async ({ page }) => (
  withCandidateProvider(page, acceptLostResponseScenario)
));

test("AI 修订保存与恢复查询均失败时本地回原并锁定到重载", async ({ page }) => (
  withCandidateProvider(page, failCandidateRecoveryScenario)
));

test("上游提前断流时工作台显示明确错误", async ({ page }) => {
  await login(page);
  try {
    await configureE2EProvider(page);
    await page.goto("/#/workbench/c-draft-1");
    await page.getByLabel("向 AI 提问").fill("上游中断测试");
    await page.getByRole("button", { name: "发送", exact: true }).click();
    const answer = page.locator(".ai-message.assistant").last();
    await expect(answer.getByRole("alert")).toHaveText("AI 服务暂不可用");
    await expect(answer.locator(".spin")).toHaveCount(0);
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
