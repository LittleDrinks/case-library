import { expect, test } from "@playwright/test";

async function signIn(page) {
  await page.goto("/#/login");
  await page.getByLabel("用户名").fill("user");
  await page.getByLabel("密码").fill("user123");
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page).toHaveURL(/#\/$/);
}

function longDocument(key) {
  const paragraph = (text) => ({ type: "paragraph", content: [{ type: "text", text }] });
  return {
    type: "doc",
    content: [
      { type: "heading", attrs: { level: 1 }, content: [{ type: "text", text: `Issue 318 ${key}` }] },
      ...Array.from({ length: 32 }, (_, index) => paragraph(
        `Long document section ${index + 1}: retained content for toolbar reachability. `.repeat(2),
      )),
      paragraph(`format-range-${key} for formatting`),
      paragraph(`cursor-target-${key}`),
    ],
  };
}

async function createCase(request, key) {
  const auth = await (await request.get("/api/auth/session")).json();
  const response = await request.post("/api/cases", {
    headers: { "X-CSRF-Token": auth.csrfToken },
    data: { title: `Issue 318 ${key}`, document: longDocument(key) },
  });
  expect(response.ok()).toBe(true);
  return response.json();
}

async function assertMobileToolbarLayout(page) {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.locator(".canvas-column").evaluate((column) => {
    column.scrollTop = column.scrollHeight;
  });
  const row = page.locator(".workbench-format-row");
  await expect(row).toBeInViewport();
  const layout = await page.evaluate(() => {
    const rowRect = document.querySelector(".workbench-format-row").getBoundingClientRect();
    const canvasRect = document.querySelector(".canvas-workspace").getBoundingClientRect();
    const boldRect = document.querySelector('.workbench-format-row [aria-label="加粗"]').getBoundingClientRect();
    return {
      rowLeft: rowRect.left,
      rowRight: rowRect.right,
      rowBottom: rowRect.bottom,
      canvasTop: canvasRect.top,
      boldTop: boldRect.top,
      boldBottom: boldRect.bottom,
      documentWidth: document.documentElement.scrollWidth,
    };
  });
  expect(layout.rowLeft).toBeGreaterThanOrEqual(0);
  expect(layout.rowRight).toBeLessThanOrEqual(390);
  expect(layout.rowBottom).toBeLessThanOrEqual(layout.canvasTop);
  expect(layout.boldTop).toBeGreaterThanOrEqual(0);
  expect(layout.boldBottom).toBeLessThanOrEqual(layout.rowBottom);
  expect(layout.documentWidth).toBeLessThanOrEqual(390);
}

test("长文标签面板外部关闭保留正文光标，工具栏格式与标签保存后可恢复", async ({ page }) => {
  const key = `issue-318-${Date.now()}`;
  await signIn(page);
  const request = page.context().request;
  const created = await createCase(request, key);
  await page.goto(`/#/workbench/${created.id}`);
  await expect(page.getByLabel("案例标题")).toHaveValue(`Issue 318 ${key}`);

  const tagTrigger = page.getByRole("button", { name: "设置标签" });
  await tagTrigger.click();
  const popover = page.locator(".case-tag-popover");
  await page.getByLabel("案例标题").focus();
  await page.keyboard.press("Escape");
  await expect(popover).toBeHidden();
  await expect(tagTrigger).toBeFocused();

  await tagTrigger.click();
  const firstTag = popover.locator('input[type="checkbox"]').first();
  await expect(firstTag).toBeVisible();
  const tagLabel = await firstTag.evaluate((input) => input.closest("label").innerText.trim());
  await firstTag.check();
  await expect(popover).toBeVisible();

  const cursorTarget = page.locator(".canvas-editor p").filter({ hasText: `cursor-target-${key}` });
  await cursorTarget.click();
  await expect(popover).toBeHidden();
  await expect(page.locator(".canvas-editor")).toBeFocused();
  await page.keyboard.press("End");
  await page.keyboard.type(` appended-${key}`);
  await expect(cursorTarget).toContainText(`appended-${key}`);

  const formatText = `format-range-${key} for formatting`;
  const formatTarget = page.locator(".canvas-editor p").filter({ hasText: formatText });
  await formatTarget.selectText();
  await expect.poll(() => page.evaluate(() => window.getSelection()?.toString())).toBe(formatText);
  await expect(page.locator(".workbench-format-row")).toBeVisible();
  const scrollTop = await page.locator(".canvas-column").evaluate((column) => column.scrollTop);
  expect(scrollTop).toBeGreaterThan(0);
  await page.locator(".workbench-format-row").getByRole("button", { name: "加粗" }).click();
  await expect(formatTarget.locator("strong")).toHaveText(formatText);

  await expect(page.locator(".save-state")).toHaveText("已保存", { timeout: 10000 });
  const saved = await (await request.get(`/api/cases/${created.id}`)).json();
  expect(saved.tagIds).toHaveLength(1);
  expect(JSON.stringify(saved.document)).toContain("bold");
  await assertMobileToolbarLayout(page);

  await page.reload();
  await expect(page.getByLabel("案例标题")).toHaveValue(`Issue 318 ${key}`);
  await expect(page.locator(".case-tag-list")).toContainText(tagLabel);
  await expect(page.locator(".canvas-editor p").filter({ hasText: formatText }).locator("strong"))
    .toHaveText(formatText);
  await expect(page.locator(".canvas-editor p").filter({ hasText: `cursor-target-${key}` }))
    .toContainText(`appended-${key}`);
});
