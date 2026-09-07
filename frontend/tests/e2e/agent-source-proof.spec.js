import { expect, test } from "@playwright/test";
import { waitForCatalogSynced } from "./catalog-ready.js";

const QUESTION = "资料区验收：请依据已选资料回答。";

async function login(page) {
  await page.goto("/#/login?redirect=/workbench/c-draft-1");
  await page.getByLabel("用户名").fill("user");
  await page.getByLabel("密码").fill("user123");
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page).toHaveURL(/#\/workbench\/c-draft-1$/);
}

async function csrfToken(page) {
  const response = await page.context().request.get("/api/auth/session");
  return (await response.json()).csrfToken;
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

async function openChat(page) {
  await page.locator(".workspace-actions").getByRole("button", { name: "AI", exact: true }).click();
  await expect(page.locator(".agent-chat-panel")).toBeVisible();
  await expect(page.getByLabel("向 AI 提问")).toBeEnabled();
}

async function createCaseViaApi(page, title) {
  const response = await page.context().request.post("/api/cases", {
    headers: { "X-CSRF-Token": await csrfToken(page) },
    data: {
      title,
      document: {
        type: "doc",
        content: [{ type: "paragraph", content: [{ type: "text", text: "资料区验收正文" }] }],
      },
    },
  });
  expect(response.ok()).toBe(true);
  return response.json();
}

async function firstAvailableMaterial(request) {
  await waitForCatalogSynced(request);
  const rows = async () => {
    const response = await request.get("/api/search", {
      params: { q: "", kind: "material", pageSize: 50 },
    });
    const items = response.ok() ? (await response.json()).items : [];
    return items.filter((row) => row.contentAvailable !== false);
  };
  await expect.poll(async () => (await rows()).length, { timeout: 30_000 }).toBeGreaterThanOrEqual(1);
  return (await rows())[0];
}

async function currentRevision(page, caseId) {
  const current = await page.context().request.get(`/api/cases/${caseId}`);
  expect(current.ok()).toBe(true);
  return (await current.json()).revision;
}

async function mountMaterial(page, caseId, materialId) {
  const response = await page.context().request.post(`/api/cases/${caseId}/materials`, {
    headers: { "X-CSRF-Token": await csrfToken(page) },
    data: { materialId, revision: await currentRevision(page, caseId) },
  });
  expect(response.ok()).toBe(true);
}

async function unmountMaterial(page, caseId, materialId) {
  const revision = await currentRevision(page, caseId);
  const response = await page.context().request.delete(
    `/api/cases/${caseId}/materials/${materialId}?revision=${revision}`,
    { headers: { "X-CSRF-Token": await csrfToken(page) } },
  );
  expect(response.ok()).toBe(true);
}

async function selectSingleSource(page) {
  await page.locator(".agent-source-picker-toggle").click();
  const option = page.locator(".agent-source-option input");
  await expect(option).toHaveCount(1);
  await option.first().check();
  await expect(page.locator(".agent-source-chip")).toHaveCount(1);
}

async function sendQuestion(page, text) {
  await page.getByLabel("向 AI 提问").fill(text);
  await page.getByRole("button", { name: "发送", exact: true }).click();
  await expect(page.locator(".agent-chat-panel"))
    .toHaveAttribute("data-run-status", "completed", { timeout: 15_000 });
}

async function userPartSequence(page) {
  return page.locator(".ai-message.user").last().evaluate((node) =>
    [...node.querySelectorAll(":scope > p")].map((p) => p.dataset.testid || "text"),
  );
}

async function persistedPartTypes(page, caseId) {
  const response = await page.context().request.get(`/api/cases/${caseId}/agent/thread`);
  expect(response.ok()).toBe(true);
  const user = (await response.json()).messages.find((message) => message.role === "user");
  return user.parts.map((part) => (part.type === "text" ? "text" : part.type));
}

async function reopenPanel(page) {
  await page.locator(".drawer-toggle").click();
  await page.locator(".drawer-toggle").click();
  await expect(page.locator(".agent-chat-panel")).toBeVisible();
}

async function assertOrderedSourceParts(page, caseId, material) {
  expect(await persistedPartTypes(page, caseId)).toEqual(["text", "data-source"]);
  expect(await userPartSequence(page)).toEqual(["text", "message-source"]);
  const chip = page.getByTestId("message-source");
  const href = new RegExp(`/api/materials/${material.id}/content$`);
  await expect(chip.locator("a")).toHaveAttribute("href", href);
}

async function assertUnmountHidesLink(page, caseId, materialId) {
  await unmountMaterial(page, caseId, materialId);
  await reopenPanel(page);
  const chip = page.getByTestId("message-source");
  await expect(chip).toContainText(/来源：.*来源已下线或不可读取/s);
  await expect(chip.locator("a")).toHaveCount(0);
}

test("选中来源消息按 part 顺序渲染，卸载后重开撤下链接并显示来源不可用", async ({ page }) => {
  test.setTimeout(90_000);
  await page.setViewportSize({ width: 1440, height: 900 });
  await login(page);
  const material = await firstAvailableMaterial(page.context().request);
  const created = await createCaseViaApi(page, `Source Proof ${Date.now()}`);
  await mountMaterial(page, created.id, material.id);
  await page.goto(`/#/workbench/${created.id}`);
  await expect(page.getByLabel("案例标题")).toBeVisible();
  await configureProviderChat(page);
  await openChat(page);
  await selectSingleSource(page);
  await sendQuestion(page, QUESTION);
  await assertOrderedSourceParts(page, created.id, material);
  await assertUnmountHidesLink(page, created.id, material.id);
});
