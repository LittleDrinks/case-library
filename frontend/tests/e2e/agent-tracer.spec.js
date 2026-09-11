import { expect, test } from "@playwright/test";
import { SKILL_ID, teachingPackage } from "./skill-package.js";

const PROVIDER_BASE_URL = process.env.E2E_PROVIDER_BASE_URL || "http://ai-provider:8080/v1";
const REQUEST_TEXT = "请结合平台资料修订第2段：补充评价依据";
const TARGET_TEXT = "第二段：教学目标需要更明确的评价依据。";
const REPLACEMENT_MARK = "修订后的段落：教学目标、课堂任务与评价依据逐项对应";
const SECOND_REPLACEMENT_MARK = "第二轮修订：教学目标、课堂任务与评价依据逐项对应";
const M1_ANNOTATION_QUOTE = "的评价依据。";

async function login(page) {
  await page.goto("/#/login");
  await page.getByLabel("用户名").fill("user");
  await page.getByLabel("密码").fill("user123");
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page).toHaveURL(/#\/$/);
}

async function csrf(page) {
  const response = await page.context().request.get("/api/auth/session");
  return (await response.json()).csrfToken;
}

function caseDocument() {
  return {
    type: "doc",
    content: [
      { type: "paragraph", content: [{ type: "text", text: "第一段仍保持原样。" }] },
      { type: "paragraph", content: [{ type: "text", text: "第二段：教学目标需要更明确的评价依据。" }] },
    ],
  };
}

async function createCase(page) {
  const response = await page.context().request.post("/api/cases", {
    headers: { "X-CSRF-Token": await csrf(page) },
    data: { title: `Tracer ${Date.now()}`, document: caseDocument() },
  });
  expect(response.ok()).toBe(true);
  return response.json();
}

async function configureChat(page) {
  const response = await page.context().request.put("/api/ai/settings", {
    headers: { "X-CSRF-Token": await csrf(page) },
    data: {
      mode: "custom", baseUrl: PROVIDER_BASE_URL,
      apiKey: "e2e-api-key", model: "e2e-model-a",
    },
  });
  expect(response.ok()).toBe(true);
}

async function waitSearchableCatalog(page) {
  await expect
    .poll(async () => {
      const response = await page.context().request.get("/api/search?q=科学家精神&pageSize=3");
      return (await response.json()).items?.length || 0;
    }, { timeout: 90_000, intervals: [2_000] })
    .toBeGreaterThan(0);
}

async function publishTeachingSkill(playwright) {
  const admin = await playwright.request.newContext();
  const login = await admin.post(
    "/api/auth/login", { data: { username: "admin", password: "admin123" } },
  );
  const headers = { "X-CSRF-Token": (await login.json()).csrfToken };
  const uploaded = await admin.post("/api/admin/skills/packages", {
    headers,
    multipart: { file: { name: "skill.zip", mimeType: "application/zip", buffer: teachingPackage() } },
  });
  expect(uploaded.ok()).toBe(true);
  const { version } = await uploaded.json();
  const published = await admin.post(`/api/admin/skills/${SKILL_ID}/publish`, {
    headers, data: { versionId: version.id },
  });
  expect(published.ok()).toBe(true);
  await admin.dispose();
}

async function openChat(page, caseId) {
  await page.goto(`/#/workbench/${caseId}`);
  await expect(page.getByLabel("案例标题")).toBeVisible();
  await page.locator(".workspace-actions").getByRole("button", { name: "AI" }).click();
  await expect(page.locator(".assistant-rail")).toHaveClass(/open/);
  await expect(page.getByLabel("向 AI 提问")).toBeEnabled();
}

async function selectAnnotationText(page, value) {
  const target = page.locator(".canvas-editor p", { hasText: TARGET_TEXT });
  if (value === TARGET_TEXT) return target.selectText();
  await target.click(); await page.keyboard.press("Home");
  const offset = await target.evaluate((node, text) => node.textContent.indexOf(text), value);
  expect(offset).toBeGreaterThanOrEqual(0);
  for (let index = 0; index < offset; index += 1) await page.keyboard.press("ArrowRight");
  await page.keyboard.down("Shift");
  for (let index = 0; index < value.length; index += 1) await page.keyboard.press("ArrowRight");
  await page.keyboard.up("Shift");
  await expect.poll(() => page.evaluate(() => window.getSelection()?.toString() || "")).toBe(value);
}

async function addAnnotation(page, quote = TARGET_TEXT) {
  await page.getByRole("button", { name: "批注", exact: true }).click();
  await selectAnnotationText(page, quote);
  await page.getByRole("button", { name: "添加选区批注" }).click();
  await page.getByLabel("批注内容").fill("请依据资料收紧这一段表述。");
  await page.getByRole("button", { name: "添加批注", exact: true }).click();
  await expect(page.locator(".comment-card")).toHaveCount(1);
  const response = await page.context().request.get(
    `/api/cases/${await currentCaseId(page)}/annotations`,
  );
  return response.json();
}

async function currentCaseId(page) {
  return page.url().split("/").pop();
}

async function expandSearchTool(page) {
  const search = page.locator('[data-testid="agent-tool-trace"]').filter({ hasText: "检索案例" });
  await expect(search).toBeVisible();
  if (await search.getAttribute("open")) return;
  await search.locator("summary").click();
}

async function selectPublishedSkill(page) {
  await page.getByTestId("skill-picker-toggle").click();
  const option = page.locator(".skill-popover [data-testid='skill-option']").filter({ hasText: SKILL_ID });
  await expect(option).toHaveCount(1, { timeout: 30_000 });
  await option.first().click();
  await expect(page.getByTestId("composer-skill-block")).toContainText(SKILL_ID);
}

async function selectCanvasTarget(page) {
  const target = page.locator(".canvas-editor p").nth(1);
  await expect(target).toHaveText(TARGET_TEXT);
  await target.selectText();
  await expect.poll(() => page.evaluate(() => window.getSelection()?.toString() || ""))
    .toBe(TARGET_TEXT);
  await expect(page.getByLabel("向 AI 提问")).toBeVisible();
}

async function sendSelection(page) {
  const requestPromise = page.waitForRequest((request) => (
    request.method() === "POST" && new URL(request.url()).pathname.endsWith("/stream")
  ));
  await page.getByLabel("向 AI 提问").fill(REQUEST_TEXT);
  await page.getByRole("button", { name: "发送", exact: true }).click();
  const payload = (await requestPromise).postDataJSON();
  expect(payload.messages[0].parts).toContainEqual({ type: "data-skill", data: { skillId: SKILL_ID } });
  const selection = payload.messages[0].parts.find((part) => part.type === "data-selection")?.data;
  expect(selection).toEqual(expect.objectContaining({ from: expect.any(Number), to: expect.any(Number) }));
  expect(selection.to).toBeGreaterThan(selection.from);
}

async function sendRequest(page) {
  await selectCanvasTarget(page);
  await sendSelection(page);
  const artifact = page.getByTestId("agent-artifact");
  await expect(artifact).toBeVisible({ timeout: 30_000 });
  await expect(artifact).toHaveAttribute("data-artifact-status", "pending");
}

async function acceptedViaApi(page, caseId) {
  const caseApi = await page.context().request.get(`/api/cases/${caseId}`);
  const persisted = await caseApi.json();
  expect(persisted.revision).toBe(2);
  expect(persisted.document.content[1].content[0].text).toContain(REPLACEMENT_MARK);
}

async function reloadRestoresTracer(page, caseId) {
  await page.reload();
  await openChat(page, caseId);
  await expect(page.getByTestId("agent-skill-load")).toBeVisible();
  await expandSearchTool(page);
  await expect(page.getByTestId("agent-skill-resource")).toContainText("生态保护案例");
  await expect(page.getByTestId("agent-source").first()).toBeVisible();
  const artifact = page.getByTestId("agent-artifact");
  await expect(artifact).toHaveAttribute("data-artifact-status", "accepted");
  await expect(artifact).toContainText(REPLACEMENT_MARK);
  await expect(artifact).toContainText("原文：第二段：教学目标需要更明确的评价依据。");
}

async function prepareTracer(page, playwright) {
  await publishTeachingSkill(playwright);
  await login(page);
  await configureChat(page);
  await waitSearchableCatalog(page);
  const created = await createCase(page);
  await openChat(page, created.id);
  await selectPublishedSkill(page);
  return created;
}

test("单段修订 tracer：发送、检索、生成、接受、刷新恢复全程真实 HTTP", async ({ page, playwright }) => {
  const created = await prepareTracer(page, playwright);

  await sendRequest(page);
  await expect(page.getByTestId("agent-skill-load")).toBeVisible();
  await expandSearchTool(page);
  await expect(page.getByTestId("agent-skill-resource")).toContainText("生态保护案例");
  const sources = page.getByTestId("agent-source");
  await expect(sources.first()).toBeVisible();
  expect(await sources.count()).toBeGreaterThan(0);
  await acceptAndVerify(page, created.id);
  await reloadRestoresTracer(page, created.id);
});

async function sendAnnotationRound(page, text, annotationId) {
  await page.getByRole("button", { name: "批注", exact: true }).click();
  const card = page.locator(".comment-card");
  await expect(card).toBeVisible();
  await card.getByRole("button", { name: "让 AI 修订" }).click();
  await selectPublishedSkill(page);
  const request = page.waitForRequest((item) => (
    item.method() === "POST" && new URL(item.url()).pathname.endsWith("/stream")
  ));
  await page.getByLabel("向 AI 提问").fill(text);
  await page.getByRole("button", { name: "发送", exact: true }).click();
  const payload = (await request).postDataJSON();
  expect(payload.messages[0].parts).toContainEqual({ type: "data-annotation", data: { id: annotationId } });
  await expect(page.getByTestId("agent-artifact")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId("agent-artifact")).toHaveAttribute("data-artifact-status", "pending");
  await expect(page.locator(".agent-chat-panel"))
    .toHaveAttribute("data-run-status", "completed", { timeout: 30_000 });
}

async function prepareAnnotationDiscussion(page, playwright, quote = TARGET_TEXT) {
  await publishTeachingSkill(playwright);
  await login(page);
  await configureChat(page);
  await waitSearchableCatalog(page);
  const created = await createCase(page);
  await openChat(page, created.id);
  await selectPublishedSkill(page);
  const annotations = await addAnnotation(page, quote);
  return { created, annotation: annotations[0] };
}

async function expectAnnotationHistory(page) {
  await page.getByRole("button", { name: "批注", exact: true }).click();
  await expect(page.locator(".comment-revisions li")).toHaveCount(2);
  await expect(page.locator(".comment-revisions")).toContainText(REPLACEMENT_MARK);
  await expect(page.locator(".comment-revisions")).toContainText(SECOND_REPLACEMENT_MARK);
}

async function closeAnnotation(page) {
  await page.getByRole("button", { name: "批注", exact: true }).click();
  const card = page.locator(".comment-card");
  await card.getByRole("button", { name: "标记解决" }).click();
  await expect(card).toHaveCount(0);
  await page.getByRole("tab", { name: "查看已解决批注" }).click();
  await expect(card).toContainText("已解决");
  await expect(card).toContainText("已拒绝");
}

function annotationCard(page, annotationId) {
  return page.locator(".comment-card[data-annotation-id=\"" + annotationId + "\"]");
}

async function expectResolvedAnnotation(page, caseId, annotationId) {
  await page.getByRole("tab", { name: "查看已解决批注" }).click();
  const card = annotationCard(page, annotationId);
  await expect(card).toContainText("已解决");
  const rows = await (await page.context().request.get(`/api/cases/${caseId}/annotations`)).json();
  expect(rows).toEqual(expect.arrayContaining([
    expect.objectContaining({ id: annotationId, status: "resolved" }),
  ]));
  const history = card.locator(".comment-revisions");
  await expect(history.locator("li")).toHaveCount(1);
  await expect(history).toContainText("已拒绝");
}

async function changeAnnotationTarget(page) {
  await page.getByRole("button", { name: "批注", exact: true }).click();
  await selectAnnotationText(page, M1_ANNOTATION_QUOTE); await page.keyboard.type("改写目标");
  await expect(page.locator(".save-state")).toHaveText("已保存", { timeout: 5_000 });
  await page.reload(); await page.getByRole("button", { name: "批注", exact: true }).click();
}

test("批注讨论：真实 Agent 两轮候选在公共面板中保留历史并合并最新轮", async ({ page, playwright }) => {
  test.setTimeout(120_000);
  const { created, annotation } = await prepareAnnotationDiscussion(page, playwright);
  await sendAnnotationRound(page, "第一轮：请结合当前选区生成修订候选。", annotation.id);
  await sendAnnotationRound(page, "第二轮：请继续收紧当前批注对应的候选。", annotation.id);
  await expectAnnotationHistory(page);
  await page.getByRole("button", { name: "合并并关闭" }).click();
  await expect(page.locator(".comment-card")).toHaveCount(0);
  await page.getByRole("tab", { name: "查看已解决批注" }).click();
  await expect(page.locator(".comment-card")).toContainText("已解决");
  await expect(page.locator(".canvas-editor")).toContainText(SECOND_REPLACEMENT_MARK);
  const current = await page.context().request.get(`/api/cases/${created.id}`);
  expect((await current.json()).document.content[1].content[0].text).toContain(SECOND_REPLACEMENT_MARK);
});

test("批注候选可直接关闭且正文与修订历史刷新一致", async ({ page, playwright }) => {
  test.setTimeout(120_000);
  const { created, annotation } = await prepareAnnotationDiscussion(
    page, playwright, M1_ANNOTATION_QUOTE,
  );
  await sendAnnotationRound(page, "请修订选区：第一轮候选仅供直接关闭，不改正文。", annotation.id);
  const before = await (await page.context().request.get(`/api/cases/${created.id}`)).json();
  await closeAnnotation(page);
  const after = await (await page.context().request.get(`/api/cases/${created.id}`)).json();
  expect(after.document).toEqual(before.document); expect(after.revision).toBe(before.revision);
  await page.reload(); await page.getByRole("button", { name: "批注", exact: true }).click();
  await expectResolvedAnnotation(page, created.id, annotation.id);
});

test("目标变化后浏览器拒绝过期采用并保留无关正文编辑", async ({ page, playwright }) => {
  test.setTimeout(120_000);
  const { created, annotation } = await prepareAnnotationDiscussion(
    page, playwright, M1_ANNOTATION_QUOTE,
  );
  await sendAnnotationRound(page, "请修订选区：第一轮候选用于目标变化验证。", annotation.id);
  await changeAnnotationTarget(page);
  const card = page.locator(".comment-card");
  await expect(card).toContainText("原文已变动，旧修订不可合并");
  await expect(card.getByRole("button", { name: "合并并关闭" })).toHaveCount(0);
  await expect(card).toContainText("已失效");
  const current = await (await page.context().request.get(`/api/cases/${created.id}`)).json();
  const text = current.document.content[1].content[0].text;
  expect(text).toBe("第二段：教学目标需要更明确改写目标");
});

async function deleteAnnotationTarget(page) {
  await page.getByRole("button", { name: "批注", exact: true }).click();
  await selectAnnotationText(page, M1_ANNOTATION_QUOTE);
  await page.keyboard.press("Backspace");
  await expect(page.locator(".save-state")).toHaveText("已保存", { timeout: 5_000 });
  await page.reload(); await page.getByRole("button", { name: "批注", exact: true }).click();
}

async function editUnrelatedText(page) {
  await page.locator(".canvas-editor p").first().click();
  await page.keyboard.press("End"); await page.keyboard.type(" 无关正文编辑");
  await expect(page.locator(".save-state")).toHaveText("已保存", { timeout: 5_000 });
  await page.reload(); await page.getByRole("button", { name: "批注", exact: true }).click();
}

test("目标删除后浏览器拒绝采用并保留已删除状态", async ({ page, playwright }) => {
  test.setTimeout(120_000);
  const { created, annotation } = await prepareAnnotationDiscussion(page, playwright, M1_ANNOTATION_QUOTE);
  await sendAnnotationRound(page, "请修订选区：删除目标后不得采用。", annotation.id);
  await deleteAnnotationTarget(page);
  const card = annotationCard(page, annotation.id);
  await expect(card).toContainText("原文已删除");
  await expect(card).toContainText("已失效");
  await expect(card.getByRole("button", { name: "合并并关闭" })).toHaveCount(0);
  const rows = await (await page.context().request.get(`/api/cases/${created.id}/annotations`)).json();
  expect(rows).toEqual(expect.arrayContaining([
    expect.objectContaining({ id: annotation.id, anchorState: "deleted" }),
  ]));
});

test("无关正文编辑后浏览器仍可采用有效修订", async ({ page, playwright }) => {
  test.setTimeout(120_000);
  const { created, annotation } = await prepareAnnotationDiscussion(page, playwright, M1_ANNOTATION_QUOTE);
  await sendAnnotationRound(page, "请修订选区：无关编辑后仍可采用。", annotation.id);
  await editUnrelatedText(page);
  const card = annotationCard(page, annotation.id);
  await expect(card.getByRole("button", { name: "合并并关闭" })).toBeVisible();
  await card.getByRole("button", { name: "合并并关闭" }).click();
  await expect(card).toHaveCount(0);
  await page.getByRole("tab", { name: "查看已解决批注" }).click();
  await expect(card).toContainText("已解决");
  const rows = await (await page.context().request.get(`/api/cases/${created.id}/annotations`)).json();
  const accepted = rows[0].revisions.find((revision) => revision.status === "accepted");
  const current = await (await page.context().request.get(`/api/cases/${created.id}`)).json();
  expect(accepted).toBeDefined();
  expect(current.document.content[0].content[0].text).toContain("无关正文编辑");
  expect(current.document.content[1].content[0].text).toContain(accepted.replacement);
});

test("批注讨论生成中切到批注面板：后台完成后当前历史自动出现新修订", async ({ page, playwright }) => {
  test.setTimeout(150_000);
  await prepareAnnotationDiscussion(page, playwright);
  await page.locator(".comment-card").getByRole("button", { name: "让 AI 修订" }).click();
  await selectPublishedSkill(page);
  await page.getByLabel("向 AI 提问").fill("第一轮：请结合当前选区生成修订候选。");
  await page.getByRole("button", { name: "发送", exact: true }).click();
  // 生成中切到批注面板：AI 面板被卸载，服务端运行继续
  await page.getByRole("button", { name: "批注", exact: true }).click();
  // 后台完成终态后无需手动刷新，当前批注历史自动出现新修订
  await expect(page.locator(".comment-revisions li")).toHaveCount(1, { timeout: 90_000 });
  await expect(page.locator(".comment-revisions")).toContainText(REPLACEMENT_MARK);
});

async function acceptAndVerify(page, caseId) {
  await page.getByTestId("agent-accept").click();
  const artifact = page.getByTestId("agent-artifact");
  await expect(artifact).toHaveAttribute("data-artifact-status", "accepted", { timeout: 15_000 });
  await acceptedViaApi(page, caseId);
}

async function adminSession(playwright) {
  const admin = await playwright.request.newContext();
  const login = await admin.post(
    "/api/auth/login", { data: { username: "admin", password: "admin123" } },
  );
  return { admin, headers: { "X-CSRF-Token": (await login.json()).csrfToken } };
}

async function adminLifecycle(admin, headers, caseId, command, revision, extra = {}) {
  const response = await admin.post(`/api/cases/${caseId}/lifecycle`, {
    headers, data: { command, revision, ...extra },
  });
  expect(response.ok(), `${command} 应成功`).toBe(true);
  return (await response.json()).case;
}

async function publishCase(playwright, title) {
  const { admin, headers } = await adminSession(playwright);
  const created = await admin.post("/api/cases", { headers, data: { title, document: caseDocument() } });
  expect(created.ok()).toBe(true);
  const draft = await created.json();
  const submitted = await adminLifecycle(admin, headers, draft.id, "submit", draft.revision);
  const started = await adminLifecycle(admin, headers, draft.id, "start", submitted.revision);
  await adminLifecycle(admin, headers, draft.id, "approve", started.revision, {
    submittedVersionId: submitted.submittedVersionId,
  });
  await admin.dispose();
  return draft.id;
}

async function hideCase(playwright, caseId) {
  const { admin, headers } = await adminSession(playwright);
  const current = await admin.get(`/api/cases/${caseId}`);
  expect(current.ok()).toBe(true);
  const hidden = await adminLifecycle(admin, headers, caseId, "hide", (await current.json()).revision);
  await admin.dispose();
  expect(hidden.publicationStatus).toBe("hidden");
}

async function waitCaseSearchable(page, caseId, title) {
  await expect.poll(async () => {
    const response = await page.context().request.get(
      `/api/search?q=${encodeURIComponent(title)}&pageSize=5`);
    const items = (await response.json()).items || [];
    return items.filter((item) => item.id === caseId).length;
  }, { timeout: 90_000, intervals: [2_000] }).toBeGreaterThan(0);
}

function sourceItem(page, caseId) {
  return page.locator(`[data-testid="agent-source"][data-source-ref="case:${caseId}"]`);
}

async function assertReadableCaseSource(page, caseId, draftId, title) {
  await expect(page.locator(".agent-chat-panel"))
    .toHaveAttribute("data-run-status", "completed", { timeout: 60_000 });
  const response = await page.context().request.get(`/api/cases/${draftId}/agent/thread`);
  expect(response.ok()).toBe(true);
  const search = (await response.json()).messages
    .find((message) => message.role === "assistant").parts
    .find((part) => part.type === "tool-search_corpus");
  expect(search.output.sources).toContainEqual(expect.objectContaining({
    kind: "case", id: caseId, title, snippet: title,
  }));
  await expandSearchTool(page);
  const item = sourceItem(page, caseId);
  await expect(item.locator("a")).toHaveAttribute("href", new RegExp(`#/cases/${caseId}$`));
  await expect(item.locator("b")).toHaveText(title);
  await expect(item).toContainText("当前可读取");
}

async function assertFocusWithdrawsCaseSource(page, caseId) {
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  const item = sourceItem(page, caseId);
  await expect(item.locator("small")).toHaveText("来源已下线或不可读取");
  await expect(item.locator("span")).toHaveText("");
  await expect(item.locator("a")).toHaveCount(0);
}

async function assertReopenMasksRun(page, draftId, caseId) {
  await page.reload();
  await openChat(page, draftId);
  const panel = page.locator(".agent-chat-panel");
  await expect(panel).toContainText("该回答引用的来源当前不可读，相关内容已隐藏");
  await expect(sourceItem(page, caseId)).toHaveCount(0);
  await expect(page.getByTestId("agent-source-read")).toContainText("当前身份无权限读取");
}

async function sendSourceRequest(page, title) {
  await selectCanvasTarget(page);
  const request = page.waitForRequest((item) => (
    item.method() === "POST" && new URL(item.url()).pathname.endsWith("/stream")
  ));
  await page.getByLabel("向 AI 提问").fill(
    `请结合平台资料修订第2段（摘要测试）：以《${title}》为依据补充评价依据`,
  );
  await page.getByRole("button", { name: "发送", exact: true }).click();
  expect((await request).postDataJSON().messages[0].parts)
    .toContainEqual({ type: "data-skill", data: { skillId: SKILL_ID } });
}

test("自建案例来源链接可点，隐藏后 focus 撤下、重开显示受限状态", async ({ page, playwright }) => {
  test.setTimeout(180_000);
  const title = `来源摘要验收 ${Date.now()}`;
  const caseId = await publishCase(playwright, title);
  await publishTeachingSkill(playwright);
  await login(page);
  await configureChat(page);
  await waitCaseSearchable(page, caseId, title);
  const draft = await createCase(page);
  await openChat(page, draft.id);
  await selectPublishedSkill(page);
  await sendSourceRequest(page, title);
  await assertReadableCaseSource(page, caseId, draft.id, title);
  await hideCase(playwright, caseId);
  await assertFocusWithdrawsCaseSource(page, caseId);
  await assertReopenMasksRun(page, draft.id, caseId);
});

async function prepareNonemptySummary(page, playwright) {
  await publishTeachingSkill(playwright);
  await login(page);
  await configureChat(page);
  const response = await page.context().request.get("/api/cases/c-02/public");
  expect(response.ok()).toBe(true);
  const source = await response.json();
  expect(source.summary.trim().length).toBeGreaterThan(20);
  await waitCaseSearchable(page, source.id, source.title);
  const draft = await createCase(page);
  await openChat(page, draft.id);
  await selectPublishedSkill(page);
  await sendSourceRequest(page, source.title);
  await expect(page.locator(".agent-chat-panel"))
    .toHaveAttribute("data-run-status", "completed", { timeout: 60_000 });
  await expandSearchTool(page);
  await expect(sourceItem(page, source.id).locator("span")).toHaveText(source.summary);
  return { source, draft };
}

async function restoreCase(playwright, caseId) {
  const { admin, headers } = await adminSession(playwright);
  try {
    const response = await admin.get(`/api/cases/${caseId}`);
    expect(response.ok()).toBe(true);
    const current = await response.json();
    if (current.publicationStatus === "public") return;
    const restored = await adminLifecycle(admin, headers, caseId, "restore", current.revision);
    expect(restored.publicationStatus).toBe("public");
  } finally { await admin.dispose(); }
}

test("来源的非空摘要在下线后撤回，重开不恢复旧内容", async ({ page, playwright }) => {
  test.setTimeout(180_000);
  const { source, draft } = await prepareNonemptySummary(page, playwright);
  try {
    await hideCase(playwright, source.id);
    await assertFocusWithdrawsCaseSource(page, source.id);
    await expect(page.locator(".agent-chat-panel")).not.toContainText(source.summary);
    await assertReopenMasksRun(page, draft.id, source.id);
    await expect(page.locator(".agent-chat-panel")).not.toContainText(source.summary);
  } finally { await restoreCase(playwright, source.id); }
});
