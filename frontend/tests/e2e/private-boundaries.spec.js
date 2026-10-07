import { expect, test } from "@playwright/test";

async function login(page, username, password) {
  await page.goto("/#/login");
  await page.getByLabel("用户名").fill(username);
  await page.getByLabel("密码").fill(password);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page).toHaveURL(/#\/$/);
  await expect(page.getByRole("button", { name: "退出登录" })).toBeVisible();
}

async function logout(page) {
  await page.goto("/#/");
  await page.getByRole("button", { name: "退出登录" }).click();
  await expect(page).toHaveURL(/#\/login$/);
}

async function session(request) {
  return (await request.get("/api/auth/session")).json();
}

async function createCase(request, title) {
  const auth = await session(request);
  const response = await request.post("/api/cases", {
    headers: { "X-CSRF-Token": auth.csrfToken },
    data: {
      title,
      document: {
        type: "doc",
        content: [{ type: "paragraph", content: [{ type: "text", text: title }] }],
      },
    },
  });
  expect(response.status()).toBe(200);
  return response.json();
}

async function submit(request, caseId) {
  const auth = await session(request);
  const current = await (await request.get(`/api/cases/${caseId}`)).json();
  const response = await request.post(`/api/cases/${caseId}/lifecycle`, {
    headers: { "X-CSRF-Token": auth.csrfToken },
    data: { command: "submit", revision: current.revision },
  });
  expect(response.status()).toBe(200);
  return response.json();
}

async function lifecycle(request, caseId, auth, command, revision, extra = {}) {
  const response = await request.post(`/api/cases/${caseId}/lifecycle`, {
    headers: { "X-CSRF-Token": auth.csrfToken },
    data: { command, revision, ...extra },
  });
  expect(response.status()).toBe(200);
  return response.json();
}

async function selectReviewText(page, marker) {
  await page.locator(".canvas-editor p").filter({ hasText: marker }).selectText();
  await expect(page.getByRole("button", { name: "添加指导批注" })).toBeVisible();
}

async function addGuidance(page, marker, content) {
  await selectReviewText(page, marker);
  await page.getByRole("button", { name: "添加指导批注" }).click();
  const float = page.getByRole("dialog", { name: "批注浮窗" });
  await float.getByLabel("批注内容").fill(content);
  await Promise.all([
    page.waitForResponse((response) => (
      response.url().includes("/annotations")
      && response.request().method() === "POST"
      && response.status() === 201
    )),
    float.getByRole("button", { name: "保存意见" }).click(),
  ]);
  await expect(float.getByText(content, { exact: true })).toBeVisible();
  await float.getByRole("button", { name: "关闭批注浮窗" }).click();
}

test("作者私稿只在作者入口可读，管理员按冻结投稿审核", async ({ page }) => {
  const request = page.context().request;
  const marker = `私人边界 ${Date.now()}`;
  await login(page, "user", "user123");
  const created = await createCase(request, marker);
  await page.goto(`/#/workbench/${created.id}`);
  await expect(page.getByLabel("案例标题")).toHaveValue(marker);

  await logout(page);
  await login(page, "admin", "admin123");
  for (const path of [
    `/api/cases/${created.id}`,
    `/api/cases/${created.id}/history`,
    `/api/cases/${created.id}/attachments`,
    `/api/cases/${created.id}/export.docx`,
    `/api/cases/${created.id}/agent/thread`,
  ]) {
    expect((await request.get(path)).status()).toBeGreaterThanOrEqual(400);
  }
  await page.goto(`/#/admin/review/${created.id}`);
  await expect(page.locator(".error-state")).toBeVisible();

  await logout(page);
  await login(page, "user", "user123");
  const attachmentAuth = await session(request);
  const ownerCase = await (await request.get(`/api/cases/${created.id}`)).json();
  const attachmentResponse = await request.post(`/api/cases/${created.id}/attachments`, {
    headers: { "X-CSRF-Token": attachmentAuth.csrfToken },
    multipart: {
      accessLevel: "private",
      revision: String(ownerCase.revision),
      file: { name: "synthetic-private.txt", mimeType: "text/plain", buffer: Buffer.from(`secret ${marker}`) },
    },
  });
  expect(attachmentResponse.status()).toBe(201);
  const attachment = await attachmentResponse.json();
  const currentCase = await (await request.get(`/api/cases/${created.id}`)).json();
  const publicAttachmentResponse = await request.post(`/api/cases/${created.id}/attachments`, {
    headers: { "X-CSRF-Token": attachmentAuth.csrfToken },
    multipart: {
      accessLevel: "public",
      revision: String(currentCase.revision),
      file: { name: "synthetic-public.txt", mimeType: "text/plain", buffer: Buffer.from(`public ${marker}`) },
    },
  });
  expect(publicAttachmentResponse.status()).toBe(201);
  const publicAttachment = await publicAttachmentResponse.json();

  await page.goto(`/#/workbench/${created.id}`);
  await page.getByRole("button", { name: "提交审核", exact: true }).click();
  await expect(page.locator(".case-status")).toHaveText("待审");
  const submittedCase = await (await request.get(`/api/cases/${created.id}`)).json();
  const firstVersionId = submittedCase.submittedVersionId;
  expect(firstVersionId).toBeTruthy();
  await logout(page);
  await login(page, "admin", "admin123");
  const reviewAgentResponse = page.waitForResponse((response) => {
    const url = new URL(response.url());
    return url.pathname.endsWith(`/api/cases/${created.id}/agent/thread`)
      && url.searchParams.get("versionId") === firstVersionId
      && url.searchParams.get("mode") === "review";
  });
  await page.goto(`/#/admin/review/${created.id}`);
  expect((await reviewAgentResponse).status()).toBe(200);
  await page.getByRole("button", { name: "开始审核", exact: true }).click();
  await expect(page.locator(".case-status")).toHaveText("审核中");
  await expect(page.getByLabel("案例标题")).toHaveValue(marker);
  await expect(page.locator(".canvas-editor")).toContainText(marker);
  await page.getByRole("button", { name: "附件", exact: true }).click();
  const attachmentPanel = page.locator(".attachment-panel");
  await expect(attachmentPanel.getByText("synthetic-private.txt", { exact: true })).toBeVisible();
  const publicDownload = attachmentPanel.getByRole("link", { name: "下载synthetic-public.txt" });
  await expect(publicDownload).toBeVisible();
  const publicDownloadUrl = new URL(await publicDownload.getAttribute("href"), page.url());
  expect(publicDownloadUrl.searchParams.get("versionId")).toBe(firstVersionId);
  const publicDownloadResponse = await request.get(publicDownloadUrl.toString());
  expect(publicDownloadResponse.status()).toBe(200);
  expect(await publicDownloadResponse.body()).toEqual(Buffer.from(`public ${marker}`));
  await expect(attachmentPanel.getByRole("link", { name: "下载synthetic-private.txt" })).toHaveCount(0);
  await expect(attachmentPanel.getByText("仅作者可下载", { exact: false })).toBeVisible();
  const adminAuth = await session(request);
  const privateContent = await request.get(
    `/api/cases/${created.id}/attachments/${attachment.id}/content?versionId=${firstVersionId}`,
  );
  expect(privateContent.status()).toBe(403);
  await page.getByRole("button", { name: "指导批注", exact: true }).click();
  await addGuidance(page, marker, "请补充教学目标");
  await addGuidance(page, marker, "请核实资料来源");

  await logout(page);
  await login(page, "user", "user123");
  await page.goto(`/#/workbench/${created.id}`);
  await page.getByRole("button", { name: "撤回提交", exact: true }).click();
  await expect(page.locator(".case-status")).toHaveText("草稿");
  await page.getByLabel("案例标题").fill(`${marker} 修改稿`);
  await expect(page.locator(".save-state")).toHaveText("已保存", { timeout: 10000 });
  const savedDraft = await (await request.get(`/api/cases/${created.id}`)).json();
  expect(savedDraft.title).toBe(`${marker} 修改稿`);

  await logout(page);
  await login(page, "admin", "admin123");
  await page.goto("/#/admin");
  const withdrawnRow = page.locator(`article[aria-label="已撤回：${marker}"]`);
  await expect(withdrawnRow).toBeVisible();
  await withdrawnRow.getByRole("link", { name: "查看记录" }).click();
  await expect(page).toHaveURL(new RegExp(`versionId=${firstVersionId}`));
  await expect(page.getByText("该版本已被作者撤回").first()).toBeVisible();
  await expect(page.getByLabel("案例标题")).toHaveValue(marker);
  await expect(page.locator(".canvas-editor")).not.toContainText(`${marker} 修改稿`);
  await expect(page.getByRole("button", { name: "通过发布", exact: true })).toHaveCount(0);
  expect((await request.get(`/api/cases/${created.id}`)).status()).toBe(404);
  expect((await request.get(`/api/cases/${created.id}/review`)).status()).toBe(404);
  const frozen = await (await request.get(
    `/api/cases/${created.id}/review?versionId=${firstVersionId}`,
  )).json();
  expect(frozen.reviewRecordStatus).toBe("withdrawn");
  const replay = await request.post(`/api/cases/${created.id}/lifecycle`, {
    headers: { "X-CSRF-Token": adminAuth.csrfToken },
    data: {
      command: "approve",
      revision: frozen.revision,
      submittedVersionId: firstVersionId,
    },
  });
  expect(replay.status()).toBeGreaterThanOrEqual(400);
  expect(replay.status()).toBeLessThan(500);
  await page.getByRole("button", { name: "指导批注", exact: true }).click();
  await expect(page.getByText("请补充教学目标", { exact: true })).toBeVisible();
  await expect(page.getByText("请核实资料来源", { exact: true })).toBeVisible();
  await addGuidance(page, marker, "撤回后继续补充这一点");

  await logout(page);
  await login(page, "user", "user123");
  await page.goto(`/#/workbench/${created.id}`);
  await page.getByRole("button", { name: "历史版本", exact: true }).click();
  await page.getByRole("button", { name: "查看 v1 指导批注" }).click();
  await expect(page.locator(".canvas-editor")).toContainText(marker);
  await expect(page.getByText("请补充教学目标", { exact: true })).toBeVisible();
  await expect(page.getByText("请核实资料来源", { exact: true })).toBeVisible();
  await expect(page.getByText("撤回后继续补充这一点", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "返回当前教师稿", exact: true }).click();
  await page.getByRole("button", { name: "提交审核", exact: true }).click();
  await expect(page.locator(".case-status")).toHaveText("待审");

  await logout(page);
  await login(page, "admin", "admin123");
  await page.goto("/#/admin");
  const pendingRow = page.locator(`article[aria-label="待审核：${marker} 修改稿"]`);
  await expect(pendingRow).toBeVisible();
  await expect(page.locator(`article[aria-label="已撤回：${marker}"]`)).toBeVisible();
  await pendingRow.getByRole("link", { name: "审核" }).click();
  await expect(page.getByLabel("案例标题")).toHaveValue(`${marker} 修改稿`);
  expect((await request.get(`/api/cases/${created.id}/review`)).status()).toBe(200);
  const currentVersionId = (await (await request.get(`/api/cases/${created.id}/review`)).json()).submittedVersionId;
  expect(currentVersionId).not.toBe(firstVersionId);
  await page.getByRole("button", { name: "历史版本", exact: true }).click();
  await page.getByRole("button", { name: "查看 v1 指导批注" }).click();
  await expect(page.getByText("该版本已被作者撤回").first()).toBeVisible();
  await expect(page.getByLabel("案例标题")).toHaveValue(marker);
  expect((await request.get(
    `/api/cases/${created.id}/review?versionId=${firstVersionId}`,
  )).status()).toBe(200);

  const currentAdminAuth = await session(request);
  const currentReview = await (await request.get(`/api/cases/${created.id}/review`)).json();
  const startCurrent = await request.post(`/api/cases/${created.id}/lifecycle`, {
    headers: { "X-CSRF-Token": currentAdminAuth.csrfToken },
    data: { command: "start", revision: currentReview.revision },
  });
  expect(startCurrent.status()).toBe(200);
  const approveCurrent = await request.post(`/api/cases/${created.id}/lifecycle`, {
    headers: { "X-CSRF-Token": currentAdminAuth.csrfToken },
    data: {
      command: "approve",
      revision: (await startCurrent.json()).case.revision,
      submittedVersionId: currentVersionId,
    },
  });
  expect(approveCurrent.status()).toBe(200);
  await page.goto("/#/admin");
  await expect(page.locator(`article[aria-label="已发布：${marker} 修改稿"]`)).toBeVisible();
  await expect(page.locator(`article[aria-label="已发布：${marker}"]`)).toHaveCount(0);
  await expect(page.locator(`article[aria-label="已撤回：${marker}"]`)).toBeVisible();
  const publicConversation = page.waitForResponse((response) => {
    const url = new URL(response.url());
    return url.pathname === `/api/cases/${created.id}/agent/thread`
      && url.searchParams.get("versionId") === currentVersionId
      && !url.searchParams.has("mode");
  });
  await page.goto(`/#/cases/${created.id}`);
  expect((await publicConversation).status()).toBe(200);
});

test("作者重开并重投后，管理员仍可只读已发布旧版审核记录", async ({ page }) => {
  const request = page.context().request;
  const marker = `已发布旧审核记录 ${Date.now()}`;
  await login(page, "user", "user123");
  const created = await createCase(request, marker);
  const firstSubmission = await submit(request, created.id);
  const firstVersionId = firstSubmission.version.id;

  await logout(page);
  await login(page, "admin", "admin123");
  const reviewerAuth = await session(request);
  let review = await request.get(`/api/cases/${created.id}/review`);
  const started = await lifecycle(
    request, created.id, reviewerAuth, "start", (await review.json()).revision,
  );
  const guidance = `v1 审核意见 ${marker}`;
  const annotation = await request.post(
    `/api/cases/${created.id}/annotations?versionId=${firstVersionId}`,
    {
      headers: { "X-CSRF-Token": reviewerAuth.csrfToken },
      data: {
        quote: marker,
        section: "正文",
        content: guidance,
        source: "admin",
        revision: started.case.revision,
        from: 1,
        to: marker.length + 1,
      },
    },
  );
  expect(annotation.status()).toBe(201);
  review = await request.get(
    `/api/cases/${created.id}/review?versionId=${firstVersionId}`,
  );
  await lifecycle(
    request,
    created.id,
    reviewerAuth,
    "approve",
    (await review.json()).revision,
    { submittedVersionId: firstVersionId },
  );

  await logout(page);
  await login(page, "user", "user123");
  const ownerAuth = await session(request);
  const ownerCase = await (await request.get(`/api/cases/${created.id}`)).json();
  const reopened = await lifecycle(
    request, created.id, ownerAuth, "reopen", ownerCase.revision,
  );
  const draftTitle = `${marker} v2 私稿`;
  const changed = await request.patch(`/api/cases/${created.id}`, {
    headers: { "X-CSRF-Token": ownerAuth.csrfToken },
    data: { title: draftTitle, revision: reopened.case.revision },
  });
  expect(changed.status()).toBe(200);
  const secondSubmission = await submit(request, created.id);
  const secondVersionId = secondSubmission.version.id;
  expect(secondVersionId).not.toBe(firstVersionId);

  await logout(page);
  await login(page, "admin", "admin123");
  const oldReviewResponse = await request.get(
    `/api/cases/${created.id}/review?versionId=${firstVersionId}`,
  );
  expect(oldReviewResponse.status()).toBe(200);
  const oldReview = await oldReviewResponse.json();
  expect(oldReview).toMatchObject({
    reviewVersionId: firstVersionId,
    reviewRecordStatus: "published",
    isCurrentReviewVersion: false,
    availableActions: [],
  });
  expect(oldReview.title).toBe(marker);
  expect(JSON.stringify(oldReview)).not.toContain(draftTitle);
  expect((await (await request.get(`/api/cases/${created.id}/public`)).json()).title)
    .toBe(marker);

  await page.goto(`/#/admin/review/${created.id}?versionId=${firstVersionId}`);
  await expect(page.getByLabel("案例标题")).toHaveValue(marker);
  await expect(page.locator(".case-status")).toHaveText("已发布 · 历史审核");
  await expect(page.locator(".canvas-editor")).toContainText(marker);
  await expect(page.locator(".canvas-editor")).not.toContainText(draftTitle);
  for (const label of ["开始审核", "通过发布", "退回修改"]) {
    await expect(page.getByRole("button", { name: label, exact: true })).toHaveCount(0);
  }
  await page.getByRole("button", { name: "指导批注", exact: true }).click();
  await expect(page.getByText(guidance, { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "回复", exact: true })).toHaveCount(0);

  const currentReview = await (await request.get(`/api/cases/${created.id}/review`)).json();
  expect(currentReview.submittedVersionId).toBe(secondVersionId);
  await page.goto(`/#/admin/review/${created.id}`);
  await expect(page.getByLabel("案例标题")).toHaveValue(draftTitle);
  await expect(page.locator(".case-status")).toHaveText("待审 · 旧版公开中");
});

test("作者手动历史版本显示冻结私批注并禁用修改", async ({ page }) => {
  const request = page.context().request;
  const marker = `手动历史批注 ${Date.now()}`;
  const annotationText = `冻结私批注 ${marker}`;
  const replyText = `冻结回复 ${marker}`;
  const liveText = `当前私批注 ${marker}`;
  await login(page, "user", "user123");
  const created = await createCase(request, marker);
  const ownerAuth = await session(request);
  const annotationResponse = await request.post(
    `/api/cases/${created.id}/annotations`,
    {
      headers: { "X-CSRF-Token": ownerAuth.csrfToken },
      data: {
        quote: marker,
        section: "正文",
        content: annotationText,
        source: "manual",
        revision: created.revision,
        from: 1,
        to: marker.length + 1,
      },
    },
  );
  expect(annotationResponse.status()).toBe(201);
  const annotation = await annotationResponse.json();
  const replyResponse = await request.post(
    `/api/cases/${created.id}/annotations/${annotation.id}/replies`,
    {
      headers: { "X-CSRF-Token": ownerAuth.csrfToken },
      data: { content: replyText },
    },
  );
  expect(replyResponse.status()).toBe(200);
  const current = await (await request.get(`/api/cases/${created.id}`)).json();
  const versionResponse = await request.post(`/api/cases/${created.id}/versions`, {
    headers: { "X-CSRF-Token": ownerAuth.csrfToken },
    data: { title: `${marker} v1`, revision: current.revision },
  });
  expect(versionResponse.status()).toBe(200);
  const version = await versionResponse.json();

  const liveEdit = await request.patch(
    `/api/cases/${created.id}/annotations/${annotation.id}`,
    {
      headers: { "X-CSRF-Token": ownerAuth.csrfToken },
      data: { content: liveText },
    },
  );
  expect(liveEdit.status()).toBe(200);

  await page.goto(`/#/workbench/${created.id}`);
  await expect(page.getByLabel("案例标题")).toHaveValue(marker);
  await page.getByRole("button", { name: "历史版本", exact: true }).click();
  await page.getByRole("button", { name: /查看历史版本/ }).click();
  await expect(page.locator(".canvas-editor")).toContainText(marker);
  await page.getByRole("button", { name: "指导批注", exact: true }).click();
  await expect(page.getByText(annotationText, { exact: true })).toBeVisible();
  await expect(page.getByText(replyText, { exact: true })).toBeVisible();
  await expect(page.getByText(liveText, { exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "编辑批注", exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "回复", exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "标记解决", exact: true })).toHaveCount(0);

  const frozenAnnotations = await (await request.get(
    `/api/cases/${created.id}/annotations?versionId=${version.id}`,
  )).json();
  const liveAnnotations = await (await request.get(
    `/api/cases/${created.id}/annotations`,
  )).json();
  expect(frozenAnnotations[0].content).toBe(annotationText);
  expect(frozenAnnotations[0].replies[0].content).toBe(replyText);
  expect(liveAnnotations.find(({ id }) => id === annotation.id).content).toBe(liveText);
});
