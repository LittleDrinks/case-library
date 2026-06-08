import { test, expect } from "@playwright/test";

const USER = {
  username: "e2e_user",
  password: "E2eUserPass123!",
  nickname: "E2E作者",
};

const ADMIN = {
  username: "e2e_admin",
  password: "E2eAdminPass123!",
  nickname: "E2E管理员",
};

async function login(page, account) {
  await page.getByRole("button", { name: "登录" }).click();
  await page.getByLabel("用户名").fill(account.username);
  await page.getByLabel("密码").fill(account.password);
  await page.locator(".modal-panel").getByRole("button", { name: "登录" }).click();
  await expect(page.locator(".user-name")).toContainText(account.nickname);
}

async function logout(page) {
  await page.getByRole("button", { name: "退出" }).click();
  await expect(page.getByRole("button", { name: "登录" })).toBeVisible();
}

async function capture(page, testInfo, name) {
  const isCreateVisual = name.startsWith("create-step") || name.startsWith("create-mobile");
  await page.screenshot({
    path: testInfo.outputPath(`${name}-${testInfo.project.name}.png`),
    fullPage: !isCreateVisual,
  });
}

async function expectCreateShellVisualStructure(page) {
  const railBox = await page.locator(".wizard-rail").boundingBox();
  expect(railBox?.width).toBeGreaterThanOrEqual(320);

  const mainBox = await page.locator(".wizard-main").boundingBox();
  expect(mainBox?.x).toBeGreaterThanOrEqual(railBox.width);

  await expect(page.locator(".rail-step.active")).toHaveCSS("background-color", "rgb(255, 245, 246)");
  await expect(page.locator(".rail-progress-bar")).toHaveCSS("background-color", "rgb(23, 201, 100)");
}

async function expectAiReviewVisualStructure(page) {
  const grid = page.locator("[data-testid='ai-review-grid']");
  const firstCard = grid.locator(".ai-review-card").nth(0);
  const secondCard = grid.locator(".ai-review-card").nth(1);
  const scoreCard = grid.locator(".score-summary-card");

  const firstBox = await firstCard.boundingBox();
  const secondBox = await secondCard.boundingBox();
  expect(firstBox?.y).toBeCloseTo(secondBox.y, 4);
  expect(secondBox.x).toBeGreaterThan(firstBox.x + firstBox.width * 0.8);

  await expect(page.locator(".review-progress-bar")).toHaveCSS("background-color", "rgb(192, 0, 36)");
  await expect(scoreCard).toHaveCSS("border-top-color", "rgb(192, 0, 36)");
  await expect(scoreCard.locator(".score-ring")).toBeVisible();
}

async function expectSubmitVisualStructure(page) {
  await expect(page.locator(".pass-notice")).toHaveCSS("border-top-color", "rgb(239, 199, 206)");
  await expect(page.locator(".submit-card")).toHaveCSS("border-top-color", "rgb(239, 199, 206)");
  await expect(page.locator(".status-pill")).toContainText("待审核");
  await expect(page.getByText("AI 自查结果仅作为专家参考")).toBeVisible();
}

test.describe("manual audit candidate flows", () => {
  test("default admin account is present and handles password-change state", async ({ page }, testInfo) => {
    test.skip(
      testInfo.project.name !== "chromium-desktop",
      "desktop-only audit because mobile hides the username text"
    );

    await page.goto("/");
    await login(page, {
      username: "10000002",
      password: "default123456",
      nickname: "小李",
    });

    const passwordChangeHeading = page.getByRole("heading", { name: "修改初始密码" });
    if (await passwordChangeHeading.isVisible().catch(() => false)) {
      await capture(page, testInfo, "default-admin-password-change");
    } else {
      await expect(page.locator(".user-name")).toContainText("小李");
      await capture(page, testInfo, "default-admin-login-state");
    }
  });

  test("author submit -> admin approve -> public search, with audit screenshots", async ({
    page,
  }, testInfo) => {
    test.skip(
      testInfo.project.name !== "chromium-desktop",
      "desktop-only audit because screenshots target desktop design alignment"
    );

    const title = `Audit案例 ${Date.now()}`;
    const dialogMessages = [];
    page.on("dialog", (dialog) => {
      dialogMessages.push(dialog.message());
      dialog.accept();
    });
    await page.route("**/api/ai/chat", async (route) => {
      const request = route.request();
      const payload = request.postDataJSON();
      const names = {
        "workflow/completeness": "完整性检查",
        "workflow/categorization": "分类检查",
        "workflow/expression": "表达检查",
        "workflow/score": "综合评分",
      };
      const promptName = names[payload.prompt_id] || payload.prompt_id;
      const parsed =
        payload.prompt_id === "workflow/score"
          ? {
              pass: false,
              score: 62,
              detail: "E2E AI 自查：综合风险偏高，建议修改后再提交。",
              suggestions: ["补充课堂反馈证据。"],
            }
          : {
              pass: true,
              detail: `E2E AI 自查：${promptName}通过。`,
              suggestions: ["保留关键教学过程描述。"],
            };
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          success: true,
          answer: JSON.stringify(parsed),
          parsed,
          parse_error: null,
        }),
      });
    });

    await page.goto("/");
    await capture(page, testInfo, "home-public");

    await login(page, USER);
    await capture(page, testInfo, "home-authenticated-user");

    await page.getByRole("link", { name: "创建案例" }).click();
    await expect(page.getByText("填写基本信息")).toBeVisible();
    await expectCreateShellVisualStructure(page);
    await capture(page, testInfo, "create-step-1");

    await page.getByLabel(/案例标题/).fill(title);
    await page.getByLabel(/所属部门\/学院/).fill("马克思主义学院");
    await page.getByRole("button", { name: "继续" }).click();

    await expect(page.getByText("编写案例内容")).toBeVisible();
    await page.locator("#ccf-content").fill(
      "本案例用于端到端审计测试。内容包含教学背景、问题分析、课堂实施、学生反馈和改进反思，用于验证创建、审核、公开展示的完整链路。"
    );
    await capture(page, testInfo, "create-step-2");
    await page.getByRole("button", { name: "继续" }).click();

    await expect(page.getByText("选择案例分类")).toBeVisible();
    await page.locator("#ccf-type").selectOption("TYPE_A");
    await page.locator("#ccf-theme").selectOption("铸魂育人");
    await capture(page, testInfo, "create-step-3");
    await page.getByRole("button", { name: "继续" }).click();

    await expect(page.getByRole("heading", { name: "提交前自查" })).toBeVisible();
    await expect(page.getByText("运行全部自查")).toBeVisible();
    await page.getByRole("button", { name: "运行全部自查" }).click();
    await expect(page.getByText("E2E AI 自查：完整性检查通过。")).toBeVisible();
    await expect(page.getByText("E2E AI 自查：综合风险偏高，建议修改后再提交。")).toBeVisible();
    await expectAiReviewVisualStructure(page);
    await capture(page, testInfo, "create-step-4-ai-results");
    await page.getByRole("button", { name: "继续" }).click();
    await expect
      .poll(() => dialogMessages.some((message) => message.includes("AI 自查提示当前案例可能还需要修改")))
      .toBe(true);

    await expect(page.getByText("确认并提交")).toBeVisible();
    await expect(page.getByText("专家人工审核流程")).toBeVisible();
    await expectSubmitVisualStructure(page);
    await capture(page, testInfo, "create-step-5-submit");
    await page.getByRole("button", { name: "正式提交案例" }).click();
    await expect(page.getByText("填写基本信息")).toBeVisible();

    await logout(page);
    await login(page, ADMIN);
    await page.getByRole("link", { name: "审核管理" }).click();
    await expect(page.getByRole("tab", { name: "待审核" })).toHaveAttribute(
      "aria-selected",
      "true"
    );

    const pendingCard = page.locator(".case-card").filter({ hasText: title });
    await expect(pendingCard).toBeVisible();
    await pendingCard.getByRole("button", { name: "查看详情" }).click();
    await expect(pendingCard.getByText("作者 AI 自查意见")).toBeVisible();
    await expect(pendingCard.getByText("E2E AI 自查：分类检查通过。")).toBeVisible();
    await expect(pendingCard.getByText("E2E AI 自查：综合风险偏高，建议修改后再提交。")).toBeVisible();
    await capture(page, testInfo, "admin-pending-review");
    await pendingCard.getByRole("button", { name: "审核" }).click();
    await page.locator("#review-comment").fill("审计测试：审核通过。");
    await page.getByLabel("通过").check();
    await capture(page, testInfo, "admin-review-modal");
    await page.getByRole("button", { name: "提交审核" }).click();
    await expect(page.locator(".modal-overlay")).toHaveCount(0);

    await logout(page);
    await page.getByRole("link", { name: "案例库" }).click();
    await page.getByPlaceholder("搜索案例标题、内容...").fill(title);
    await page.getByRole("button", { name: "搜索" }).click();

    const publicCard = page.locator(".case-card").filter({ hasText: title });
    await expect(publicCard).toBeVisible();
    await capture(page, testInfo, "public-approved-search-result");
  });

  test("create flow visual shell is stable on mobile", async ({ page }, testInfo) => {
    test.skip(
      testInfo.project.name !== "chromium-mobile",
      "mobile-only visual regression coverage"
    );

    await page.goto("/");
    await login(page, USER);
    await page.getByRole("link", { name: "创建案例" }).click();
    await expect(page.getByText("填写基本信息")).toBeVisible();
    await expect(page.locator(".wizard-rail-mobile")).toBeVisible();
    await expect(page.locator(".wizard-rail")).not.toBeVisible();

    const horizontalOverflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1);
    expect(horizontalOverflow).toBe(false);

    await capture(page, testInfo, "create-mobile-step-1");
  });
});
