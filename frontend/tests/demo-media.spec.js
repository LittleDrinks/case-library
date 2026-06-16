import { test, expect } from "@playwright/test";
import { login, logout } from "./support/auth.js";
import {
  confirmAndSubmitCase,
  expectPendingSubmission,
  startCreateCase,
  submitAdminReview,
} from "./support/auditFlow.js";
import { cleanupAuditCases } from "./support/caseCleanup.js";

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

const TITLE = `DemoMedia案例 ${Date.now()}`;
const INITIAL_CONTENT = [
  "Demo media 案例第一段，说明教学背景、课堂目标和学生参与情况。",
  "Demo media 案例第二段，保留来源材料补充点，用于展示 AI 和人工批注。",
].join("\n");
const SOURCE_MATERIAL = "Demo media 来源材料：学院新闻、课堂反馈与访谈记录摘录。";
const ADMIN_PARAGRAPH_COMMENT = "Demo media 人工批注：请补充来源材料中的时间和参与对象。";
const ADMIN_SUGGESTION = "补充学院新闻日期、参与学生和课堂反馈摘要。";

async function mockAiReview(page) {
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
              { paragraph_id: "p1", text: "Demo media 案例第一段，说明教学背景、课堂目标和学生参与情况。" },
              { paragraph_id: "p2", text: "Demo media 案例第二段，保留来源材料补充点，用于展示 AI 和人工批注。" },
            ],
            source_material: SOURCE_MATERIAL,
          },
          comments: [
            {
              id: "demo-media-ai-comment",
              paragraph_id: "p2",
              category: "source",
              severity: "important",
              message: "Demo media AI 批注：来源材料需要补充时间和参与对象。",
              suggestion: "提交人工审核前补充可核验来源。",
            },
          ],
          summary: {
            suggested_next_steps: ["补充可核验来源。"],
          },
        },
      }),
    });
  });
}

async function openMySubmissionDetail(page, title) {
  await page.getByRole("link", { name: "我的材料" }).click();
  const caseCard = page.locator(".case-card").filter({ hasText: title });
  await expect(caseCard).toBeVisible();
  await caseCard.getByRole("button", { name: "查看详情" }).click();
  return caseCard;
}

async function openPendingAdminCard(page, title) {
  await page.getByRole("link", { name: "审核管理" }).click();
  await expect(page.getByRole("tab", { name: "待审核" })).toHaveAttribute(
    "aria-selected",
    "true"
  );
  const caseCard = page.locator(".case-card").filter({ hasText: title });
  await expect(caseCard).toBeVisible();
  return caseCard;
}

test.describe.serial("baseline demo media", () => {
  test.beforeEach(async ({ page }, testInfo) => {
    test.skip(
      testInfo.project.name !== "chromium-desktop",
      "baseline demo videos are recorded only for the desktop viewport"
    );
    page.on("dialog", (dialog) => dialog.accept());
    await mockAiReview(page);
  });

  test.afterAll(async ({ browser }, testInfo) => {
    if (testInfo.project.name !== "chromium-desktop") {
      return;
    }

    const page = await browser.newPage();
    try {
      await page.goto("/");
      await login(page, ADMIN);
      await cleanupAuditCases(page, TITLE);
    } finally {
      await page.close();
    }
  });

  test("01 teacher creates and submits an AI-reviewed case", async ({ page }) => {
    await page.goto("/");
    await login(page, ADMIN);
    await cleanupAuditCases(page, TITLE);
    await logout(page, { waitForLoginButton: true });

    await login(page, USER);
    await startCreateCase(page);

    await expect(page.getByText("填写案例基本信息")).toBeVisible();
    await page.getByLabel(/案例标题/).fill(TITLE);
    await page.getByLabel(/所属部门\/学院/).fill("马克思主义学院");
    await page.getByRole("button", { name: "继续" }).click();

    await expect(page.getByText("撰写案例内容")).toBeVisible();
    await page.locator("#ccf-content").fill(INITIAL_CONTENT);
    await page.locator("#ccf-source").fill(SOURCE_MATERIAL);
    await page.getByRole("button", { name: "继续" }).click();

    await expect(page.getByText("选择分类")).toBeVisible();
    await page.getByRole("button", { name: "思政课教学案例" }).click();
    await page.getByRole("button", { name: "铸魂育人" }).click();
    await page.getByRole("button", { name: "继续" }).click();

    await expect(page.getByRole("heading", { name: "AI 智能内容审核" })).toBeVisible();
    await page.getByRole("button", { name: "生成自查建议" }).click();
    await expect(page.getByText("100%")).toBeVisible();
    await expect(page.getByText("Demo media AI 批注：来源材料需要补充时间和参与对象。")).toBeVisible();
    await page.getByRole("button", { name: "继续" }).click();

    await expect(page.getByText("确认并提交")).toBeVisible();
    await confirmAndSubmitCase(page);
    await expectPendingSubmission(page, TITLE);

    await openMySubmissionDetail(page, TITLE);
    await expect(page.getByRole("heading", { name: TITLE })).toBeVisible();
    await expect(page.getByText("历史版本")).toBeVisible();
    await expect(page.getByText(SOURCE_MATERIAL).first()).toBeVisible();
  });

  test("02 admin reviews a submitted version with paragraph comments", async ({ page }) => {
    await page.goto("/");
    await login(page, ADMIN);

    const pendingCard = await openPendingAdminCard(page, TITLE);
    await pendingCard.getByRole("button", { name: "查看详情" }).click();
    await expect(page.getByRole("heading", { name: TITLE })).toBeVisible();
    await expect(page.getByText("版本预览")).toBeVisible();
    await expect(page.getByText(INITIAL_CONTENT.split("\n")[1])).toBeVisible();
    await expect(page.getByText(SOURCE_MATERIAL)).toBeVisible();

    await page.getByRole("button", { name: "审核此案例" }).click();
    await submitAdminReview(page, {
      status: "reject",
      comment: "退回修改：来源材料不足。",
      paragraphId: "p2",
      paragraphMessage: ADMIN_PARAGRAPH_COMMENT,
      paragraphSuggestion: ADMIN_SUGGESTION,
    });
  });

  test("03 author views review comments and resubmits a revision", async ({ page }) => {
    await page.goto("/");
    await login(page, USER);
    await page.getByRole("link", { name: "我的材料" }).click();
    await page.getByRole("tab", { name: "需修改" }).click();

    const revisionCard = page.locator(".case-card").filter({ hasText: TITLE });
    await expect(revisionCard).toBeVisible();
    await revisionCard.getByRole("button", { name: "查看详情" }).click();
    await expect(page.getByRole("heading", { name: TITLE })).toBeVisible();
    await page.getByRole("button", { name: "显示审核结果" }).click();
    await expect(page.getByText("人工段落批注", { exact: true })).toBeVisible();
    await expect(page.getByText(ADMIN_PARAGRAPH_COMMENT)).toBeVisible();
    await expect(page.getByText(ADMIN_SUGGESTION)).toBeVisible();
    await page.getByRole("button", { name: "复制" }).first().click();
    await expect(page.getByText(/v\d+ 已复制/)).toBeVisible();

    await page.getByRole("button", { name: "修改案例" }).click();
    await expect(page).toHaveURL(/#create\?draft=/);
    await expect(page.getByRole("heading", { name: "撰写案例内容" })).toBeVisible();
    await page.locator("#ccf-content").fill(`${INITIAL_CONTENT}\n已补充来源材料时间、参与对象和课堂反馈摘要。`);
    await page.locator("#ccf-source").fill(`${SOURCE_MATERIAL}\n补充：2026 年课堂反馈摘要。`);
    await page.getByRole("button", { name: "继续" }).click();
    await expect(page.getByText("选择分类")).toBeVisible();
    await page.getByRole("button", { name: "继续" }).click();
    await expect(page.getByRole("heading", { name: "AI 智能内容审核" })).toBeVisible();
    await page.getByRole("button", { name: "继续" }).click();
    await expect(page.getByText("确认并提交")).toBeVisible();
    await confirmAndSubmitCase(page);
    await expectPendingSubmission(page, TITLE);
  });

  test("04 public home and library browse approved case without review internals", async ({ page }) => {
    await page.goto("/");
    await login(page, ADMIN);
    const resubmittedCard = await openPendingAdminCard(page, TITLE);
    await resubmittedCard.getByRole("button", { name: "查看详情" }).click();
    await expect(page.getByRole("heading", { name: TITLE })).toBeVisible();
    await expect(page.getByText("已补充来源材料时间")).toBeVisible();
    await page.getByRole("button", { name: "审核此案例" }).click();
    await submitAdminReview(page, {
      status: "approve",
      comment: "审核通过：退回意见已修改。",
    });
    await logout(page, { waitForLoginButton: true });

    await page.getByRole("link", { name: "首页" }).click();
    await expect(page.getByRole("heading", { name: "最新案例" })).toBeVisible();
    const latestHomeCard = page
      .getByLabel("最新案例")
      .locator(".case-card")
      .filter({ hasText: TITLE });
    await expect(latestHomeCard).toBeVisible();
    await expect(latestHomeCard.getByText("已补充来源材料时间")).toBeVisible();
    await expect(latestHomeCard.getByText(ADMIN_PARAGRAPH_COMMENT)).toHaveCount(0);

    await page.getByRole("link", { name: "案例库" }).click();
    await page.locator(".filter-selects select").first().selectOption("TYPE_A");
    await page.locator(".filter-selects select").nth(1).selectOption("铸魂育人");
    await page.getByPlaceholder("搜索案例标题、内容...").fill(TITLE);
    await page.getByRole("button", { name: "搜索" }).click();

    const publicCard = page.locator(".case-card").filter({ hasText: TITLE });
    await expect(publicCard).toBeVisible();
    await publicCard.getByRole("button", { name: "查看详情" }).click();
    await expect(page.getByRole("heading", { name: TITLE })).toBeVisible();
    await expect(page.getByText("已补充来源材料时间")).toBeVisible();
    await expect(page.getByText(SOURCE_MATERIAL)).toBeVisible();
    await expect(page.getByText(ADMIN_PARAGRAPH_COMMENT)).toHaveCount(0);
    await expect(page.getByText("Demo media AI 批注")).toHaveCount(0);
  });
});
