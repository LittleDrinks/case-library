import { expect, test } from "@playwright/test";

async function login(page, username, password) {
  await page.goto("/#/login");
  await page.getByLabel("用户名").fill(username);
  await page.getByLabel("密码").fill(password);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page).toHaveURL(/#\/$/);
  await expect(page.getByRole("button", { name: "退出登录" })).toBeVisible();
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

async function lifecycle(request, caseId, auth, command, revision, extra = {}) {
  const response = await request.post(`/api/cases/${caseId}/lifecycle`, {
    headers: { "X-CSRF-Token": auth.csrfToken },
    data: { command, revision, ...extra },
  });
  expect(response.status()).toBe(200);
  return response.json();
}

test("管理员作者在工作台读取本人私稿批注", async ({ page }) => {
  const request = page.context().request;
  const marker = `管理员作者私稿 ${Date.now()}`;
  await login(page, "admin", "admin123");
  const created = await createCase(request, marker);
  const auth = await session(request);
  const noteContent = `仅作者可见的批注 ${marker}`;
  const note = await request.post(`/api/cases/${created.id}/annotations`, {
    headers: { "X-CSRF-Token": auth.csrfToken },
    data: {
      quote: marker,
      section: "正文",
      content: noteContent,
      source: "manual",
      revision: created.revision,
      from: 1,
      to: marker.length + 1,
    },
  });
  expect(note.status()).toBe(201);

  const listResponse = page.waitForResponse((response) => (
    response.url().includes(`/api/cases/${created.id}/annotations`)
    && response.request().method() === "GET"
  ));
  await page.goto(`/#/workbench/${created.id}`);
  const listed = await listResponse;
  expect(listed.status()).toBe(200);
  await page.getByRole("button", { name: "指导批注", exact: true }).click();
  await expect(page.getByText(noteContent, { exact: true })).toBeVisible();
});

test("作者提交后仍使用本人未绑定版本的对话", async ({ page }) => {
  const request = page.context().request;
  const marker = `管理员作者对话 ${Date.now()}`;
  await login(page, "admin", "admin123");
  const created = await createCase(request, marker);
  const threadScopes = [];
  page.on("request", (pending) => {
    const url = new URL(pending.url());
    if (url.pathname === `/api/cases/${created.id}/agent/thread`) {
      threadScopes.push({
        versionId: url.searchParams.get("versionId"),
        mode: url.searchParams.get("mode"),
      });
    }
  });
  const initialThread = page.waitForResponse((response) => {
    const url = new URL(response.url());
    return url.pathname === `/api/cases/${created.id}/agent/thread`;
  });
  await page.goto(`/#/workbench/${created.id}`);
  const thread = await initialThread;
  expect(thread.status()).toBe(200);
  expect(new URL(thread.url()).searchParams.has("versionId")).toBe(false);
  expect(new URL(thread.url()).searchParams.has("mode")).toBe(false);

  await page.getByRole("button", { name: "提交审核", exact: true }).click();
  await expect(page.locator(".case-status")).toHaveText("待审");
  expect(threadScopes.length).toBeGreaterThan(0);
  expect(threadScopes.every((scope) => !scope.versionId && !scope.mode)).toBe(true);
  await expect(page.getByText("案例版本不存在", { exact: true })).toHaveCount(0);
});

test("管理员作者从已发布版本另开新稿后进入本人私稿工作台", async ({ page }) => {
  const request = page.context().request;
  const marker = `管理员作者重开 ${Date.now()}`;
  await login(page, "admin", "admin123");
  const created = await createCase(request, marker);
  const auth = await session(request);
  const submitted = await lifecycle(request, created.id, auth, "submit", created.revision);
  const started = await lifecycle(
    request, created.id, auth, "start", submitted.case.revision,
  );
  await lifecycle(
    request,
    created.id,
    auth,
    "approve",
    started.case.revision,
    { submittedVersionId: submitted.version.id },
  );

  await page.goto(`/#/admin/review/${created.id}?versionId=${submitted.version.id}`);
  await expect(page.getByRole("button", { name: "另开新稿", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "另开新稿", exact: true }).click();

  await expect(page).toHaveURL(new RegExp(`#\\/workbench\\/${created.id}$`));
  await expect(page.locator(".case-status")).toHaveText("草稿 · 旧版公开中");
  await page.getByRole("button", { name: "附件", exact: true }).click();
  const privateFileName = `管理员作者私稿资料 ${Date.now()}.txt`;
  await page.getByLabel("选择附件").setInputFiles({
    name: privateFileName,
    mimeType: "text/plain",
    buffer: Buffer.from(`private material ${marker}`),
  });
  await page.getByRole("button", { name: /^来源 / }).click();
  await expect(page.getByText(new RegExp(privateFileName))).toBeVisible();
});
