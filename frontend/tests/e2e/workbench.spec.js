import { expect, test } from "@playwright/test";
import { readFile } from "node:fs/promises";

async function signIn(page, username, password) {
  await page.goto("/#/login");
  await page.getByLabel("用户名").fill(username);
  await page.getByLabel("密码").fill(password);
  await page.getByRole("button", { name: "登录", exact: true }).click();
}

async function signInFromRoot(page, username, password) {
  await page.goto("/#/");
  const loginLink = page.getByRole("link", { name: "登录", exact: true });
  if (await loginLink.count()) await loginLink.click();
  await page.getByLabel("用户名").fill(username);
  await page.getByLabel("密码").fill(password);
  await page.getByRole("button", { name: "登录", exact: true }).click();
}

async function login(page, username = "user", password = "user123") {
  await expect.poll(async () => (
    await page.context().request.get("/api/auth/session")
  ).status()).toBe(401);
  await page.goto("/#/login");
  await page.getByLabel("用户名").fill(username);
  await page.getByLabel("密码").fill(password);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page).toHaveURL(/#\/$/);
  await page.goto("/#/workbench/c-draft-1");
  await expect(page).toHaveURL(/#\/workbench\/c-draft-1$/);
}

async function logoutAndWait(page) {
  await page.getByRole("button", { name: "退出登录" }).click();
  await expect(page).toHaveURL(/#\/login$/);
}

function lifecycleDocument(marker) {
  return {
    type: "doc",
    content: [
      { type: "heading", attrs: { level: 1 }, content: [{ type: "text", text: "一、教学说明" }] },
      { type: "paragraph", content: [{ type: "text", text: marker }] },
    ],
  };
}

async function createCase(request, marker) {
  const auth = await (await request.get("/api/auth/session")).json();
  const response = await request.post("/api/cases", {
    headers: { "X-CSRF-Token": auth.csrfToken },
    data: { title: marker, document: lifecycleDocument(marker) },
  });
  expect(response.ok()).toBe(true);
  return response.json();
}

async function uploadAttachment(request, caseId, level, name, content) {
  const auth = await (await request.get("/api/auth/session")).json();
  const current = await (await request.get(`/api/cases/${caseId}`)).json();
  const response = await request.post(`/api/cases/${caseId}/attachments`, {
    headers: { "X-CSRF-Token": auth.csrfToken },
    multipart: {
      accessLevel: level,
      revision: String(current.revision),
      file: { name, mimeType: "text/plain", buffer: Buffer.from(content) },
    },
  });
  expect(response.ok()).toBe(true);
  return response.json();
}

async function lifecycle(request, caseId, command, submittedVersionId) {
  const auth = await (await request.get("/api/auth/session")).json();
  const current = await (await request.get(`/api/cases/${caseId}`)).json();
  const response = await request.post(`/api/cases/${caseId}/lifecycle`, {
    headers: { "X-CSRF-Token": auth.csrfToken },
    data: { command, revision: current.revision, submittedVersionId },
  });
  expect(response.ok()).toBe(true);
  return response.json();
}

async function createPublishedCase(page, marker) {
  await login(page);
  const request = page.context().request;
  const created = await createCase(request, marker);
  const submitted = await lifecycle(request, created.id, "submit");
  await logoutAndWait(page);
  await login(page, "admin", "admin123");
  await lifecycle(request, created.id, "start");
  await lifecycle(request, created.id, "approve", submitted.version.id);
  return created;
}

function deferred() {
  let resolve;
  const promise = new Promise((done) => { resolve = done; });
  return { promise, resolve };
}

async function holdLifecycle(page, caseId, command) {
  const started = deferred();
  const release = deferred();
  await page.route(`**/api/cases/${caseId}/lifecycle`, async (route) => {
    if (route.request().postDataJSON()?.command !== command) return route.continue();
    started.resolve();
    await release.promise;
    await route.continue();
  });
  return { started: started.promise, release: release.resolve };
}

async function holdAttachmentUpload(page, caseId) {
  const started = deferred();
  const release = deferred();
  await page.route(`**/api/cases/${caseId}/attachments`, async (route) => {
    if (route.request().method() !== "POST") return route.continue();
    started.resolve();
    await release.promise;
    await route.continue();
  });
  return { started: started.promise, release: release.resolve };
}

async function expectMutationLocked(page, button, label) {
  await expect(button).toBeVisible();
  await expect(button).toBeDisabled();
  if (label) await expect(button).toHaveText(label);
  await expect(page.getByLabel("案例标题")).toHaveAttribute("readonly", "");
  await expect(page.locator(".canvas-editor")).toHaveAttribute("contenteditable", "false");
}

async function createManualSnapshot(page) {
  await page.getByRole("button", { name: "版本历史" }).click();
  await page.getByRole("button", { name: "创建快照" }).click();
  await expect(page.getByText("手动快照")).toBeVisible();
}

async function crashDraftValue(page, caseId) {
  const auth = await (await page.context().request.get("/api/auth/session")).json();
  const key = `case-library:crash-draft:${auth.user.id}:${caseId}`;
  return page.evaluate((draftKey) => localStorage.getItem(draftKey), key);
}

async function openAttachments(page) {
  await page.locator(".workspace-actions").getByRole("button", { name: "附件" }).click();
  await expect(page.locator(".assistant-rail")).toHaveClass(/open/);
}

async function restoreCase(request, original) {
  const session = await (await request.get("/api/auth/session")).json();
  const current = await (await request.get("/api/cases/c-draft-1")).json();
  await request.patch("/api/cases/c-draft-1", {
    headers: { "X-CSRF-Token": session.csrfToken },
    data: { title: original.title, document: original.document, revision: current.revision },
  });
}

async function capture(page, name) {
  const directory = process.env.PLAYWRIGHT_CAPTURE_DIR;
  if (!directory) return;
  await page.screenshot({ path: `${directory}/${name}.png`, fullPage: false });
}

async function expectOwnWorkbench(page) {
  const created = await createCase(page.context().request, `改密后案例 ${Date.now()}`);
  await page.goto(`/#/workbench/${created.id}`);
  await expect(page.getByLabel("案例标题")).toHaveValue(created.title);
}

async function downloadDocx(page) {
  const pending = page.waitForEvent("download");
  await page.getByRole("button", { name: "导出 DOCX" }).click();
  const download = await pending;
  const bytes = await readFile(await download.path());
  return { download, bytes };
}

async function editAndVerifyAutosave(page, request, marker) {
  await page.getByLabel("案例标题").fill(marker);
  await expect(page.locator(".save-state")).toHaveText(/未保存|保存中/);
  const { download } = await downloadDocx(page);
  expect(download.suggestedFilename()).toBe("case-c-draft-1.docx");
  await expect(page.locator(".save-state")).toHaveText("已保存", { timeout: 5000 });
  const saved = await (await request.get("/api/cases/c-draft-1")).json();
  expect(saved.title).toBe(marker);
  await page.reload();
  await expect(page.getByLabel("案例标题")).toHaveValue(marker);
  await capture(page, "workbench-desktop");
}

async function openMobileReview(page) {
  await page.setViewportSize({ width: 390, height: 844 });
  await login(page);
  const request = page.context().request;
  const created = await createCase(request, `手机审核 ${Date.now()}`);
  await lifecycle(request, created.id, "submit");
  await logoutAndWait(page);
  await login(page, "admin", "admin123");
  await lifecycle(request, created.id, "start");
  await page.goto(`/#/admin/review/${created.id}`);
}

async function buttonLayout(buttons) {
  return buttons.evaluateAll((rows) => rows.map((button) => ({
    left: button.getBoundingClientRect().left,
    right: button.getBoundingClientRect().right,
    clipped: button.scrollWidth > button.clientWidth || button.scrollHeight > button.clientHeight,
  })));
}

async function assertMiddleLayout(page) {
  await page.setViewportSize({ width: 1024, height: 768 });
  await expect(page.locator(".outline-wrap")).toBeHidden();
  const rail = await page.locator(".assistant-rail").boundingBox();
  const paper = await page.locator(".document-paper").boundingBox();
  expect(rail.width).toBeGreaterThanOrEqual(385);
  expect(rail.width).toBeLessThanOrEqual(395);
  expect(paper.x + paper.width).toBeLessThanOrEqual(rail.x);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(1024);
}

async function assertDesktopLayout(page) {
  await page.setViewportSize({ width: 1600, height: 1000 });
  await expect(page.locator(".outline-wrap")).toBeVisible();
  const rail = await page.locator(".assistant-rail").boundingBox();
  const paper = await page.locator(".document-paper").boundingBox();
  expect(rail.width).toBeGreaterThanOrEqual(415);
  expect(rail.width).toBeLessThanOrEqual(425);
  expect(paper.width).toBeLessThanOrEqual(900);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(1600);
  const items = page.locator(".outline-panel button:not(.outline-collapse)");
  const index = (await items.count()) - 1;
  const text = await items.nth(index).textContent();
  const headings = page.locator(".canvas-editor h1, .canvas-editor h2");
  expect(await headings.nth(index).textContent()).toBe(text.trim());
  await items.nth(index).click();
  await expect(headings.nth(index)).toBeInViewport();
}

async function seedCrashDraft(page, auth, original) {
  const key = `case-library:crash-draft:${auth.user.id}:c-draft-1`;
  const value = {
    userId: auth.user.id,
    caseId: "c-draft-1",
    baseRevision: original.revision,
    snapshot: { title: "浏览器恢复稿", document: original.document },
  };
  await page.evaluate(({ key, value }) => {
    localStorage.setItem(key, JSON.stringify(value));
  }, { key, value });
  return key;
}

async function assertCrashDraftRecovered(page, request, key) {
  await page.reload();
  await expect(page.getByLabel("案例标题")).toHaveValue("浏览器恢复稿");
  await expect(page.locator(".save-state")).toHaveText("已保存", { timeout: 5000 });
  expect((await (await request.get("/api/cases/c-draft-1")).json()).title).toBe("浏览器恢复稿");
  expect(await page.evaluate((draftKey) => localStorage.getItem(draftKey), key)).toBeNull();
}

async function submitCaseForReview(page, created, marker) {
  await page.goto(`/#/workbench/${created.id}`);
  await expect(page.getByLabel("案例标题")).toHaveValue(marker);
  await page.getByRole("button", { name: "提交审核" }).click();
  await expect(page.locator(".case-status")).toHaveText("待审");
  await expect(page.locator(".canvas-editor")).toHaveAttribute("contenteditable", "false");
}

async function approveCase(page, created, marker) {
  await logoutAndWait(page);
  await login(page, "admin", "admin123");
  await page.goto(`/#/admin/review/${created.id}`);
  await expect(page.getByLabel("案例标题")).toHaveValue(marker);
  await page.getByRole("button", { name: "开始审核" }).click();
  await expect(page.locator(".case-status")).toHaveText("审核中");
  await page.getByRole("button", { name: "通过发布" }).click();
  await expect(page.locator(".case-status")).toHaveText("已发布");
}

async function expectPublishedCase(page, created, marker) {
  await logoutAndWait(page);
  const response = await page.context().request.get(`/api/cases/${created.id}`);
  expect(response.ok()).toBe(true);
  expect(await response.json()).toMatchObject({
    title: marker,
    document: lifecycleDocument(marker),
    workflowStatus: "published",
    publicationStatus: "public",
  });
}

async function uploadWorkbenchEvidence(page) {
  await page.getByLabel("附件访问级别").selectOption("campus");
  await page.getByLabel("选择附件").setInputFiles({
    name: "课堂证据.txt", mimeType: "text/plain", buffer: Buffer.from("evidence"),
  });
  await expect(page.getByText("课堂证据.txt")).toBeVisible();
  await expect(page.getByRole("button", { name: "附件 1" })).toBeVisible();
  await expect(page.locator(".attachment-copy span")).toContainText("校内访问");
}

async function downloadAndDeleteEvidence(page) {
  const pending = page.waitForEvent("download");
  await page.getByRole("link", { name: "下载课堂证据.txt" }).click();
  expect((await readFile(await (await pending).path())).toString()).toBe("evidence");
  await page.getByRole("button", { name: "删除课堂证据.txt" }).click();
  await expect(page.getByText("课堂证据.txt")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "附件 0" })).toBeVisible();
}

async function publishCaseWithAttachments(page) {
  await login(page);
  const request = page.context().request;
  const created = await createCase(request, `公开附件 ${Date.now()}`);
  await uploadAttachment(request, created.id, "public", "公开材料.txt", "public");
  await uploadAttachment(request, created.id, "private", "内部材料.txt", "private");
  const submitted = await lifecycle(request, created.id, "submit");
  await logoutAndWait(page);
  await login(page, "admin", "admin123");
  await lifecycle(request, created.id, "start");
  await lifecycle(request, created.id, "approve", submitted.version.id);
  await logoutAndWait(page);
  return created;
}

async function assertAnonymousAttachmentAccess(page) {
  await expect(page.getByText("公开材料.txt")).toBeVisible();
  await expect(page.getByText("内部材料.txt")).toBeVisible();
  await expect(page.getByRole("link", { name: "下载公开材料.txt" })).toBeVisible();
  await expect(page.getByRole("link", { name: "下载内部材料.txt" })).toHaveCount(0);
  await expect(page.getByText("仅作者与管理员可下载")).toBeVisible();
  await expect(page.getByLabel("选择附件")).toHaveCount(0);
  await expect(page.locator(".workspace-header")).toHaveCount(0);
}

test("无自有案例的账号登录后从首页进入我的案例", async ({ page }) => {
  const initial = "Demo-10000002-2026!";
  const replacement = `Roster-Admin-${Date.now()}!`;
  await signInFromRoot(page, "10000002", initial);
  await page.getByLabel("当前密码").fill(initial);
  await page.getByLabel("新密码", { exact: true }).fill(replacement);
  await page.getByLabel("确认新密码").fill(replacement);
  await page.getByRole("button", { name: "保存新密码" }).click();

  await signInFromRoot(page, "10000002", replacement);

  await expect(page).toHaveURL(/#\/$/);
  await page.getByRole("link", { name: "我的案例", exact: true }).click();
  await expect(page).toHaveURL(/#\/my-cases$/);
  await expect(page.getByRole("heading", { name: "我的案例", exact: true })).toBeVisible();
});

test("强制改密页可以退出并切换账号", async ({ page }) => {
  await signIn(page, "10000001", "Demo-10000001-2026!");
  await expect(page).toHaveURL(/#\/change-password$/);

  await logoutAndWait(page);
  await login(page);
});

test("名单账号首登必须改密后才能进入工作台", async ({ page }) => {
  const initial = "Demo-10000001-2026!";
  const replacement = `Roster-Changed-${Date.now()}!`;
  await signIn(page, "10000001", initial);
  await expect(page).toHaveURL(/#\/change-password$/);
  await page.goto("/#/workbench/c-draft-1");
  await expect(page).toHaveURL(/#\/change-password$/);
  await page.getByLabel("当前密码").fill(initial);
  await page.getByLabel("新密码", { exact: true }).fill(replacement);
  await page.getByLabel("确认新密码").fill(replacement);
  await page.getByRole("button", { name: "保存新密码" }).click();
  await expect(page).toHaveURL(/#\/login$/);
  await signIn(page, "10000001", initial);
  await expect(page.getByRole("alert")).toContainText("用户名或密码错误");
  await signIn(page, "10000001", replacement);
  await expect(page).toHaveURL(/#\/$/);
  await expectOwnWorkbench(page);
});

test("作者登录后编辑案例，自动保存并在刷新后恢复", async ({ page }) => {
  await login(page);
  const request = page.context().request;
  const original = await (await request.get("/api/cases/c-draft-1")).json();
  const marker = `端到端保存 ${Date.now()}`;

  try {
    await editAndVerifyAutosave(page, request, marker);
  } finally {
    await restoreCase(request, original);
  }
});

test("客户端切换案例时重新绑定正文与草稿", async ({ page }) => {
  await login(page);
  const request = page.context().request;
  const first = await createCase(request, `路由案例一 ${Date.now()}`);
  const second = await createCase(request, `路由案例二 ${Date.now()}`);
  await page.goto(`/#/workbench/${first.id}`);
  await expect(page.getByLabel("案例标题")).toHaveValue(first.title);

  await page.evaluate((id) => { window.location.hash = `#/workbench/${id}`; }, second.id);

  await expect(page).toHaveURL(new RegExp(`#\\/workbench\\/${second.id}$`));
  await expect(page.getByLabel("案例标题")).toHaveValue(second.title);
});

test("旧标签页不会覆盖新的工作版本", async ({ page }) => {
  await login(page);
  const request = page.context().request;
  const original = await (await request.get("/api/cases/c-draft-1")).json();
  const auth = await (await request.get("/api/auth/session")).json();

  try {
    await request.patch("/api/cases/c-draft-1", {
      headers: { "X-CSRF-Token": auth.csrfToken },
      data: { title: `较新版本 ${Date.now()}`, revision: original.revision },
    });
    await page.getByLabel("案例标题").fill("旧页面内容");
    await expect(page.locator(".conflict-banner")).toContainText("本页内容尚未保存", { timeout: 5000 });
  } finally {
    await restoreCase(request, original);
  }
});

test("导出前保存当前正文并下载有效 DOCX", async ({ page }) => {
  await login(page);
  const request = page.context().request;
  const original = await (await request.get("/api/cases/c-draft-1")).json();
  const marker = `导出即时保存 ${Date.now()}`;

  try {
    await page.getByLabel("案例标题").fill(marker);
    const { download, bytes } = await downloadDocx(page);
    expect(download.suggestedFilename()).toBe("case-c-draft-1.docx");
    expect(bytes.subarray(0, 2).toString()).toBe("PK");
    await expect(page.locator(".save-state")).toHaveText("已保存");
    expect((await (await request.get("/api/cases/c-draft-1")).json()).title).toBe(marker);
  } finally {
    await restoreCase(request, original);
  }
});

test("手机工作台使用正文单栏和可收起辅助面板", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await login(page);

  await expect(page.locator(".document-paper")).toBeVisible();
  await expect(page.locator(".outline-wrap")).toBeHidden();
  await expect(page.locator(".assistant-rail")).not.toHaveClass(/open/);
  const titleBox = await page.locator(".document-title").boundingBox();
  const bylineBox = await page.locator(".document-byline").boundingBox();
  expect(titleBox.y + titleBox.height).toBeLessThanOrEqual(bylineBox.y + 1);

  await page.locator(".assistant-tabs").getByRole("button", { name: "AI", exact: true }).click();
  await expect(page.locator(".assistant-rail")).toHaveClass(/open/);
  await expect.poll(async () => (await page.locator(".assistant-rail").boundingBox())?.height).toBeGreaterThan(390);
  await capture(page, "workbench-mobile");
  await page.getByRole("button", { name: "收起面板" }).click();
  await expect(page.locator(".assistant-rail")).not.toHaveClass(/open/);
});

test("390px 审核头完整展示全部审核动作", async ({ page }) => {
  await openMobileReview(page);
  await expect(page.locator(".workspace-actions .lifecycle-action")).toHaveCount(3);
  const buttons = page.locator(".workspace-actions button:visible");
  const layout = await buttonLayout(buttons);
  expect(layout.every(({ left, right, clipped }) => left >= 0 && right <= 390 && !clipped)).toBe(true);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  await capture(page, "review-header-mobile");
});

test("手机端自动保存失败时显示明确警示", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await login(page);
  const created = await createCase(page.context().request, `保存失败 ${Date.now()}`);
  await page.goto(`/#/workbench/${created.id}`);
  await page.route(`**/api/cases/${created.id}`, async (route) => {
    if (route.request().method() !== "PATCH") return route.continue();
    await route.fulfill({ status: 503, contentType: "application/json", body: '{"detail":"服务暂不可用"}' });
  });

  await page.getByLabel("案例标题").fill("等待恢复的正文");

  await expect(page.getByRole("alert")).toContainText("自动保存失败", { timeout: 5000 });
});

test("中屏与桌面工作台保持约定列宽且无横向溢出", async ({ page }) => {
  await login(page);
  await assertMiddleLayout(page);
  await assertDesktopLayout(page);
});

test("浏览器重启后自动恢复同一基础修订的本地草稿", async ({ page }) => {
  await login(page);
  const request = page.context().request;
  const auth = await (await request.get("/api/auth/session")).json();
  const original = await (await request.get("/api/cases/c-draft-1")).json();

  try {
    const key = await seedCrashDraft(page, auth, original);
    await assertCrashDraftRecovered(page, request, key);
  } finally {
    await restoreCase(request, original);
  }
});

test("作者提交的冻结版本经管理员审核后向匿名用户发布", async ({ page }) => {
  await login(page);
  const marker = `审核发布 ${Date.now()}`;
  const created = await createCase(page.context().request, marker);
  await submitCaseForReview(page, created, marker);
  await approveCase(page, created, marker);
  await expectPublishedCase(page, created, marker);
});

test("提交请求在途锁定编辑器并保留提交前正文", async ({ page }) => {
  await login(page);
  const marker = `提交在途 ${Date.now()}`;
  const created = await createCase(page.context().request, marker);
  await page.goto(`/#/workbench/${created.id}`);
  const held = await holdLifecycle(page, created.id, "submit");
  await page.getByLabel("案例标题").fill(`${marker} 已编辑`);
  const submit = page.getByRole("button", { name: "提交审核" });
  await submit.click();
  try {
    await expectMutationLocked(page, submit, "处理中");
    await held.started;
  } finally { held.release(); }
  await expect(page.locator(".case-status")).toHaveText("待审");
  await expect(page.getByLabel("案例标题")).toHaveValue(`${marker} 已编辑`);
  await expect.poll(() => crashDraftValue(page, created.id)).toBeNull();
});

test("附件请求在途锁定正文避免与自动保存竞争", async ({ page }) => {
  await login(page);
  const created = await createCase(page.context().request, `附件互斥 ${Date.now()}`);
  await page.goto(`/#/workbench/${created.id}`);
  await openAttachments(page);
  const held = await holdAttachmentUpload(page, created.id);

  await page.getByLabel("选择附件").setInputFiles({
    name: "互斥验证.txt", mimeType: "text/plain", buffer: Buffer.from("locked"),
  });
  await held.started;
  try {
    await expect(page.getByLabel("案例标题")).toHaveAttribute("readonly", "");
    await expect(page.locator(".canvas-editor")).toHaveAttribute("contenteditable", "false");
  } finally { held.release(); }
  await expect(page.getByText("互斥验证.txt")).toBeVisible();
});

test("作者在草稿工作台上传、下载并删除附件", async ({ page }) => {
  await login(page);
  const created = await createCase(page.context().request, `附件工作台 ${Date.now()}`);
  await page.goto(`/#/workbench/${created.id}`);
  await openAttachments(page);
  await uploadWorkbenchEvidence(page);
  await downloadAndDeleteEvidence(page);
});

test("公开详情按作者和匿名权限展示私密附件", async ({ page }) => {
  const created = await publishCaseWithAttachments(page);
  await login(page);
  await page.goto(`/#/cases/${created.id}`);
  await expect(page.getByRole("link", { name: "下载内部材料.txt" })).toBeVisible();
  await logoutAndWait(page);
  await page.goto(`/#/cases/${created.id}`);
  await expect(page.getByRole("heading", { level: 1, name: created.title })).toBeVisible();
  await assertAnonymousAttachmentAccess(page);
});

test("管理员可隐藏并恢复同一公开版本", async ({ page }) => {
  const created = await createPublishedCase(page, `隐藏恢复 ${Date.now()}`);
  await page.goto(`/#/admin/review/${created.id}`);

  await page.getByRole("button", { name: "暂时隐藏" }).click();
  await expect(page.locator(".case-status")).toHaveText("已隐藏");
  await expect(page.getByRole("button", { name: "恢复公开" })).toBeVisible();
  await page.getByRole("button", { name: "恢复公开" }).click();

  await expect(page.locator(".case-status")).toHaveText("已发布");
  await expect(page.getByRole("button", { name: "暂时隐藏" })).toBeVisible();
});

test("管理员下线隐藏案例后作者才能继续编辑", async ({ page }) => {
  const created = await createPublishedCase(page, `下线编辑 ${Date.now()}`);
  await page.goto(`/#/admin/review/${created.id}`);
  await page.getByRole("button", { name: "暂时隐藏" }).click();
  const reopened = page.waitForResponse((response) => (
    response.url().endsWith(`/api/cases/${created.id}/lifecycle`)
      && response.request().postDataJSON()?.command === "reopen"
  ));
  await page.getByRole("button", { name: "下线编辑" }).click();
  expect((await reopened).ok()).toBe(true);

  const current = await (await page.context().request.get(`/api/cases/${created.id}`)).json();
  expect(current.workflowStatus).toBe("draft");
  expect(current.publicationStatus).toBe("hidden");
  await expect(page.getByLabel("案例标题")).toHaveAttribute("readonly", "");
});

test("作者创建工作快照并回滚正文", async ({ page }) => {
  await login(page);
  const marker = `版本快照 ${Date.now()}`;
  const created = await createCase(page.context().request, marker);
  await page.goto(`/#/workbench/${created.id}`);
  await page.getByRole("button", { name: "版本历史" }).click();
  await page.getByRole("button", { name: "创建快照" }).click();
  await expect(page.getByText("手动快照")).toBeVisible();

  await page.getByLabel("案例标题").fill("回滚前修改");
  await expect(page.locator(".save-state")).toHaveText("已保存", { timeout: 5000 });
  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "回滚到手动快照" }).click();

  await expect(page.getByLabel("案例标题")).toHaveValue(marker);
  await expect(page.getByText("回滚前快照")).toBeVisible();
});

test("回滚请求在途锁定编辑器且按钮立即进入 busy", async ({ page }) => {
  await login(page);
  const marker = `回滚在途 ${Date.now()}`;
  const created = await createCase(page.context().request, marker);
  await page.goto(`/#/workbench/${created.id}`);
  await createManualSnapshot(page);
  const rollback = page.getByRole("button", { name: "回滚到手动快照" });
  const held = await holdLifecycle(page, created.id, "rollback");
  await page.getByLabel("案例标题").fill(`${marker} 已编辑`);
  page.once("dialog", (dialog) => dialog.accept());
  await rollback.click();
  try {
    await expectMutationLocked(page, rollback);
    await held.started;
  } finally { held.release(); }
  await expect(page.getByLabel("案例标题")).toHaveValue(marker);
  await expect(page.getByText("回滚前快照")).toBeVisible();
  await expect.poll(() => crashDraftValue(page, created.id)).toBeNull();
});
