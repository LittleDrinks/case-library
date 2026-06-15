import { expect } from "@playwright/test";
import { login, logout } from "./auth.js";
import { capture } from "./capture.js";

const DEFAULT_AUDIT_CASE_CONTENT =
  "本案例用于端到端审计测试。内容包含教学背景、问题分析、课堂实施、学生反馈和改进反思，用于验证创建、审核、公开展示的完整链路。";

const DEFAULT_AUDIT_CASE_SOURCE = "E2E 来源材料：学院新闻与课堂反馈摘录。";

export async function createAndSubmitAuditCase(page, testInfo, { title }) {
  await page.getByRole("link", { name: "创建案例" }).click();
  await expect(page.getByText("填写基本信息")).toBeVisible();
  await capture(page, testInfo, "create-step-1");

  await page.getByLabel(/案例标题/).fill(title);
  await page.getByLabel(/所属部门\/学院/).fill("马克思主义学院");
  await page.getByRole("button", { name: "继续" }).click();

  await expect(page.getByText("编写案例内容")).toBeVisible();
  await page.locator("#ccf-content").fill(DEFAULT_AUDIT_CASE_CONTENT);
  await page.locator("#ccf-source").fill(DEFAULT_AUDIT_CASE_SOURCE);
  await capture(page, testInfo, "create-step-2");
  await page.getByRole("button", { name: "继续" }).click();

  await expect(page.getByText("选择案例分类")).toBeVisible();
  await page.locator("#ccf-type").selectOption("TYPE_A");
  await page.locator("#ccf-theme").selectOption("铸魂育人");
  await capture(page, testInfo, "create-step-3");
  await page.getByRole("button", { name: "继续" }).click();

  await expect(page.getByRole("heading", { name: "提交前自查" })).toBeVisible();
  await expect(page.getByText("生成只读审核版本")).toBeVisible();
  await page.getByRole("button", { name: "生成只读审核版本" }).click();
  await expect(page.getByText("100% 已完成")).toBeVisible();
  await expect(page.getByText(/已生成 v2 只读审核版本/)).toBeVisible();
  await expect(page.getByText("版本正文")).toBeVisible();
  await expect(page.getByText("AI 批注")).toBeVisible();
  await expect(page.getByText("来源材料用于验证版本快照。")).toBeVisible();
  await expect(page.getByText("E2E AI 段落批注：请补充来源材料中的时间和参与对象。")).toBeVisible();
  await capture(page, testInfo, "create-step-4-ai-results");
  await page.getByRole("button", { name: "继续" }).click();

  await expect(page.getByText("确认并提交")).toBeVisible();
  await expect(page.getByText("专家人工审核流程")).toBeVisible();
  await capture(page, testInfo, "create-step-5-submit");
  await page.getByRole("button", { name: "正式提交案例" }).click();
  await expect(page.getByText("填写基本信息")).toBeVisible();

  await page.getByRole("link", { name: "我的提交" }).click();
  const teacherPendingCard = page.locator(".case-card").filter({ hasText: title });
  await expect(teacherPendingCard).toBeVisible();
  await teacherPendingCard.getByRole("button", { name: "查看详情" }).click();
  await expect(teacherPendingCard.getByText("历史版本")).toBeVisible();
  await expect(teacherPendingCard.getByText("来源材料", { exact: true }).first()).toBeVisible();
  await expect(teacherPendingCard.getByText(DEFAULT_AUDIT_CASE_SOURCE).first()).toBeVisible();
  await expect(teacherPendingCard.getByRole("button", { name: "复制版本" }).first()).toBeVisible();
  await capture(page, testInfo, "teacher-version-history");
}

export async function approveAuditCaseAndVerifyPublicSearch(page, testInfo, { admin, title }) {
  await logout(page);
  await login(page, admin);
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
  await expect(pendingCard.getByText("提交版本")).toBeVisible();
  await expect(pendingCard.getByText("p1").first()).toBeVisible();
  await capture(page, testInfo, "admin-pending-review");
  await pendingCard.getByRole("button", { name: "审核" }).click();
  await expect(page.locator("#review-version")).toHaveValue(/^\d+$/);
  await page.locator("#review-comment").fill("审计测试：审核通过。");
  await page.locator("#paragraph-id").selectOption("p1");
  await page.locator("#paragraph-category").selectOption("source");
  await page.locator("#paragraph-severity").selectOption("important");
  await page.locator("#paragraph-message").fill("审计测试：补充来源材料中的时间和参与对象。");
  await page.locator("#paragraph-suggestion").fill("补充学院新闻链接和课堂反馈摘要。");
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
  await expect(page.getByText(DEFAULT_AUDIT_CASE_SOURCE)).toBeVisible();
  await expect(page.getByText("作者 AI 自查意见")).toHaveCount(0);
  await capture(page, testInfo, "public-approved-search-result");
  await page.getByLabel("关闭").click();
}
