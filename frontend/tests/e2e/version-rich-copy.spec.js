import { expect, test } from "@playwright/test";

const baseOrigin = new URL(process.env.PLAYWRIGHT_BASE_URL).origin;

test.use({
  launchOptions: {
    channel: "chromium",
    args: [`--unsafely-treat-insecure-origin-as-secure=${baseOrigin}`],
  },
});

const historicalDocument = {
  type: "doc",
  content: [
    { type: "heading", attrs: { level: 1 }, content: [{ type: "text", text: "历史稿标题" }] },
    { type: "paragraph", content: [
      { type: "text", text: "第一行" },
      { type: "hardBreak" },
      { type: "text", text: "第二行" },
      { type: "text", text: "加粗", marks: [{ type: "bold" }] },
    ] },
    { type: "bulletList", content: [
      { type: "listItem", content: [{ type: "paragraph", content: [{ type: "text", text: "项目一" }] }] },
      { type: "listItem", content: [{ type: "paragraph", content: [{ type: "text", text: "项目二" }] }] },
    ] },
  ],
};

async function fulfillJson(route, value) {
  await route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify(value),
  });
}

async function mockWorkbenchApi(page) {
  const mutations = [];
  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const { pathname } = new URL(request.url());
    if (request.method() !== "GET") {
      mutations.push(`${request.method()} ${pathname}`);
      await route.fulfill({ status: 405, contentType: "application/json", body: "{}" });
      return;
    }
    if (pathname === "/api/auth/session") {
      await fulfillJson(route, { user: { id: "copy-user", role: "user" }, csrfToken: "copy-csrf" });
      return;
    }
    if (pathname === "/api/cases/copy-case") {
      await fulfillJson(route, {
        id: "copy-case", title: "当前教师稿标题", revision: 3, ownerId: "copy-user",
        workflowStatus: "draft", publicationStatus: "none", availableActions: ["submit", "snapshot", "rollback"],
        document: { type: "doc", content: [{ type: "paragraph", content: [{ type: "text", text: "当前教师稿正文" }] }] },
      });
      return;
    }
    if (pathname === "/api/cases/copy-case/history") {
      await fulfillJson(route, { versions: [{
        id: "copy-history-v1", number: 1, kind: "manual", title: "复制测试历史稿",
        createdAt: "2026-09-01T08:00:00Z", document: historicalDocument,
      }], events: [] });
      return;
    }
    if (pathname === "/api/cases/copy-case/annotations" || pathname === "/api/tag-groups") {
      await fulfillJson(route, []);
      return;
    }
    if (pathname === "/api/cases/copy-case/sources") {
      await fulfillJson(route, { entries: [] });
      return;
    }
    if (pathname === "/api/cases/copy-case/agent/thread") {
      await fulfillJson(route, {
        id: "copy-thread", title: "复制验收", messages: [], runs: [], writes: [], artifacts: [],
        activeRun: null, latestRun: null, eventSeq: 0,
      });
      return;
    }
    if (pathname === "/api/ai/settings") {
      await fulfillJson(route, { configured: false });
      return;
    }
    if (pathname === "/api/skills") {
      await fulfillJson(route, []);
      return;
    }
    await route.fulfill({ status: 404, contentType: "application/json", body: "{}" });
  });
  return mutations;
}

test("selected history pastes with formatting into rich text and readable text targets", async ({ page, context }) => {
  const mutations = await mockWorkbenchApi(page);
  await page.goto("/#/workbench/copy-case");
  await context.grantPermissions(["clipboard-read", "clipboard-write"], {
    origin: new URL(page.url()).origin,
  });
  await expect(page.getByLabel("案例标题")).toHaveValue("当前教师稿标题");

  await page.getByRole("button", { name: "版本历史" }).click();
  await page.getByRole("button", { name: "查看历史版本 v1 · 复制测试历史稿" }).click();
  await expect(page.locator(".version-paper .canvas-editor h1")).toHaveText("历史稿标题");
  await page.getByRole("button", { name: "复制正文" }).click();
  await expect(page.getByRole("status")).toContainText("已复制");

  await page.evaluate(() => {
    const rich = document.createElement("div");
    rich.id = "rich-paste-target";
    rich.contentEditable = "true";
    rich.setAttribute("aria-label", "富文本粘贴目标");
    rich.style.cssText = "position:fixed;left:8px;bottom:8px;width:420px;min-height:180px;z-index:99999;background:white;";
    const plain = document.createElement("textarea");
    plain.id = "plain-paste-target";
    plain.setAttribute("aria-label", "纯文本粘贴目标");
    plain.style.cssText = "position:fixed;right:8px;bottom:8px;width:420px;height:180px;z-index:99999;background:white;";
    document.body.append(rich, plain);
  });

  const richTarget = page.getByLabel("富文本粘贴目标");
  await richTarget.click();
  await page.keyboard.press("Control+V");
  await expect(richTarget.locator("h1")).toHaveText("历史稿标题");
  await expect(richTarget.locator("p br")).toHaveCount(1);
  await expect(richTarget.locator("ul > li")).toHaveCount(2);
  await expect(richTarget.locator("strong")).toHaveText("加粗");

  const plainTarget = page.getByLabel("纯文本粘贴目标");
  await plainTarget.click();
  await page.keyboard.press("Control+V");
  const plainText = await plainTarget.inputValue();
  expect(plainText).toContain("历史稿标题\n第一行\n第二行加粗");
  expect(plainText).toMatch(/项目一\n+项目二/);
  expect(plainText).not.toContain("当前教师稿正文");
  expect(mutations).toEqual([]);
});
