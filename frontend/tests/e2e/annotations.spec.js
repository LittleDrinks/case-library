import { expect, test } from "@playwright/test";
import { createGeneralFigureCase, saveCaseChanges } from "./case-creation.js";

async function login(page, username = "user", password = "user123") {
  await expect.poll(async () => (
    await page.context().request.get("/api/auth/session")
  ).status()).toBe(401);
  await page.goto("/#/workbench/c-draft-1");
  await page.getByLabel("用户名").fill(username);
  await page.getByLabel("密码").fill(password);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page).toHaveURL(/#\/workbench\/c-[^/]+$/);
}

async function logoutAndWait(page) {
  await page.getByRole("button", { name: "退出登录" }).click();
  await expect(page).toHaveURL(/#\/login$/);
}

async function createCase(request, marker) {
  const auth = await (await request.get("/api/auth/session")).json();
  const caseRecord = await createGeneralFigureCase(request, auth.csrfToken);
  return saveCaseChanges(request, auth.csrfToken, caseRecord, {
    title: marker,
    document: annotationDocument(marker),
  });
}

function annotationDocument(marker) {
  return { type: "doc", content: [
    { type: "heading", attrs: { level: 1 }, content: [{ type: "text", text: "一、教学说明" }] },
    { type: "paragraph", content: [{ type: "text", text: marker }] },
  ] };
}

async function lifecycle(request, caseId, command, extra = {}) {
  const auth = await (await request.get("/api/auth/session")).json();
  const current = await (await request.get(`/api/cases/${caseId}`)).json();
  const response = await request.post(`/api/cases/${caseId}/lifecycle`, {
    headers: { "X-CSRF-Token": auth.csrfToken },
    data: { command, revision: current.revision, ...extra },
  });
  expect(response.ok()).toBe(true);
  return response.json();
}

async function completeReviewDecision(page) {
  let dialog = page.getByRole("dialog", { name: "退回修改" });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByLabel("原因类型")).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
  await page.getByRole("button", { name: "退回修改" }).click();
  dialog = page.getByRole("dialog", { name: "退回修改" });
  await expect(dialog.getByRole("button", { name: "确认退回" })).toBeDisabled();
  await dialog.getByLabel("原因类型").fill("教学目标不清晰");
  await dialog.getByLabel("总评").fill("请依据批注补充后重新提交。");
  await dialog.getByRole("button", { name: "确认退回" }).click();
}

async function openReview(page, marker) {
  await login(page);
  const request = page.context().request;
  const created = await createCase(request, marker);
  await lifecycle(request, created.id, "submit");
  await logoutAndWait(page);
  await login(page, "admin", "admin123");
  await lifecycle(request, created.id, "start");
  await page.goto(`/#/admin/review/${created.id}`);
  return created;
}

async function addReviewAnnotation(page) {
  await page.locator(".canvas-editor p").selectText();
  await page.getByRole("button", { name: "添加选区批注" }).click();
  await page.getByLabel("批注内容").fill("请明确课程目标对应的评价标准。");
  await page.getByRole("button", { name: "添加批注", exact: true }).click();
  await expect(page.getByText("请明确课程目标对应的评价标准。")).toBeVisible();
}

async function rejectCase(page) {
  await page.getByRole("button", { name: "退回修改" }).click();
  await completeReviewDecision(page);
  await expect(page.locator(".case-status")).toHaveText("草稿");
}

async function resolveAsAuthor(page, created, marker) {
  await logoutAndWait(page);
  await login(page);
  await page.goto(`/#/workbench/${created.id}`);
  await page.getByRole("button", { name: "批注", exact: true }).click();
  await expect(page.locator(".comment-card blockquote")).toHaveText(marker);
  await page.getByLabel("回复批注").fill("已补充评价标准。");
  await page.getByRole("button", { name: "回复", exact: true }).click();
  await page.getByRole("button", { name: "标记解决" }).click();
  await expect(page.getByText("已解决", { exact: true })).toBeVisible();
}

test("审核批注随退回跨轮保留并由作者解决", async ({ page }) => {
  const marker = `批注选区 ${Date.now()}`;
  const created = await openReview(page, marker);
  await addReviewAnnotation(page);
  await rejectCase(page);
  await resolveAsAuthor(page, created, marker);
});
