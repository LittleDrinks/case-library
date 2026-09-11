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

async function openDraft(page, marker) {
  await login(page);
  const created = await createCase(page.context().request, marker);
  await page.goto(`/#/workbench/${created.id}`);
  await expect(page.locator(".canvas-editor")).toContainText(marker);
  return created;
}

async function selectManualAnnotation(page, marker) {
  await page.locator(".canvas-editor p", { hasText: marker }).selectText();
  await expect(page.getByRole("button", { name: "添加选区批注" })).toBeEnabled();
  await page.getByRole("button", { name: "添加选区批注" }).click();
}

async function selectSubstring(page, paragraph, value) {
  await paragraph.click();
  await page.keyboard.press("Home");
  const offset = await paragraph.evaluate((node, text) => node.textContent.indexOf(text), value);
  expect(offset).toBeGreaterThanOrEqual(0);
  for (let index = 0; index < offset; index += 1) await page.keyboard.press("ArrowRight");
  await page.keyboard.down("Shift");
  for (let index = 0; index < value.length; index += 1) await page.keyboard.press("ArrowRight");
  await page.keyboard.up("Shift");
  await expect.poll(() => page.evaluate(() => window.getSelection()?.toString() || "")).toBe(value);
}

async function addSelectedAnnotation(page, paragraph, quote, content) {
  await selectSubstring(page, paragraph, quote);
  await page.getByRole("button", { name: "添加选区批注" }).click();
  await page.getByLabel("批注内容").fill(content);
  await page.getByRole("button", { name: "添加批注", exact: true }).click();
  await expect(page.locator(".comment-card", { hasText: content })).toBeVisible();
  const caseId = page.url().split("/").pop();
  const response = await page.context().request.get("/api/cases/" + caseId + "/annotations");
  return (await response.json()).find((row) => row.content === content);
}

async function dataIds(locator) {
  return locator.evaluateAll((nodes) => nodes.map((node) => node.dataset.annotationId).sort());
}

async function expectAnnotationIdentity(page, first, second) {
  const cards = page.locator(".comment-card");
  await expect(cards).toHaveCount(2);
  expect(await dataIds(cards)).toEqual([first.id, second.id].sort());
  const anchors = page.locator(".annotation-anchor");
  await expect(anchors).toHaveCount(2);
  expect(await dataIds(anchors)).toEqual([first.id, second.id].sort());
}

async function resolveFirstAnnotation(page, first, second) {
  await page.locator(".annotation-anchor[data-annotation-id=\"" + second.id + "\"]").click();
  await expect(page.locator(".comment-card[data-annotation-id=\"" + second.id + "\"]")).toBeInViewport();
  await page.locator(".comment-card[data-annotation-id=\"" + first.id + "\"]").getByRole("button", { name: "标记解决" }).click();
  await expect(page.locator(".comment-card[data-annotation-id=\"" + first.id + "\"]")).toContainText("已解决");
  await expect(page.locator(".comment-card[data-annotation-id=\"" + second.id + "\"]")).toContainText("待处理");
}

async function expectReloadedAnnotations(page, first, second) {
  const cards = page.locator(".comment-card");
  await expect(cards).toHaveCount(2);
  const caseId = page.url().split("/").pop();
  const rows = await (await page.context().request.get("/api/cases/" + caseId + "/annotations")).json();
  expect(rows).toEqual(expect.arrayContaining([
    expect.objectContaining({ id: first.id, status: "resolved", quote: "同段甲：教学依据" }),
    expect.objectContaining({ id: second.id, status: "pending", quote: "同段乙：课堂活动" }),
  ]));
  expect(await dataIds(cards)).toEqual([first.id, second.id].sort());
}

async function addManualAnnotation(page, marker, content) {
  await selectManualAnnotation(page, marker);
  await page.getByLabel("批注内容").fill(content);
  await page.getByRole("button", { name: "添加批注", exact: true }).click();
  await expect(page.locator(".comment-card blockquote")).toHaveText(marker);
  await expect(page.locator(".annotation-anchor")).toHaveCount(1);
}

async function editManualAnnotation(page, content) {
  const card = page.locator(".comment-card").first();
  await card.getByRole("button", { name: "编辑批注" }).click();
  await page.getByLabel("编辑批注").fill(content);
  await page.getByRole("button", { name: "保存批注" }).click();
  await expect(card).toContainText(content);
}

async function deleteManualAnnotation(page) {
  await page.locator(".comment-card").first().getByRole("button", { name: "删除批注" }).click();
  await expect(page.locator(".comment-card")).toHaveCount(0);
}

async function seedManualAnnotation(page, marker) {
  await page.setViewportSize({ width: 1280, height: 900 });
  await openDraft(page, marker);
  await addManualAnnotation(page, marker, "请补充课堂活动与评价依据。");
  return page.url().split("/").pop();
}

async function expectActiveAnnotation(page, caseId, marker) {
  const response = await page.context().request.get(`/api/cases/${caseId}/annotations`);
  const annotations = await response.json();
  expect(annotations[0]).toMatchObject({ quote: marker, anchorState: "active" });
}

async function manualAnnotationScenario(page) {
  const marker = `手工批注正文 ${Date.now()}`;
  await seedManualAnnotation(page, marker);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.reload();
  await page.getByRole("button", { name: "批注", exact: true }).click();
  await expect(page.locator(".comment-card blockquote")).toHaveText(marker);
  const panel = await page.locator(".comment-panel").boundingBox();
  expect(panel.y + panel.height).toBeLessThanOrEqual(844);
  await editManualAnnotation(page, "已补充课堂活动与评价依据。");
  await deleteManualAnnotation(page);
}

test("审核批注随退回跨轮保留并由作者解决", async ({ page }) => {
  const marker = `批注选区 ${Date.now()}`;
  const created = await openReview(page, marker);
  await addReviewAnnotation(page);
  await rejectCase(page);
  await resolveAsAuthor(page, created, marker);
});

test("教师可在桌面创建并在移动端刷新编辑删除手工批注", async ({ page }) => {
  await manualAnnotationScenario(page);
});

test("同段多个批注可分别打开与关闭并刷新保留", async ({ page }) => {
  const marker = `同段甲：教学依据；同段乙：课堂活动 ${Date.now()}`;
  await openDraft(page, marker);
  const paragraph = page.locator(".canvas-editor p", { hasText: marker });
  await page.getByRole("button", { name: "批注", exact: true }).click();
  const first = await addSelectedAnnotation(page, paragraph, "同段甲：教学依据", "第一条批注");
  const second = await addSelectedAnnotation(page, paragraph, "同段乙：课堂活动", "第二条批注");
  expect(first.id).not.toBe(second.id);
  await expectAnnotationIdentity(page, first, second);
  await resolveFirstAnnotation(page, first, second);
  await page.reload(); await page.getByRole("button", { name: "批注", exact: true }).click();
  await expectReloadedAnnotations(page, first, second);
});

test("正文前置编辑保存刷新后批注仍绑定原选区", async ({ page }) => {
  const marker = `持久锚点正文 ${Date.now()}`;
  const caseId = await seedManualAnnotation(page, marker);
  await page.locator(".annotation-anchor").click();
  await expect(page.locator(".comment-panel")).toBeVisible();

  const paragraph = page.locator(".canvas-editor p", { hasText: marker });
  await paragraph.click();
  await page.keyboard.press("Home");
  await page.keyboard.type("前置文字 ");
  await expect(page.locator(".save-state")).toHaveText("已保存", { timeout: 5000 });
  await expect(page.locator(".annotation-anchor")).toHaveText(marker);

  await expectActiveAnnotation(page, caseId, marker);
  await page.reload();
  await expect(page.locator(".annotation-anchor")).toHaveText(marker);
  await page.getByRole("button", { name: "批注", exact: true }).click();
  await expect(page.locator(".comment-card blockquote")).toHaveText(marker);
});

test("匿名用户不能读取案例批注", async ({ page }) => {
  const created = await openDraft(page, `匿名批注权限 ${Date.now()}`);
  await logoutAndWait(page);
  const response = await page.context().request.get(`/api/cases/${created.id}/annotations`);
  expect(response.status()).toBe(401);
});
