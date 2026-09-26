import { expect, test } from "@playwright/test";

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
  await page.goto("/#/");
  await page.getByRole("button", { name: "退出登录" }).click();
  await expect(page).toHaveURL(/#\/login$/);
}

async function createCase(request, marker) {
  const auth = await (await request.get("/api/auth/session")).json();
  const document = { type: "doc", content: [
    { type: "heading", attrs: { level: 1 }, content: [{ type: "text", text: "一、教学说明" }] },
    { type: "paragraph", content: [{ type: "text", text: marker }] },
  ] };
  const response = await request.post("/api/cases", {
    headers: { "X-CSRF-Token": auth.csrfToken }, data: { title: marker, document },
  });
  expect(response.ok()).toBe(true);
  return response.json();
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


for (const withMessage of [true, false]) {
  test(`退回原因${withMessage ? "多选与完整留言" : "其他无留言"}刷新可读，作者可再次投稿`, async ({ page }) => {
    const marker = `审核退回 ${Date.now()}`;
    const created = await openReview(page, marker);
    await page.getByRole("button", { name: "退回修改", exact: true }).click();
    const dialog = page.getByRole("dialog", { name: "退回修改" });
    const confirm = dialog.getByRole("button", { name: "确认退回" });
    await expect(confirm).toBeDisabled();
    const reasons = withMessage ? ["内容需要补充或修改", "事实、数据或来源需要核实"] : ["其他"];
    for (const reason of reasons) await dialog.getByLabel(reason, { exact: true }).check();
    const message = "请补充课堂活动的具体步骤，并注明材料来源。".repeat(12) + "末尾反馈可读。";
    if (withMessage) await dialog.getByLabel("留言（可选）").fill(message);
    await expect(confirm).toBeEnabled();
    await confirm.click();
    await expect(dialog).toBeHidden();
    await expect(page.locator(".case-status")).toHaveText("草稿");
    await logoutAndWait(page);
    await login(page);
    await page.goto(`/#/workbench/${created.id}`);
    await page.reload();
    const notice = page.locator(".review-return-banner");
    for (const reason of reasons) await expect(notice).toContainText(reason);
    if (withMessage) await expect(notice).toContainText(message);
    await expect(page.getByRole("button", { name: "批注", exact: true })).toHaveCount(0);
    await page.getByLabel("案例标题").fill(`${marker} 已补充`);
    await expect(page.locator(".save-state")).toHaveText("已保存");
    await page.getByRole("button", { name: "提交审核", exact: true }).click();
    await expect(page.locator(".case-status")).toHaveText("待审");
  });
}
