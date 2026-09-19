import { expect } from "@playwright/test";
import { readFile } from "node:fs/promises";
import { unzipSync } from "fflate";
import { createBdd } from "playwright-bdd";

const { Given, When, Then, After } = createBdd();
const states = new WeakMap();
const DOCX_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document";

function stateOf(testInfo) {
  let state = states.get(testInfo);
  if (!state) {
    state = {};
    states.set(testInfo, state);
  }
  return state;
}

async function jsonResponse(response) {
  expect(response.ok()).toBe(true);
  return response.json();
}

async function sessionOf(page) {
  return jsonResponse(await page.context().request.get("/api/auth/session"));
}

async function caseOf(page, caseId) {
  return jsonResponse(await page.context().request.get(`/api/cases/${caseId}`));
}

async function login(page) {
  await page.goto("/#/login");
  await page.getByLabel("用户名").fill("user");
  await page.getByLabel("密码").fill("user123");
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page).toHaveURL(/#\/$/);
}

async function openWorkbench(page, caseId) {
  await page.goto(`/#/workbench/${caseId}`);
  await expect(page.getByLabel("案例标题")).toBeVisible();
}

function documentFor(marker) {
  return {
    type: "doc",
    content: [
      { type: "heading", attrs: { level: 1 }, content: [{ type: "text", text: "一、教学说明" }] },
      { type: "paragraph", content: [{ type: "text", text: marker }] },
    ],
  };
}

async function createCase(page, marker, documentMarker = marker) {
  const auth = await sessionOf(page);
  const response = await page.context().request.post("/api/cases", {
    headers: { "X-CSRF-Token": auth.csrfToken },
    data: { title: marker, document: documentFor(documentMarker) },
  });
  return jsonResponse(response);
}

async function lifecycle(page, caseId, command) {
  const auth = await sessionOf(page);
  const current = await caseOf(page, caseId);
  const response = await page.context().request.post(`/api/cases/${caseId}/lifecycle`, {
    headers: { "X-CSRF-Token": auth.csrfToken },
    data: { command, revision: current.revision },
  });
  return jsonResponse(response);
}

async function saveCase(page, caseId, snapshot) {
  const auth = await sessionOf(page);
  const current = await caseOf(page, caseId);
  const response = await page.context().request.patch(`/api/cases/${caseId}`, {
    headers: { "X-CSRF-Token": auth.csrfToken },
    data: { ...snapshot, revision: current.revision },
  });
  return jsonResponse(response);
}

async function restoreCase(page, original) {
  await saveCase(page, original.id, {
    title: original.title,
    document: original.document,
  });
}

async function wordDocumentText(page, xml) {
  return page.evaluate((source) => {
    const parsed = new DOMParser().parseFromString(source, "application/xml");
    if (parsed.getElementsByTagName("parsererror").length) throw new Error("DOCX XML解析失败");
    const namespace = "http://schemas.openxmlformats.org/wordprocessingml/2006/main";
    return Array.from(parsed.getElementsByTagNameNS(namespace, "t"), (node) => node.textContent || "")
      .join("");
  }, xml);
}

Given("教师打开登录页并输入演示账号", async ({ page }) => {
  await page.goto("/#/login");
  await page.getByLabel("用户名").fill("user");
  await page.getByLabel("密码").fill("user123");
});

When("教师点击登录", async ({ page }) => {
  await page.getByRole("button", { name: "登录", exact: true }).click();
});

Then("浏览器显示教师身份且会话接口返回该用户", async ({ page }) => {
  await expect(page).toHaveURL(/#\/$/);
  await expect(page.locator(".site-account")).toContainText("演示用户");
  expect(await sessionOf(page)).toMatchObject({ user: { username: "user", role: "user" } });
});

When("教师刷新页面", async ({ page }) => {
  await page.reload();
});

Then("会话保持登录状态无需重新认证", async ({ page }) => {
  await expect(page).toHaveURL(/#\/$/);
  await expect(page.locator(".site-account")).toContainText("演示用户");
  await expect(page.getByRole("link", { name: "登录", exact: true })).toHaveCount(0);
});

Given("教师登录并打开一个独立草稿工作台", async ({ page, $testInfo }) => {
  const state = stateOf($testInfo);
  await login(page);
  state.exportTitleMarker = `浏览器BDD DOCX标题 ${Date.now()} & 版式`;
  state.exportBodyMarker = `浏览器BDD DOCX正文 ${Date.now()} <结构>`;
  const created = await createCase(page, state.exportTitleMarker, state.exportBodyMarker);
  state.caseId = created.id;
  state.autosaveOriginal = created;
  await openWorkbench(page, created.id);
});
When("教师把标题改为唯一的浏览器验收标记", async ({ page, $testInfo }) => {
  const state = stateOf($testInfo);
  state.autosaveMarker = `浏览器BDD保存 ${Date.now()}`;
  await page.getByLabel("案例标题").fill(state.autosaveMarker);
});
Then("保存状态先显示未保存或保存中并最终显示已保存", async ({ page, $testInfo }) => {
  const state = stateOf($testInfo);
  await expect(page.locator(".save-state")).toHaveText(/未保存|保存中/);
  await expect(page.locator(".save-state")).toHaveText("已保存", { timeout: 5000 });
  expect((await caseOf(page, state.caseId)).title).toBe(state.autosaveMarker);
});
Then("标题保持该浏览器验收标记", async ({ page, $testInfo }) => {
  await expect(page.getByLabel("案例标题")).toHaveValue(stateOf($testInfo).autosaveMarker);
});


Given("教师登录并创建带历史版本的已改动草稿案例", async ({ page, $testInfo }) => {
  const state = stateOf($testInfo);
  await login(page);
  const marker = `浏览器BDD恢复 ${Date.now()}`;
  const created = await createCase(page, marker);
  await lifecycle(page, created.id, "submit");
  await lifecycle(page, created.id, "withdraw");
  await saveCase(page, created.id, { title: `${marker} 当前稿` });
  state.restoreCaseId = created.id;
  await openWorkbench(page, created.id);
  await page.getByRole("button", { name: "版本历史", exact: true }).click();
  const version = page.getByRole("button", { name: /^查看历史版本 v1 ·/ });
  await expect(version).toBeVisible();
  await version.click();
  await expect(page.locator(".version-paper")).toBeVisible();
  state.restoreBefore = await caseOf(page, created.id);
  state.overwriteRequests = 0;
  state.overwriteListener = (request) => {
    if (request.method() !== "POST" || !request.url().includes(`/api/cases/${created.id}/lifecycle`)) return;
    if (request.postDataJSON()?.command === "overwrite") state.overwriteRequests += 1;
  };
  page.on("request", state.overwriteListener);
});

When("教师点击恢复此版本并在确认框中选择取消恢复", async ({ page }) => {
  await page.locator(".version-paper-actions .version-restore").click();
  const dialog = page.getByRole("dialog", { name: /恢复此版本/ });
  await expect(dialog).toBeVisible();
  await dialog.getByRole("button", { name: "取消恢复", exact: true }).click();
  await expect(dialog).toBeHidden();
});

Then("未发出恢复网络请求", async ({ $testInfo }) => {
  expect(stateOf($testInfo).overwriteRequests).toBe(0);
});
Then("案例标题、修订号与正文均与取消前一致", async ({ page, $testInfo }) => {
  const state = stateOf($testInfo);
  const current = await caseOf(page, state.restoreCaseId);
  expect(current).toMatchObject({
    title: state.restoreBefore.title,
    revision: state.restoreBefore.revision,
    document: state.restoreBefore.document,
  });
  await page.getByRole("tab", { name: "当前教师稿" }).click();
  await expect(page.getByLabel("案例标题")).toHaveValue(state.restoreBefore.title);
  await expect(page.locator(".canvas-editor")).toContainText(
    state.restoreBefore.document.content[1].content[0].text,
  );
});


When("教师点击导出DOCX", async ({ page, $testInfo }) => {
  const state = stateOf($testInfo);
  const downloadEvent = page.waitForEvent("download");
  await page.getByRole("button", { name: "导出 DOCX", exact: true }).click();
  state.download = await downloadEvent;
  state.downloadPath = $testInfo.outputPath(`${state.caseId}.docx`);
  await state.download.saveAs(state.downloadPath);
});

Then("浏览器下载独立草稿的DOCX文件且为合法Word文档", async ({ page, $testInfo }) => {
  const state = stateOf($testInfo);
  expect(state.download.suggestedFilename()).toBe(`case-${state.caseId}.docx`);
  const bytes = await readFile(state.downloadPath);
  expect(bytes.subarray(0, 2).toString()).toBe("PK");
  const files = unzipSync(bytes);
  expect(Object.keys(files)).toEqual(expect.arrayContaining([
    "[Content_Types].xml",
    "_rels/.rels",
    "word/document.xml",
  ]));
  const types = new TextDecoder().decode(files["[Content_Types].xml"]);
  const documentXml = new TextDecoder().decode(files["word/document.xml"]);
  expect(types).toContain(DOCX_TYPE);
  expect(documentXml).toContain("<w:document");
  const documentText = await wordDocumentText(page, documentXml);
  expect(documentText).toContain(state.exportTitleMarker);
  expect(documentText).toContain(state.exportBodyMarker);
});

After(async ({ page, $testInfo }) => {
  const state = stateOf($testInfo);
  if (state.overwriteListener) page.off("request", state.overwriteListener);
  if (state.autosaveOriginal) await restoreCase(page, state.autosaveOriginal);
});
