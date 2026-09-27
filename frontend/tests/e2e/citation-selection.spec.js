import { expect, test } from "@playwright/test";

const text = "课前阅读材料；分组讨论；小组代表发表核心观点";
const source = { id: "selection-source", sourceType: "material", number: 1, title: "参考资料" };
const document = { type: "doc", content: [
  { type: "heading", attrs: { level: 1 }, content: [{ type: "text", text: "教学说明" }] },
  { type: "paragraph", content: [
    { type: "text", text },
    { type: "text", text: "\u200b", marks: [{ type: "citation", attrs: { sourceType: "material", sourceId: source.id } }] },
  ] },
] };

async function openCase(page, readOnly) {
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    let body = [];
    if (path === "/api/auth/session") body = { user: { id: "selection-owner", role: "user", name: "验收教师" }, csrfToken: "fixture" };
    else if (path === "/api/cases/selection-case") body = {
      id: "selection-case", ownerId: "selection-owner", title: "引用选区验收", revision: 1,
      workflowStatus: readOnly ? "pending" : "draft", document, tagIds: [], availableActions: [],
    };
    else if (path.endsWith("/sources")) body = { entries: [source] };
    else if (path.endsWith("/history")) body = { versions: [], events: [] };
    else if (path.endsWith("/agent/thread")) body = { id: "selection-thread", messages: [], artifacts: [], writes: [], activeRun: null };
    else if (path === "/api/ai/settings") body = { configured: true };
    await route.fulfill({ json: body });
  });
  await page.goto("/#/workbench/selection-case");
  await expect(page.locator(".ProseMirror p")).toBeVisible();
}

async function dragAcrossCitation(page, backward) {
  await page.locator(".ProseMirror h1").click();
  const points = await page.locator(".ProseMirror p").evaluate((paragraph) => {
    const range = window.document.createRange();
    range.setStart(paragraph.firstChild, 0);
    range.collapse(true);
    const start = range.getBoundingClientRect();
    const citation = paragraph.querySelector("sup").getBoundingClientRect();
    return [{ x: start.x, y: start.y + start.height / 2 }, { x: citation.right + 1, y: start.y + start.height / 2 }];
  });
  const [start, end] = backward ? points.reverse() : points;
  await page.mouse.move(start.x, start.y);
  await page.mouse.down();
  await page.mouse.move(end.x, end.y, { steps: 22 });
  await page.mouse.up();
}

for (const readOnly of [false, true]) {
  test(`${readOnly ? "只读" : "编辑"}正文从引用编号右侧反向拖选保持选区并传入 AI`, async ({ page }) => {
    await page.setViewportSize({ width: 1600, height: 1000 });
    await openCase(page, readOnly);
    for (const backward of [false, true]) {
      await dragAcrossCitation(page, backward);
      await expect.poll(() => page.evaluate(() => window.getSelection().toString())).toContain(text);
      await expect(page.getByTestId("composer-selection")).toHaveAttribute("title", text + "\u200b");
      await page.getByRole("textbox", { name: "向 AI 提问" }).fill("只润色选中的这句话");
      await expect(page.getByTestId("composer-selection")).toHaveAttribute("title", text + "\u200b");
    }
  });
}
