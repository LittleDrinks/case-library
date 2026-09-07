import { expect, test } from "@playwright/test";
import { SKILL_ID, teachingPackage } from "./skill-package.js";

const REQUEST_TEXT = "请结合平台资料修订第2段：补充评价依据";
const REPLACEMENT_MARK = "修订后的段落：教学目标、课堂任务与评价依据逐项对应";

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
    data: { title: `Tracer ${Date.now()}`, document: caseDocument() },
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

async function waitSearchableCatalog(page) {
  await expect
    .poll(async () => {
      const response = await page.context().request.get("/api/search?q=科学家精神&pageSize=3");
      return (await response.json()).items?.length || 0;
    }, { timeout: 90_000, intervals: [2_000] })
    .toBeGreaterThan(0);
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

async function selectPublishedSkill(page) {
  const picker = page.getByLabel("选择 Skill");
  await expect(picker.locator(`option[value="${SKILL_ID}"]`)).toBeVisible({ timeout: 30_000 });
  await picker.selectOption(SKILL_ID);
}

async function sendRequest(page) {
  await page.getByLabel("向 AI 提问").fill(REQUEST_TEXT);
  await page.getByRole("button", { name: "发送", exact: true }).click();
  const artifact = page.getByTestId("agent-artifact");
  await expect(artifact).toBeVisible({ timeout: 30_000 });
  await expect(artifact).toHaveAttribute("data-artifact-status", "pending");
}

async function acceptedViaApi(page, caseId) {
  const caseApi = await page.context().request.get(`/api/cases/${caseId}`);
  const persisted = await caseApi.json();
  expect(persisted.revision).toBe(2);
  expect(persisted.document.content[1].content[0].text).toContain(REPLACEMENT_MARK);
}

async function reloadRestoresTracer(page, caseId) {
  await page.reload();
  await openChat(page, caseId);
  await expect(page.getByTestId("agent-skill-load")).toBeVisible();
  await expect(page.getByTestId("agent-source").first()).toBeVisible();
  const artifact = page.getByTestId("agent-artifact");
  await expect(artifact).toHaveAttribute("data-artifact-status", "accepted");
  await expect(artifact).toContainText(REPLACEMENT_MARK);
  await expect(artifact).toContainText("原文：第二段：教学目标需要更明确的评价依据。");
}

async function prepareTracer(page, playwright) {
  await publishTeachingSkill(playwright);
  await login(page);
  await configureChat(page);
  await waitSearchableCatalog(page);
  const created = await createCase(page);
  await openChat(page, created.id);
  await selectPublishedSkill(page);
  return created;
}

test("单段修订 tracer：发送、检索、生成、接受、刷新恢复全程真实 HTTP", async ({ page, playwright }) => {
  const created = await prepareTracer(page, playwright);

  await sendRequest(page);
  await expect(page.getByTestId("agent-skill-load")).toBeVisible();
  const sources = page.getByTestId("agent-source");
  await expect(sources.first()).toBeVisible();
  expect(await sources.count()).toBeGreaterThan(0);

  await page.getByTestId("agent-accept").click();
  const artifact = page.getByTestId("agent-artifact");
  await expect(artifact).toHaveAttribute("data-artifact-status", "accepted", { timeout: 15_000 });
  await acceptedViaApi(page, created.id);
  await reloadRestoresTracer(page, created.id);
});
