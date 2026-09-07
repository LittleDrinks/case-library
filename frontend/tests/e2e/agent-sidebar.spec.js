import { expect, test } from "@playwright/test";
import { SKILL_ID, teachingPackage } from "./skill-package.js";
import { waitForCatalogSynced } from "./catalog-ready.js";

const CASE_ID = "c-draft-1";
const MATERIAL_COUNT = 15;
const THINKING_TEXT = "先核对资料区与选区，再检索平台依据。";
const THINKING_QUESTION = "请结合平台资料修订第2段（思考测试）：补充评价依据";
const TARGET_TEXT = "第二段：教学目标需要更明确的评价依据。";
const ANSWER = "隔离模型回答：已依据当前可见资源完成分析。";
const FIRST_QUESTION = "侧栏验收：默认线程的问题";
const SECOND_QUESTION = "侧栏验收：新建线程的问题";

async function login(page, caseId = CASE_ID) {
  await page.goto(`/#/login?redirect=/workbench/${caseId}`);
  await page.getByLabel("用户名").fill("user");
  await page.getByLabel("密码").fill("user123");
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`#\\/workbench\\/${caseId}$`));
}

async function openChat(page) {
  await page.locator(".workspace-actions").getByRole("button", { name: "AI", exact: true }).click();
  await expect(page.locator(".agent-chat-panel")).toBeVisible();
  await expect.poll(() => page.locator(".assistant-rail").evaluate((node) => node.getBoundingClientRect().height)).toBeGreaterThan(300);
  await expect(page.getByLabel("向 AI 提问")).toBeEnabled();
}

async function layout(page) {
  return page.evaluate(() => {
    const rail = document.querySelector(".assistant-rail").getBoundingClientRect();
    const panel = document.querySelector(".agent-chat-panel");
    const conversation = document.querySelector(".ai-conversation");
    const composer = document.querySelector(".assistant-composer").getBoundingClientRect();
    return {
      railBottom: rail.bottom, viewport: innerHeight, railHeight: rail.height,
      panelOverflow: getComputedStyle(panel).overflow,
      conversationOverflow: getComputedStyle(conversation).overflowY,
      composerBottom: composer.bottom, widthOverflow: document.documentElement.scrollWidth - innerWidth,
    };
  });
}

async function assertLayout(page, screenshot) {
  const box = await layout(page);
  expect(Math.abs(box.railBottom - box.viewport)).toBeLessThanOrEqual(1);
  expect(box.railHeight).toBeGreaterThan(300);
  expect(box.panelOverflow).toBe("hidden");
  expect(box.conversationOverflow).toBe("auto");
  expect(box.composerBottom).toBeLessThanOrEqual(box.railBottom + 1);
  expect(box.widthOverflow).toBeLessThanOrEqual(1);
  await page.screenshot({ path: screenshot });
}

async function assertReducedMotion(page) {
  expect(await page.evaluate(() => matchMedia("(prefers-reduced-motion: reduce)").matches)).toBe(true);
  expect(await page.evaluate(() => {
    const details = document.createElement("details");
    details.className = "agent-reasoning streaming";
    details.innerHTML = "<summary>测试</summary>";
    document.body.append(details);
    const animation = getComputedStyle(details.querySelector("summary")).animationName;
    details.remove();
    return animation;
  })).toBe("none");
}

async function csrfToken(page) {
  const response = await page.context().request.get("/api/auth/session");
  return (await response.json()).csrfToken;
}

function documentWith(paragraphs) {
  return {
    type: "doc",
    content: paragraphs.map((text) => ({ type: "paragraph", content: [{ type: "text", text }] })),
  };
}

async function createCaseViaApi(page, title, paragraphs, document = documentWith(paragraphs || [])) {
  const response = await page.context().request.post("/api/cases", {
    headers: { "X-CSRF-Token": await csrfToken(page) },
    data: { title, document },
  });
  expect(response.ok()).toBe(true);
  return response.json();
}

async function configureProviderChat(page) {
  const response = await page.context().request.put("/api/ai/settings", {
    headers: { "X-CSRF-Token": await csrfToken(page) },
    data: {
      mode: "custom", baseUrl: "http://ai-provider:8080/v1",
      apiKey: "e2e-api-key", model: "e2e-model-a",
    },
  });
  expect(response.ok()).toBe(true);
}

async function sendQuestion(page, text) {
  await page.getByLabel("向 AI 提问").fill(text);
  await page.getByRole("button", { name: "发送", exact: true }).click();
  await expect(page.locator(".ai-message.assistant").last()).toContainText(ANSWER, { timeout: 15_000 });
}

async function openThreadList(page) {
  await page.getByTestId("agent-thread-list-open").click();
  await expect(page.getByTestId("agent-thread-list")).toBeVisible();
}

async function threadSnapshot(page, caseId, threadId) {
  const response = await page.context().request.get(`/api/cases/${caseId}/agent/threads/${threadId}`);
  expect(response.ok()).toBe(true);
  return response.json();
}

function userTexts(snapshot) {
  return snapshot.messages
    .filter((message) => message.role === "user")
    .map((message) => message.parts.find((part) => part.type === "text")?.text);
}

async function createEmptyThread(page) {
  await page.getByTestId("agent-thread-create").click();
  await expect(page.getByLabel("向 AI 提问")).toBeEnabled();
  await expect(page.locator(".ai-message")).toHaveCount(0);
  await expect(page.getByTestId("agent-thread-list-open")).toContainText("未命名对话");
}

async function switchThread(page, text) {
  await openThreadList(page);
  await expect(page.getByTestId("agent-thread-open")).toHaveCount(2);
  await page.getByTestId("agent-thread-open").filter({ hasText: text }).click();
  await expect(page.locator(".ai-message.user").last()).toContainText(text);
}

async function assertThreadsIsolatedViaApi(page, caseId) {
  const listResponse = await page.context().request.get(`/api/cases/${caseId}/agent/threads`);
  expect(listResponse.ok()).toBe(true);
  const threads = await listResponse.json();
  expect(threads).toHaveLength(2);
  const [first, second] = await Promise.all(
    threads.map((row) => threadSnapshot(page, caseId, row.id)),
  );
  expect(userTexts(first)).toEqual([FIRST_QUESTION]);
  expect(userTexts(second)).toEqual([SECOND_QUESTION]);
  expect(first.latestRun.id).not.toBe(second.latestRun.id);
}

async function reloadRestoresThread(page, text) {
  await page.reload();
  await openChat(page);
  await expect(page.getByTestId("agent-thread-list-open")).toContainText(text);
  await expect(page.locator(".ai-message.user")).toContainText(text);
}

function longParagraphs(count) {
  return Array.from({ length: count }, (_, index) => `第${index + 1}段：撑起工作台滚动高度的验收正文。`);
}

async function composerViewportBox(page) {
  return page.evaluate(() => {
    const rect = document.querySelector(".assistant-composer textarea").getBoundingClientRect();
    return { top: rect.top, bottom: rect.bottom, height: rect.height, viewport: innerHeight };
  });
}

async function availableMaterialIds(page, count) {
  await waitForCatalogSynced(page.context().request);
  const response = await page.context().request.get("/api/search", {
    params: { q: "", kind: "material", pageSize: 100 },
  });
  expect(response.ok()).toBe(true);
  const rows = (await response.json()).items.filter((row) => row.contentAvailable !== false);
  expect(rows.length).toBeGreaterThanOrEqual(count);
  return rows.slice(0, count).map((row) => row.id);
}

async function mountMaterials(page, caseId, materialIds) {
  const headers = { "X-CSRF-Token": await csrfToken(page) };
  for (const materialId of materialIds) {
    const current = await page.context().request.get(`/api/cases/${caseId}`);
    expect(current.ok()).toBe(true);
    const { revision } = await current.json();
    const response = await page.context().request.post(`/api/cases/${caseId}/materials`, {
      headers, data: { materialId, revision },
    });
    expect(response.ok()).toBe(true);
  }
}

async function selectAllSources(page) {
  await page.locator(".agent-source-picker-toggle").click();
  const options = page.locator(".agent-source-option input");
  await expect(options).toHaveCount(MATERIAL_COUNT);
  for (let index = 0; index < MATERIAL_COUNT; index += 1) await options.nth(index).check();
  await expect(page.locator(".agent-source-chip")).toHaveCount(MATERIAL_COUNT);
  await expect(page.locator(".agent-source-summary")).toContainText(`已选 ${MATERIAL_COUNT} 条`);
}

function intersects(a, b) {
  return a.left < b.right - 1 && b.left < a.right - 1 && a.top < b.bottom - 1 && b.top < a.bottom - 1;
}

async function composerGeometry(page) {
  return page.evaluate(() => {
    const box = (node) => {
      const rect = node.getBoundingClientRect();
      return { left: rect.left, right: rect.right, top: rect.top, bottom: rect.bottom, width: rect.width, height: rect.height };
    };
    return {
      textarea: box(document.querySelector(".assistant-composer textarea")),
      send: box(document.querySelector('.assistant-composer button[aria-label="发送"]')),
      chips: [...document.querySelectorAll(".agent-source-chip")].map(box),
      viewport: innerHeight, width: innerWidth,
      scrollWidth: document.documentElement.scrollWidth,
    };
  });
}

async function publishTeachingSkill(playwright) {
  const admin = await playwright.request.newContext();
  const loginResponse = await admin.post(
    "/api/auth/login", { data: { username: "admin", password: "admin123" } },
  );
  const headers = { "X-CSRF-Token": (await loginResponse.json()).csrfToken };
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

async function waitSearchableCatalog(page) {
  await expect
    .poll(async () => {
      const response = await page.context().request.get("/api/search?q=科学家精神&pageSize=3");
      return (await response.json()).items?.length || 0;
    }, { timeout: 90_000, intervals: [2_000] })
    .toBeGreaterThan(0);
}

function tracerDocument() {
  return {
    type: "doc",
    content: [
      { type: "paragraph", content: [{ type: "text", text: "第一段保持原样。" }] },
      { type: "paragraph", content: [{ type: "text", text: TARGET_TEXT }] },
    ],
  };
}

async function selectPublishedSkill(page) {
  const picker = page.getByLabel("选择 Skill");
  await expect(picker).toBeVisible();
  await expect(picker.locator(`option[value="${SKILL_ID}"]`)).toHaveCount(1, { timeout: 30_000 });
  await picker.selectOption(SKILL_ID);
  await expect(picker).toHaveValue(SKILL_ID);
}

async function selectCanvasTarget(page) {
  const target = page.locator(".canvas-editor p").nth(1);
  await expect(target).toHaveText(TARGET_TEXT);
  await target.selectText();
  await expect.poll(() => page.evaluate(() => window.getSelection()?.toString() || ""))
    .toBe(TARGET_TEXT);
}

async function prepareThinkingRun(page, playwright) {
  await publishTeachingSkill(playwright);
  await login(page);
  await configureProviderChat(page);
  await waitSearchableCatalog(page);
  const created = await createCaseViaApi(page, `Sidebar Thinking ${Date.now()}`, null, tracerDocument());
  await page.goto(`/#/workbench/${created.id}`);
  await expect(page.getByLabel("案例标题")).toBeVisible();
  await openChat(page);
  await selectPublishedSkill(page);
  await selectCanvasTarget(page);
  return created;
}

async function expectThinkingStreaming(page) {
  const thinking = page.locator(".agent-reasoning").first();
  await expect(thinking).toHaveClass(/streaming/, { timeout: 15_000 });
  await expect(thinking.locator("summary")).toContainText("思考中");
  await expect(thinking).toHaveAttribute("open", "");
  await expect(page.locator("[data-testid='agent-skill-load'], .agent-tool-trace")).toHaveCount(0);
}

async function expectThinkingBeforeTools(page) {
  const ordered = await page.evaluate(() => {
    const messages = [...document.querySelectorAll(".ai-message.assistant")];
    const message = messages[messages.length - 1];
    const reasoning = message?.querySelector(".agent-reasoning");
    const tool = message?.querySelector("[data-testid='agent-skill-load'], .agent-tool-trace");
    return Boolean(reasoning && tool && reasoning.compareDocumentPosition(tool) & Node.DOCUMENT_POSITION_FOLLOWING);
  });
  expect(ordered).toBe(true);
}

async function expectRunCompleted(page) {
  const panel = page.locator(".agent-chat-panel");
  await expect(panel).toHaveAttribute("data-run-status", "completed", { timeout: 30_000 });
  const thinking = page.locator(".agent-reasoning").first();
  await expect(thinking).not.toHaveClass(/streaming/);
  await expect(thinking.locator("summary")).toContainText("思考过程");
  await expect(thinking).not.toHaveAttribute("open", "");
}

async function expectCompletedToolsFolded(page) {
  const traces = page.locator(
    "[data-testid='agent-skill-load'], [data-testid='agent-source-read'], .agent-tool-trace, [data-testid='agent-skill-resource']",
  );
  await expect(traces.first()).toBeVisible();
  const count = await traces.count();
  expect(count).toBeGreaterThanOrEqual(4);
  for (let index = 0; index < count; index += 1) {
    await expect(traces.nth(index)).not.toHaveAttribute("open", "");
  }
}

async function expectFoldedToolsExpand(page) {
  const thinking = page.locator(".agent-reasoning").first();
  await thinking.locator("summary").click();
  await expect(thinking).toContainText(THINKING_TEXT);
  const load = page.getByTestId("agent-skill-load");
  await load.locator("summary").click();
  await expect(load).toHaveAttribute("open", "");
  await expect(load.locator("summary")).toContainText("已加载 Skill");
}

test("AI 侧栏固定布局、线程视图、移动端和 reduced motion", async ({ page }) => {
  test.setTimeout(60_000);
  await page.setViewportSize({ width: 1440, height: 900 });
  await login(page);
  await openChat(page);
  await assertLayout(page, "test-results/agent-sidebar-desktop.png");
  await page.getByTestId("agent-thread-list-open").click();
  await expect(page.getByTestId("agent-thread-list")).toBeVisible();
  await expect(page.locator(".agent-thread-rows")).toHaveCSS("overflow-y", "auto");
  await page.screenshot({ path: "test-results/agent-sidebar-threads.png" });
  await page.getByTestId("agent-thread-back").click();
  await page.emulateMedia({ reducedMotion: "reduce" });
  await assertReducedMotion(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.reload();
  await openChat(page);
  await assertLayout(page, "test-results/agent-sidebar-mobile.png");
});

async function prepareThreadCase(page) {
  await page.setViewportSize({ width: 1440, height: 900 });
  await login(page);
  await configureProviderChat(page);
  const created = await createCaseViaApi(page, `Sidebar Threads ${Date.now()}`, ["侧栏线程验收正文"]);
  await page.goto(`/#/workbench/${created.id}`);
  await expect(page.getByLabel("案例标题")).toBeVisible();
  await openChat(page);
  return created;
}

test("真实 HTTP 线程：新建、切换与刷新恢复", async ({ page }) => {
  test.setTimeout(60_000);
  const created = await prepareThreadCase(page);
  await sendQuestion(page, FIRST_QUESTION);
  await expect(page.getByTestId("agent-thread-list-open")).toContainText(FIRST_QUESTION);
  await openThreadList(page);
  await expect(page.getByTestId("agent-thread-open")).toHaveCount(1);
  await createEmptyThread(page);
  await sendQuestion(page, SECOND_QUESTION);

  await switchThread(page, FIRST_QUESTION);
  await expect(page.locator(".agent-chat-panel")).not.toContainText(SECOND_QUESTION);
  await assertThreadsIsolatedViaApi(page, created.id);
  await reloadRestoresThread(page, FIRST_QUESTION);
});

test("工作台滚动到底后侧栏输入仍可见", async ({ page }) => {
  test.setTimeout(60_000);
  await page.setViewportSize({ width: 1440, height: 900 });
  await login(page);
  const created = await createCaseViaApi(page, `Sidebar Scroll ${Date.now()}`, longParagraphs(40));
  await page.goto(`/#/workbench/${created.id}`);
  await expect(page.getByLabel("案例标题")).toBeVisible();
  await openChat(page);

  await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight));
  await expect.poll(() => page.evaluate(() => window.scrollY)).toBeGreaterThan(100);
  const box = await composerViewportBox(page);
  expect(box.top).toBeGreaterThanOrEqual(-1);
  expect(box.bottom).toBeLessThanOrEqual(box.viewport + 1);
  expect(box.height).toBeGreaterThanOrEqual(60);
  await expect(page.getByLabel("向 AI 提问")).toBeEditable();
  await page.screenshot({ path: "test-results/agent-sidebar-scrolled.png" });
});

async function prepareSelectedSources(page) {
  await page.setViewportSize({ width: 1440, height: 900 });
  await login(page);
  const created = await createCaseViaApi(page, `Sidebar Sources ${Date.now()}`, ["资料上下文验收正文"]);
  await mountMaterials(page, created.id, await availableMaterialIds(page, MATERIAL_COUNT));
  await page.goto(`/#/workbench/${created.id}`);
  await expect(page.getByLabel("案例标题")).toBeVisible();
  await openChat(page);
  await selectAllSources(page);
}

test("移动端 15 条已选资料不挤压输入框且按钮不重叠", async ({ page }) => {
  test.setTimeout(60_000);
  await prepareSelectedSources(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.locator(".agent-source-chips")).toBeVisible();
  const box = await composerGeometry(page);
  expect(box.scrollWidth).toBeLessThanOrEqual(box.width + 1);
  expect(box.textarea.width).toBeGreaterThanOrEqual(180);
  expect(box.textarea.height).toBeGreaterThanOrEqual(48);
  expect(box.textarea.bottom).toBeLessThanOrEqual(box.viewport + 1);
  expect(box.send.bottom).toBeLessThanOrEqual(box.viewport + 1);
  for (const chip of box.chips) {
    expect(intersects(chip, box.textarea)).toBe(false);
    expect(intersects(chip, box.send)).toBe(false);
  }
  await page.screenshot({ path: "test-results/agent-sidebar-mobile-sources.png" });
});

test("真实运行：Thinking 流式展开、完成后与工具一起折叠", async ({ page, playwright }) => {
  test.setTimeout(90_000);
  await page.setViewportSize({ width: 1440, height: 900 });
  await prepareThinkingRun(page, playwright);

  await page.getByLabel("向 AI 提问").fill(THINKING_QUESTION);
  await page.getByRole("button", { name: "发送", exact: true }).click();
  await expectThinkingStreaming(page);
  await expectRunCompleted(page);
  await expectThinkingBeforeTools(page);
  await expectCompletedToolsFolded(page);
  await expectFoldedToolsExpand(page);
  await page.screenshot({ path: "test-results/agent-sidebar-thinking.png" });
});
