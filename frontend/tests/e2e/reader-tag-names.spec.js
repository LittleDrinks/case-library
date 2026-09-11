import { expect, test } from "@playwright/test";

const PUBLISHED_TAGS = ["科学家精神", "爱国主义教育", "文化自信", "大思政课建设"];
const TAG_IDS = {
  科学家精神: "tag-seed-4-1", 爱国主义教育: "tag-seed-4-2",
  文化自信: "tag-seed-4-3", 劳动教育: "tag-seed-4-4", 大思政课建设: "tag-seed-4-5",
};
const ADDED_TAG = "劳动教育";
const REMOVED_TAG = "文化自信";
const NEW_TAG_SET = [...PUBLISHED_TAGS, ADDED_TAG];
const PUBLISHED_TAG_IDS = PUBLISHED_TAGS.map((name) => TAG_IDS[name]);

async function signIn(page, { username, password }) {
  await page.goto("/#/login");
  await page.getByLabel("用户名").fill(username);
  await page.getByLabel("密码").fill(password);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page).toHaveURL(/#\/$/);
}

async function authHeaders(request) {
  const session = await (await request.get("/api/auth/session")).json();
  return { "X-CSRF-Token": session.csrfToken };
}

async function applyTagSet(request, headers, caseId) {
  const current = await (await request.get(`/api/cases/${caseId}`)).json();
  // 通过真实目录形状设置标签：覆盖提交所需标签并留出后续编辑增量。
  const tagIds = [...PUBLISHED_TAG_IDS, "tag-seed-1-4"];
  const patched = await (await request.patch(`/api/cases/${caseId}`, {
    headers, data: { revision: current.revision, tagIds },
  })).json();
  expect(patched.tagIds).toEqual(expect.arrayContaining([...PUBLISHED_TAG_IDS, "tag-seed-1-4"]));
}

async function createTaggedCase(request, marker) {
  const headers = await authHeaders(request);
  const document = {
    type: "doc",
    content: [
      { type: "heading", attrs: { level: 1 }, content: [{ type: "text", text: "一、教学说明" }] },
      { type: "paragraph", content: [{ type: "text", text: marker }] },
    ],
  };
  const created = await (await request.post("/api/cases", { headers, data: { title: marker, document } })).json();
  expect(created.id).toBeTruthy();
  await applyTagSet(request, headers, created.id);
  return created;
}

async function publishCase(request, caseId) {
  const headers = await authHeaders(request);
  const current = await (await request.get(`/api/cases/${caseId}`)).json();
  const submitted = await (await request.post(`/api/cases/${caseId}/lifecycle`, {
    headers, data: { command: "submit", revision: current.revision },
  })).json();
  expect(submitted.version.id).toBeTruthy();
  return submitted.version.id;
}

async function approveAsAdmin(browser, caseId, versionId) {
  const context = await browser.newContext();
  const page = await context.newPage();
  await signIn(page, ADMIN);
  const request = page.context().request;
  const headers = await authHeaders(request);
  const current = await (await request.get(`/api/cases/${caseId}`)).json();
  await lifecycle(request, headers, caseId, "start", current.revision);
  const started = await (await request.get(`/api/cases/${caseId}`)).json();
  await lifecycle(request, headers, caseId, "approve", started.revision, versionId);
  await context.close();
}

async function lifecycle(request, headers, caseId, command, revision, submittedVersionId) {
  const response = await request.post(`/api/cases/${caseId}/lifecycle`, {
    headers, data: { command, revision, submittedVersionId },
  });
  expect(response.ok()).toBe(true);
  return response.json();
}

async function openPublicCase(page, caseId, marker) {
  await page.goto(`/#/cases/${caseId}`);
  await expect(page.locator("textarea.document-title")).toHaveValue(marker);
}

async function assertRealTagNames(page) {
  const tags = page.getByLabel("案例标签");
  for (const name of NEW_TAG_SET) await expect(tags).toContainText(name);
  await expect(tags).not.toContainText("tag-seed");
}

async function capture(page, testInfo, name) {
  await page.screenshot({ path: testInfo.outputPath(name), fullPage: false });
}

async function assertEditedTags(page) {
  const tags = page.getByLabel("案例标签");
  await expect(tags).toContainText(ADDED_TAG);
  await expect(tags).not.toContainText(REMOVED_TAG);
}

async function reopenAndAddTag(page, caseId, marker) {
  // 作者另开新稿得到可编辑工作版本（既有 reopen 流程），修改标签后等待自动保存。
  await page.goto(`/#/workbench/${caseId}`);
  await page.getByRole("button", { name: "另开新稿" }).click();
  await expect(page.locator("textarea.document-title")).not.toHaveAttribute("readonly");
  const popover = page.locator(".case-tag-popover");
  await page.getByRole("button", { name: "设置标签" }).click();
  // 作者真实修改：勾上劳动教育并取消文化自信，产生工作记录净变化后等待自动保存。
  await popover.locator("label", { hasText: ADDED_TAG }).locator("input").check();
  await popover.locator("label", { hasText: REMOVED_TAG }).locator("input").uncheck();
  await expect(page.getByText("已保存")).toBeVisible();
  await page.getByRole("button", { name: "设置标签" }).click();

  await page.reload();
  await expect(page.locator("textarea.document-title")).toHaveValue(marker);
}

async function newBrowserPage(browser) {
  const context = await browser.newContext();
  const page = await context.newPage();
  return { context, page, request: page.context().request };
}

async function publishWithAdmin(browser, request, marker) {
  const created = await createTaggedCase(request, marker);
  const versionId = await publishCase(request, created.id);
  await approveAsAdmin(browser, created.id, versionId);
  return created;
}
async function newAuthorPage(browser, marker) {
  const author = await newBrowserPage(browser);
  await signIn(author.page, AUTHOR);
  const created = await publishWithAdmin(browser, author.request, marker);
  await author.context.close();
  return created;
}

test("匿名访客公开阅读看到真实标签名称而非内部 ID", async ({ browser }, testInfo) => {
  const marker = `公开阅读标签-${Date.now()}`;
  const created = await newAuthorPage(browser, marker);
  const reader = await newBrowserPage(browser);
  await openPublicCase(reader.page, created.id, marker);
  await assertRealTagNames(reader.page);
  await capture(reader.page, testInfo, "anonymous-reader-tags.png");
  await reader.context.close();
});

test("公开阅读目录加载失败展示错误与重试，不回退内部 ID", async ({ browser }, testInfo) => {
  const marker = `目录失败标签-${Date.now()}`;
  const created = await newAuthorPage(browser, marker);


  const reader = await newBrowserPage(browser);
  await reader.page.route("**/api/tag-groups", (route) => route.abort());
  await openPublicCase(reader.page, created.id, marker);
  const tags = reader.page.locator(".case-tags");
  await expect(tags).toContainText("标签目录加载失败");
  await expect(tags).not.toContainText("tag-seed");
  await capture(reader.page, testInfo, "reader-catalog-failed.png");

  await reader.page.unroute("**/api/tag-groups");
  await tags.getByRole("button", { name: "重试" }).click();
  await assertRealTagNames(reader.page);
  await capture(reader.page, testInfo, "reader-catalog-retry.png");
  await reader.context.close();
});

test("作者从公开阅读回到工作台修改标签并保存，刷新后名称与公开页一致", async ({ browser }, testInfo) => {
  const { context, page, request } = await newBrowserPage(browser);
  await signIn(page, AUTHOR);
  const marker = `作者编辑标签-${Date.now()}`;
  const created = await publishWithAdmin(browser, request, marker);
  await openPublicCase(page, created.id, marker);
  await assertRealTagNames(page);
  await capture(page, testInfo, "author-reader-tags.png");
  await reopenAndAddTag(page, created.id, marker);
  await assertRealTagNames(page);
  await assertEditedTags(page);
  await capture(page, testInfo, "author-workbench-tags.png");

  await openPublicCase(page, created.id, marker);
  await assertRealTagNames(page);
  await assertEditedTags(page);
  await capture(page, testInfo, "author-public-after-edit.png");
  await context.close();
});

