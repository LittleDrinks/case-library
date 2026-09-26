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
  content: [{
    type: "orderedList",
    attrs: { start: 3 },
    content: [
      {
        type: "listItem",
        content: [
          { type: "paragraph", content: [{ type: "text", text: "历史编号一" }] },
          {
            type: "orderedList",
            attrs: { start: 6 },
            content: [{
              type: "listItem",
              content: [{ type: "paragraph", content: [{ type: "text", text: "嵌套历史项" }] }],
            }],
          },
        ],
      },
      {
        type: "listItem",
        content: [{ type: "paragraph", content: [{ type: "text", text: "历史编号二" }] }],
      },
    ],
  }],
};

function orderedLists(node, found = []) {
  if (node.type === "orderedList") found.push(node);
  node.content?.forEach((child) => orderedLists(child, found));
  return found;
}

async function fulfillJson(route, value) {
  await route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify(value),
  });
}

async function mockWorkbenchApi(page) {
  let currentCase = {
    id: "copy-case",
    title: "当前教师稿标题",
    revision: 3,
    ownerId: "copy-user",
    workflowStatus: "draft",
    publicationStatus: "none",
    availableActions: ["submit", "snapshot", "rollback"],
    document: {
      type: "doc",
      content: [{ type: "paragraph", content: [{ type: "text", text: "当前教师稿正文" }] }],
    },
  };
  const mutations = [];
  const saves = [];

  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const { pathname } = new URL(request.url());

    if (request.method() === "PATCH" && pathname === "/api/cases/copy-case") {
      const payload = request.postDataJSON();
      mutations.push(`${request.method()} ${pathname}`);
      saves.push(payload);
      currentCase = {
        ...currentCase,
        title: payload.title,
        document: payload.document,
        revision: currentCase.revision + 1,
      };
      await fulfillJson(route, currentCase);
      return;
    }
    if (request.method() !== "GET") {
      mutations.push(`${request.method()} ${pathname}`);
      await route.fulfill({ status: 405, contentType: "application/json", body: "{}" });
      return;
    }
    if (pathname === "/api/auth/session") {
      await fulfillJson(route, {
        user: { id: "copy-user", role: "user" }, csrfToken: "copy-csrf",
      });
      return;
    }
    if (pathname === "/api/cases/copy-case") {
      await fulfillJson(route, currentCase);
      return;
    }
    if (pathname === "/api/cases/copy-case/history") {
      await fulfillJson(route, {
        versions: [{
          id: "copy-history-v1", number: 1, kind: "manual", title: "编号列表历史稿",
          createdAt: "2026-09-01T08:00:00Z", document: historicalDocument,
        }],
        events: [],
      });
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
        id: "copy-thread", title: "编号列表验收", messages: [], runs: [], writes: [], artifacts: [],
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

  return { mutations, saves };
}

test("工具栏创建的编号列表自动保存并在刷新后保留", async ({ page }) => {
  const { saves } = await mockWorkbenchApi(page);
  await page.goto("/#/workbench/copy-case");
  await expect(page.getByLabel("案例标题")).toHaveValue("当前教师稿标题");

  const editor = page.locator(".canvas-editor").first();
  await editor.locator("p").click();
  await page.getByRole("button", { name: "编号列表", exact: true }).click();
  await expect(editor.locator("ol > li")).toContainText("当前教师稿正文");
  await expect(page.locator(".save-state")).toHaveText("已保存", { timeout: 5000 });

  const savedLists = orderedLists(saves.at(-1).document);
  expect(savedLists).toHaveLength(1);
  expect(savedLists[0].attrs).toEqual({ start: 1 });

  await page.reload();
  await expect(page.locator(".canvas-editor ol > li")).toContainText("当前教师稿正文");
});

test("历史编号列表可复制粘贴、自动保存并刷新保留起点和嵌套", async ({ page, context }) => {
  const { mutations, saves } = await mockWorkbenchApi(page);
  await page.goto("/#/workbench/copy-case");
  await context.grantPermissions(["clipboard-read", "clipboard-write"], { origin: baseOrigin });
  await expect(page.getByLabel("案例标题")).toHaveValue("当前教师稿标题");

  await page.getByRole("button", { name: "历史版本" }).click();
  await page.getByRole("button", { name: "查看历史版本 v1 · 编号列表历史稿" }).click();
  await expect(page.locator(".version-paper .canvas-editor ol[start='3'] ol[start='6']"))
    .toHaveCount(1);
  await page.getByRole("button", { name: "复制正文" }).click();
  await expect(page.getByRole("status")).toContainText("已复制");
  expect(mutations).toEqual([]);

  await page.getByRole("tab", { name: "当前教师稿" }).click();
  const editor = page.locator(".canvas-editor").first();
  await editor.locator("p").click();
  await page.keyboard.press("Control+End");
  await page.keyboard.press("Control+V");
  await expect.poll(() => saves.length, { timeout: 5000 }).toBe(1);
  await expect(page.locator(".save-state")).toHaveText("已保存");

  let savedLists = orderedLists(saves.at(-1).document);
  expect(savedLists.map((list) => list.attrs.start)).toEqual([3, 6]);
  expect(savedLists.every((list) => Object.keys(list.attrs).join() === "start")).toBe(true);
  expect(mutations).toEqual(["PATCH /api/cases/copy-case"]);

  await page.reload();
  const savedEditor = page.locator(".canvas-editor").first();
  await expect(savedEditor.locator("ol[start='3'] ol[start='6']")).toContainText("嵌套历史项");

  const nestedParagraph = savedEditor.locator("ol[start='3'] ol[start='6'] p");
  await nestedParagraph.click();
  await page.keyboard.press("End");
  await page.keyboard.type("后续编辑");
  await expect(nestedParagraph).toContainText("嵌套历史项后续编辑");
  await expect(page.locator(".save-state")).toHaveText("已保存", { timeout: 5000 });

  savedLists = orderedLists(saves.at(-1).document);
  expect(savedLists.map((list) => list.attrs.start)).toEqual([3, 6]);
  await page.reload();
  await expect(page.locator(".canvas-editor ol[start='3'] ol[start='6'] p"))
    .toContainText("嵌套历史项后续编辑");
});
