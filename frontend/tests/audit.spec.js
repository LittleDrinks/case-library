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
  await page.screenshot({
    path: testInfo.outputPath(`${name}-${testInfo.project.name}.png`),
    fullPage: true,
  });
}

test.describe("manual audit candidate flows", () => {
  test("default admin account is present but requires password change", async ({ page }, testInfo) => {
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

    await expect(page.getByRole("heading", { name: "修改初始密码" })).toBeVisible();
    await capture(page, testInfo, "default-admin-password-change");
  });

  test("author submit -> admin approve -> public search, with audit screenshots", async ({
    page,
  }, testInfo) => {
    test.skip(
      testInfo.project.name !== "chromium-desktop",
      "desktop-only audit because screenshots target desktop design alignment"
    );

    const title = `Audit案例 ${Date.now()}`;
    page.on("dialog", (dialog) => {
      dialog.accept();
    });
    await page.route("**/api/cases/*/ai-review", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          success: true,
          status: "ok",
          data: {
            version: {
              version_number: 2,
              paragraphs: [
                { paragraph_id: "p1", text: "本案例用于端到端审计测试。" },
                { paragraph_id: "p2", text: "来源材料用于验证版本快照。" },
              ],
              source_material: "E2E 来源材料：学院新闻与课堂反馈摘录。",
            },
            comments: [
              {
                id: "c1",
                paragraph_id: "p2",
                category: "source",
                severity: "important",
                message: "E2E AI 段落批注：请补充来源材料中的时间和参与对象。",
                suggestion: "补充课堂反馈证据。",
              },
            ],
            summary: {
              suggested_next_steps: ["补充课堂反馈证据。"],
            },
          },
        }),
      });
    });

    await page.goto("/");
    await capture(page, testInfo, "home-public");

    await login(page, USER);
    await capture(page, testInfo, "home-authenticated-user");

    await page.getByRole("link", { name: "创建案例" }).click();
    await expect(page.getByText("填写基本信息")).toBeVisible();
    await capture(page, testInfo, "create-step-1");

    await page.getByLabel(/案例标题/).fill(title);
    await page.getByLabel(/所属部门\/学院/).fill("马克思主义学院");
    await page.getByRole("button", { name: "继续" }).click();

    await expect(page.getByText("编写案例内容")).toBeVisible();
    await page.locator("#ccf-content").fill(
      "本案例用于端到端审计测试。内容包含教学背景、问题分析、课堂实施、学生反馈和改进反思，用于验证创建、审核、公开展示的完整链路。"
    );
    await page.locator("#ccf-source").fill("E2E 来源材料：学院新闻与课堂反馈摘录。");
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
    await expect(page.getByText(/已生成 v2 只读审核版本/)).toBeVisible();
    await expect(page.getByText("p2：E2E AI 段落批注：请补充来源材料中的时间和参与对象。")).toBeVisible();
    await capture(page, testInfo, "create-step-4-ai-results");
    await page.getByRole("button", { name: "继续" }).click();

    await expect(page.getByText("确认并提交")).toBeVisible();
    await expect(page.getByText("专家人工审核流程")).toBeVisible();
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
    await expect(pendingCard.getByText(/已生成 v2 只读审核版本/)).toBeVisible();
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
    await publicCard.getByRole("button", { name: "查看详情" }).click();
    await expect(page.locator(".detail-source").getByText("来源材料：", { exact: true })).toBeVisible();
    await expect(page.getByText("E2E 来源材料：学院新闻与课堂反馈摘录。")).toBeVisible();
    await expect(page.getByText("作者 AI 自查意见")).toHaveCount(0);
    await capture(page, testInfo, "public-approved-search-result");
  });
});
