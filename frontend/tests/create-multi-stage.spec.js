import { test, expect } from "@playwright/test";
import {
  confirmAndSubmitCase,
  fillCaseWizardBasics,
  startCreateCase,
} from "./support/auditFlow.js";
import { login } from "./support/auth.js";

const USER = {
  username: "multi_stage_user",
  password: "MultiStagePass123!",
  nickname: "MultiStageUser",
};

test("create flow restores multi-stage draft and submits complete target_stages", async ({
  page,
}, testInfo) => {
  test.skip(
    testInfo.project.name !== "chromium-desktop",
    "desktop-only: focuses on request payload, not responsive layout"
  );

  const uniqueTitle = `MultiStage测试 ${Date.now()}`;
  const createRequests = [];
  const updateRequests = [];

  await page.route("**/api/auth/login", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        success: true,
        data: {
          id: "mock-user",
          username: USER.username,
          role: "normal",
          nickname: USER.nickname,
          must_change_password: false,
          status: "active",
          token: "mock-token",
        },
      }),
    });
  });

  await page.route("**/api/constants", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        success: true,
        data: {
          case_types: {
            TYPE_A: "思政课教学案例",
            TYPE_B: "课程思政共享资源案例",
            TYPE_C: "实践育人案例",
          },
          themes: ["强国建设", "实践育人", "数字赋能", "铸魂育人"],
          target_stages: {
            undergraduate: "本科生",
            master: "硕士研究生",
            doctor: "博士研究生",
          },
          statuses: {},
        },
      }),
    });
  });

  await page.route("**/api/prompts**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ success: true, data: [] }),
    });
  });

  await page.route(/\/api\/cases(?:\?.*)?$/, async (route) => {
    const request = route.request();
    if (request.method() === "GET") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ success: true, data: [], total: 0 }),
      });
      return;
    }

    if (request.method() !== "POST") {
      await route.continue();
      return;
    }

    const params = new URLSearchParams(request.postData() || "");
    createRequests.push(params);
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        success: true,
        case_id: `case-${createRequests.length}`,
      }),
    });
  });

  await page.route(/\/api\/cases\/[^/]+(?:\/submit)?(?:\?.*)?$/, async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (request.method() === "POST" && url.pathname.endsWith("/submit")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ success: true }),
      });
      return;
    }

    if (request.method() !== "PUT") {
      await route.continue();
      return;
    }

    updateRequests.push(new URLSearchParams(request.postData() || ""));
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ success: true }),
    });
  });

  await page.goto("/");
  await login(page, USER, {
    indicator: "none",
    waitForLoginButton: true,
  });

  await startCreateCase(page);
  await fillCaseWizardBasics(page, {
    title: uniqueTitle,
    department: "测试学院",
    content: "这是用于多学段草稿恢复与提交的案例正文内容。",
  });

  const masterButton = page.getByRole("button", { name: "硕士研究生" });
  await masterButton.click();
  await expect(masterButton).toHaveAttribute("aria-pressed", "true");

  await page.getByRole("button", { name: "保存草稿" }).click();
  await expect(page.getByText("草稿已保存")).toBeVisible();

  const savedDraft = await page.evaluate(() =>
    JSON.parse(localStorage.getItem("case_library_create_case_draft"))
  );
  expect(savedDraft.form.target_stages).toEqual(["undergraduate", "master"]);
  expect(JSON.parse(createRequests[0].get("target_stages"))).toEqual([
    "undergraduate",
    "master",
  ]);

  await page.reload();
  await expect(page.getByText("填写案例基本信息")).toBeVisible();
  await page.getByRole("button", { name: "继续" }).click();
  await expect(page.getByText("撰写案例内容")).toBeVisible();
  await page.getByRole("button", { name: "继续" }).click();
  await expect(page.getByText("选择分类")).toBeVisible();
  await expect(page.getByRole("button", { name: "本科生" })).toHaveAttribute(
    "aria-pressed",
    "true"
  );
  await expect(page.getByRole("button", { name: "硕士研究生" })).toHaveAttribute(
    "aria-pressed",
    "true"
  );

  await page.getByRole("button", { name: "继续" }).click();
  await expect(page.getByRole("heading", { name: "AI 智能内容审核" })).toBeVisible();
  await page.getByRole("button", { name: "继续" }).click();
  await expect(page.getByText("本科生、硕士研究生")).toBeVisible();
  const submitRequestPromise = page.waitForRequest((request) => {
    const url = new URL(request.url());
    return request.method() === "POST" && url.pathname.endsWith("/submit");
  });
  await confirmAndSubmitCase(page);
  const submitRequest = await submitRequestPromise;

  expect(createRequests).toHaveLength(1);
  expect(updateRequests).toHaveLength(1);
  expect(JSON.parse(updateRequests[0].get("target_stages"))).toEqual([
    "undergraduate",
    "master",
  ]);
  expect(new URL(submitRequest.url()).pathname.split("/").at(-2)).toBe("case-1");
});
