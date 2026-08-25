import { expect, test } from "@playwright/test";
import { readFile } from "node:fs/promises";

async function login(page, username, password) {
  await expect.poll(async () => (
    await page.context().request.get("/api/auth/session")
  ).status()).toBe(401);
  await page.goto("/#/workbench/c-draft-1");
  await page.getByLabel("用户名").fill(username);
  await page.getByLabel("密码").fill(password);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page).toHaveURL(workbenchRoute(username));
}

function workbenchRoute(username) {
  return username === "admin" ? /#\/admin\/review\/c-draft-1$/ : /#\/workbench\/c-draft-1$/;
}

function upload(name, content) {
  return { name, mimeType: "text/plain", buffer: Buffer.from(content) };
}

async function submitFiles(page, files) {
  const response = page.waitForResponse(importResponse);
  await page.getByLabel("选择资料").setInputFiles(files);
  await page.getByRole("button", { name: "开始导入" }).click();
  expect((await response).ok()).toBe(true);
}

function importResponse(response) {
  const url = new URL(response.url());
  return url.pathname === "/api/admin/material-imports"
    && response.request().method() === "POST";
}

function deferred() {
  let resolve;
  const promise = new Promise((ready) => { resolve = ready; });
  return { promise, resolve };
}

async function pauseImport(page, path, started, release) {
  await page.route(path, async (route) => {
    started.resolve();
    await release.promise;
    await route.continue();
  });
}

async function openAdminImport(page) {
  await page.goto("/#/admin/material-imports");
  await page.getByLabel("用户名").fill("admin");
  await page.getByLabel("密码").fill("admin123");
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page).toHaveURL(/#\/admin\/material-imports$/);
  await expect(page.getByLabel("素材访问级别")).toHaveValue("campus");
}

async function approveCandidate(page, filename, title) {
  const row = page.getByRole("article", { name: `待审核：${filename}` });
  await expect(row).toBeVisible();
  await row.getByLabel(`素材标题：${filename}`).fill(title);
  await row.getByLabel(`批准入库：${filename}`).click();
  await expect(page.getByRole("status")).toContainText(`已批准入库：${title}`);
  await expect(row).toHaveCount(0);
}

async function rejectCandidate(page, filename) {
  const row = page.getByRole("article", { name: `待审核：${filename}` });
  await row.getByLabel(`拒绝候选：${filename}`).click();
  await expect(page.getByRole("status")).toContainText(`已拒绝：${filename}`);
  await expect(row).toHaveCount(0);
}

async function loginTeacher(page) {
  await logoutAndWait(page);
  await page.getByLabel("用户名").fill("user");
  await page.getByLabel("密码").fill("user123");
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page.getByRole("button", { name: "退出登录" })).toBeVisible();
}

async function logoutAndWait(page) {
  await page.getByRole("button", { name: "退出登录" }).click();
  await expect(page).toHaveURL(/#\/login$/);
}

async function createDraft(request, title) {
  const auth = await readOkJson(await request.get("/api/auth/session"));
  return readOkJson(await request.post("/api/cases", {
    headers: { "X-CSRF-Token": auth.csrfToken }, data: { title },
  }));
}

async function clearCaseMaterials(request, caseId) {
  const auth = await (await request.get("/api/auth/session")).json();
  let record = await readOkJson(await request.get(`/api/cases/${caseId}`));
  const rows = await readArray(await request.get(`/api/cases/${caseId}/materials`));
  for (const row of rows) {
    const response = await request.delete(
      `/api/cases/${caseId}/materials/${encodeURIComponent(row.id)}?revision=${record.revision}`,
      { headers: { "X-CSRF-Token": auth.csrfToken } },
    );
    expect(response.ok()).toBe(true);
    record = await readOkJson(await request.get(`/api/cases/${caseId}`));
  }
}

async function readOkJson(response) {
  const failure = response.ok() ? "" : await response.text();
  expect(response.ok(), failure).toBe(true);
  return response.json();
}

async function readArray(response) {
  const payload = await readOkJson(response);
  expect(Array.isArray(payload)).toBe(true);
  return payload;
}

async function waitForSearchMaterial(request, title) {
  await expect.poll(async () => {
    const response = await request.get("/api/search", {
      params: { q: title, kind: "material", pageSize: 50 },
    });
    if (!response.ok()) return false;
    return (await response.json()).items.some((item) => item.title === title);
  }, { timeout: 15_000 }).toBe(true);
}

function isMaterialSearch(request, title) {
  const url = new URL(request.url());
  return url.pathname === "/api/search"
    && url.searchParams.get("q") === title
    && url.searchParams.get("kind") === "material";
}

function materialSearchResponse(title) {
  return response => isMaterialSearch(response.request(), title);
}

async function submitMaterialSearch(page, title) {
  const response = page.waitForResponse(materialSearchResponse(title), { timeout: 5_000 });
  await page.getByRole("button", { name: "搜索", exact: true }).click();
  return response;
}

async function searchApprovedMaterial(page, title) {
  const response = await submitMaterialSearch(page, title);
  if (response.ok()) return;
  await waitForSearchMaterial(page.context().request, title);
  const retry = page.waitForResponse(materialSearchResponse(title), { timeout: 5_000 });
  await page.reload();
  await readOkJson(await retry);
}

async function rejectFirstMaterialSearch(page, title) {
  let rejected = false;
  await page.route("**/api/search*", async (route) => {
    if (!rejected && isMaterialSearch(route.request(), title)) {
      rejected = true;
      await route.fulfill({ status: 503, body: '{"detail":"检索目录正在同步"}' });
      return;
    }
    await route.continue();
  });
}

async function mountAfterCatalogRetry(page, caseId, title) {
  await rejectFirstMaterialSearch(page, title);
  await mountApprovedMaterial(page, caseId, title);
}

async function openApprovedMaterialSearch(page, caseId, title) {
  await page.goto(`/#/materials?caseId=${caseId}`);
  await page.getByLabel("搜索素材").fill(title);
  await waitForSearchMaterial(page.context().request, title);
  await searchApprovedMaterial(page, title);
}

async function mountApprovedMaterial(page, caseId, title) {
  await openApprovedMaterialSearch(page, caseId, title);
  await page.getByLabel(`选择${title}`).check();
  await page.getByRole("button", { name: "加入当前案例" }).click();
  await expect(page.getByRole("status")).toHaveText("已加入 1 条素材");
}

async function downloadApprovedMaterial(page, caseId, title, filename, content) {
  await openApprovedMaterialSearch(page, caseId, title);
  const pending = page.waitForEvent("download");
  await page.getByRole("link", { name: `下载${title}` }).click();
  const download = await pending;
  expect(download.suggestedFilename()).toBe(filename);
  expect(await readFile(await download.path(), "utf8")).toBe(content);
}

async function expectMaterialAbsent(page, caseId, title) {
  await page.goto(`/#/materials?caseId=${caseId}`);
  await page.getByLabel("搜索素材").fill(title);
  const response = page.waitForResponse(candidate => (
    new URL(candidate.url()).pathname === "/api/search"
    && new URL(candidate.url()).searchParams.get("q") === title
  ));
  await page.getByRole("button", { name: "搜索", exact: true }).click();
  const payload = await readOkJson(await response);
  expect(payload.items.map(item => item.title)).not.toContain(title);
  await expect(page.getByText(title, { exact: true })).toHaveCount(0);
}

async function expectWorkbenchMaterial(page, title) {
  await page.getByRole("link", { name: "返回当前案例" }).click();
  await page.getByLabel("辅助面板").getByRole("button", { name: "附件" }).click();
  await page.getByRole("button", { name: /素材 1/ }).click();
  await expect(page.getByText(title, { exact: true })).toBeVisible();
}

async function reviewImportedCandidates(page, marker, filename, rejected, title) {
  await openAdminImport(page);
  await page.getByLabel("素材访问级别").selectOption("public");
  await submitFiles(page, [
    upload(filename, `真实审核与挂载-${marker}`),
    upload(rejected, `真实拒绝-${marker}`),
  ]);
  await approveCandidate(page, filename, title);
  await rejectCandidate(page, rejected);
}

async function importApprovedFile(page, access, filename, title, content) {
  await page.getByLabel("素材访问级别").selectOption(access);
  await submitFiles(page, upload(filename, content));
  await approveCandidate(page, filename, title);
}

async function lifecycle(request, caseId, command, versionId) {
  const auth = await readOkJson(await request.get("/api/auth/session"));
  const current = await readOkJson(await request.get(`/api/cases/${caseId}`));
  return readOkJson(await request.post(`/api/cases/${caseId}/lifecycle`, {
    headers: { "X-CSRF-Token": auth.csrfToken },
    data: { command, revision: current.revision, submittedVersionId: versionId },
  }));
}

async function publishDraft(page, caseId) {
  const submitted = await lifecycle(page.context().request, caseId, "submit");
  await logoutAndWait(page);
  await login(page, "admin", "admin123");
  await lifecycle(page.context().request, caseId, "start");
  await lifecycle(page.context().request, caseId, "approve", submitted.version.id);
  await logoutAndWait(page);
}

async function expectPublicDownload(page, title, content) {
  const pending = page.waitForEvent("download");
  await page.getByRole("link", { name: `下载${title}` }).click();
  expect(await readFile(await (await pending).path(), "utf8")).toBe(content);
}

test("管理员批量导入资料并识别重复内容", async ({ page }) => {
  const marker = `${Date.now()}-${test.info().parallelIndex}`;
  const first = `批量导入甲-${marker}`;
  const second = `批量导入乙-${marker}`;
  await openAdminImport(page);
  await submitFiles(page, [
    upload(`资料甲-${marker}.txt`, first),
    upload(`资料乙-${marker}.txt`, second),
  ]);
  await expect(page.getByText("成功", { exact: true })).toBeVisible();
  await expect(page.getByRole("cell", { name: "待审核", exact: true })).toHaveCount(2);

  await submitFiles(page, upload(`重复资料-${marker}.txt`, first));
  await expect(page.getByRole("cell", { name: "重复", exact: true })).toBeVisible();
});

test("普通用户不能进入资料批量导入", async ({ page }) => {
  await login(page, "user", "user123");
  await expect(page.getByRole("link", { name: "管理后台" })).toHaveCount(0);

  await page.goto("/#/admin/material-imports");
  await expect(page).toHaveURL(/#\/$/);
});

test("导入完成后再加载审核候选", async ({ page }) => {
  const filename = `等待导入-${Date.now()}.txt`;
  const path = "**/api/admin/material-imports";
  const started = deferred();
  const release = deferred();
  await openAdminImport(page);
  await pauseImport(page, path, started, release);
  try {
    const submitted = submitFiles(page, upload(filename, `wait-${filename}`));
    await started.promise;
    release.resolve();
    await submitted;
    await page.reload();
    await expect(page.getByRole("article", { name: `待审核：${filename}` })).toBeVisible();
  } finally { await page.unroute(path); }
});

test("管理员审核导入候选后教师可检索并挂入草稿", async ({ page }) => {
  const marker = `${Date.now()}-${test.info().parallelIndex}`;
  const filename = `审核闭环-${marker}.txt`;
  const rejected = `拒绝闭环-${marker}.txt`;
  const title = `批准素材-${marker}`;
  await reviewImportedCandidates(page, marker, filename, rejected, title);
  await loginTeacher(page);
  const draft = await createDraft(page.context().request, `审核挂载草稿-${marker}`);
  await clearCaseMaterials(page.context().request, draft.id);
  await expectMaterialAbsent(page, draft.id, rejected.replace(/\.txt$/, ""));
  await downloadApprovedMaterial(
    page, draft.id, title, filename, `真实审核与挂载-${marker}`,
  );
  await mountApprovedMaterial(page, draft.id, title);
  await expectWorkbenchMaterial(page, title);
});

test("发布案例公开文件可匿名下载且校内文件保持受限", async ({ page }) => {
  test.setTimeout(60_000);
  const marker = `${Date.now()}-${test.info().parallelIndex}`;
  const publicTitle = `公开原文件-${marker}`;
  const campusTitle = `校内原文件-${marker}`;
  await openAdminImport(page);
  await importApprovedFile(page, "public", `${publicTitle}.txt`, publicTitle, `public-bytes-${marker}`);
  await importApprovedFile(page, "campus", `${campusTitle}.txt`, campusTitle, `campus-bytes-${marker}`);
  await loginTeacher(page);
  const draft = await createDraft(page.context().request, `素材公开页-${marker}`);
  await mountApprovedMaterial(page, draft.id, publicTitle);
  await mountAfterCatalogRetry(page, draft.id, campusTitle);
  await publishDraft(page, draft.id);
  await page.goto(`/#/cases/${draft.id}`);
  await expectPublicDownload(page, publicTitle, `public-bytes-${marker}`);
  await expect(page.getByText(campusTitle, { exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: `下载${campusTitle}` })).toHaveCount(0);
  await expect(page.getByRole("button", { name: `${campusTitle}内容受限` })).toBeDisabled();
});
