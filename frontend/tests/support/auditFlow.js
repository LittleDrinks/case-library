import { expect } from "@playwright/test";
import { login, logout } from "./auth.js";
import { capture } from "./capture.js";

const DEFAULT_AUDIT_CASE_CONTENT =
  "本案例用于端到端审计测试。内容包含教学背景、问题分析、课堂实施、学生反馈和改进反思，用于验证创建、审核、公开展示的完整链路。";

const DEFAULT_AUDIT_CASE_SOURCE = "E2E 来源材料：学院新闻与课堂反馈摘录。";

export async function confirmAndSubmitCase(page) {
  await page.getByLabel("我确认本案例内容真实、原创，引用材料已注明来源。").check();
  await page.getByLabel("我了解提交后案例将进入专家人工审核流程。").check();
  await page.getByRole("button", { name: "正式提交案例" }).click();
}

export async function expectPendingSubmission(page, title) {
  await expect(page.getByRole("heading", { name: "我的提交" })).toBeVisible();
  await expect(page.getByRole("tab", { name: "全部" })).toHaveAttribute(
    "aria-selected",
    "true"
  );
  const pendingCard = page.locator(".case-card").filter({ hasText: title });
  await expect(pendingCard).toBeVisible();
  await expect(pendingCard).toContainText("待审核");
  return pendingCard;
}

export async function submitAdminReview(page, {
  status = "approve",
  comment,
  paragraphId,
  paragraphCategory = "source",
  paragraphSeverity = "important",
  paragraphMessage,
  paragraphSuggestion,
  captureBeforeSubmit,
} = {}) {
  const workspace = page.locator(".review-workspace");
  await expect(workspace).toBeVisible();
  await expect(workspace.getByText("提交版本", { exact: true })).toBeVisible();

  if (comment) {
    await page.locator("#review-comment").fill(comment);
  }

  if (paragraphId && paragraphMessage) {
    const paragraph = page.locator(`[data-paragraph-id="${paragraphId}"]`);
    await expect(paragraph).toBeVisible();
    await paragraph.click();
    await expect(page.locator(".review-side-panel")).toContainText(`当前：${paragraphId}`);
    await page.locator("#paragraph-category").selectOption(paragraphCategory);
    await page.locator("#paragraph-severity").selectOption(paragraphSeverity);
    await page.locator("#paragraph-message").fill(paragraphMessage);
    if (paragraphSuggestion) {
      await page.locator("#paragraph-suggestion").fill(paragraphSuggestion);
    }
    await page.getByRole("button", { name: "添加批注" }).click();
    await expect(paragraph.getByText("待提交批注")).toBeVisible();
    await expect(paragraph.getByText(paragraphMessage)).toBeVisible();
  }

  await page.getByLabel(status === "approve" ? "通过" : "需修改").check();
  if (captureBeforeSubmit) {
    await captureBeforeSubmit();
  }
  await page.getByRole("button", { name: "提交审核" }).click();
  await expect(workspace).toHaveCount(0);
  await expect(page.getByRole("tab", { name: "待审核" })).toBeVisible();
}

export async function createAndSubmitAuditCase(page, testInfo, { title }) {
  await page.getByRole("link", { name: "创建案例" }).click();
  await expect(page.getByText("填写案例基本信息")).toBeVisible();
  await capture(page, testInfo, "create-step-1");

  await page.getByLabel(/案例标题/).fill(title);
  await page.getByLabel(/所属部门\/学院/).fill("马克思主义学院");
  await page.getByRole("button", { name: "继续" }).click();

  await expect(page.getByText("撰写案例内容")).toBeVisible();
  await page.locator("#ccf-content").fill(DEFAULT_AUDIT_CASE_CONTENT);
  await page.locator("#ccf-source").fill(DEFAULT_AUDIT_CASE_SOURCE);
  await capture(page, testInfo, "create-step-2");
  await page.getByRole("button", { name: "继续" }).click();

  await expect(page.getByText("选择分类")).toBeVisible();
  await page.getByRole("button", { name: "思政课教学案例" }).click();
  await page.getByRole("button", { name: "铸魂育人" }).click();
  await capture(page, testInfo, "create-step-3");
  await page.getByRole("button", { name: "继续" }).click();

  await expect(page.getByRole("heading", { name: "AI 智能内容审核" })).toBeVisible();
  await expect(page.getByRole("button", { name: "生成自查建议" })).toBeVisible();
  await page.getByRole("button", { name: "生成自查建议" }).click();
  await expect(page.getByText("自查进度")).toBeVisible();
  await expect(page.getByText("100%")).toBeVisible();
  await expect(page.getByText(/已生成 v2 只读审核版本/)).toBeVisible();
  await expect(page.getByText("版本正文")).toBeVisible();
  await expect(page.getByText("AI 批注", { exact: true })).toBeVisible();
  await expect(page.getByText("来源材料用于验证版本快照。")).toBeVisible();
  await expect(page.getByText("E2E AI 段落批注：请补充来源材料中的时间和参与对象。")).toBeVisible();
  await capture(page, testInfo, "create-step-4-ai-results");
  await page.getByRole("button", { name: "继续" }).click();

  await expect(page.getByText("确认并提交")).toBeVisible();
  await expect(page.getByText(/提交后案例将进入专家人工审核流程，期间仍可/)).toBeVisible();
  await capture(page, testInfo, "create-step-5-submit");
  await confirmAndSubmitCase(page);
  await expectPendingSubmission(page, title);

  await page.getByRole("link", { name: "我的提交" }).click();
  const teacherPendingCard = page.locator(".case-card").filter({ hasText: title });
  await expect(teacherPendingCard).toBeVisible();
  await teacherPendingCard.getByRole("button", { name: "查看详情" }).click();
  await expect(page.getByRole("heading", { name: title })).toBeVisible();
  await expect(page.getByText("历史版本")).toBeVisible();
  await expect(page.getByText("来源材料", { exact: true }).first()).toBeVisible();
  await expect(page.getByText(DEFAULT_AUDIT_CASE_SOURCE).first()).toBeVisible();
  await expect(page.getByRole("button", { name: "复制" }).first()).toBeVisible();
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
  await expect(page.getByRole("heading", { name: title })).toBeVisible();
  await expect(page.getByText("版本预览")).toBeVisible();
  await expect(page.getByText(DEFAULT_AUDIT_CASE_CONTENT)).toBeVisible();
  await expect(page.getByText(DEFAULT_AUDIT_CASE_SOURCE)).toBeVisible();
  await capture(page, testInfo, "admin-pending-review");
  await page.getByRole("button", { name: "审核此案例" }).click();
  await submitAdminReview(page, {
    status: "approve",
    comment: "审计测试：审核通过。",
    paragraphId: "p1",
    paragraphMessage: "审计测试：补充来源材料中的时间和参与对象。",
    paragraphSuggestion: "补充学院新闻链接和课堂反馈摘要。",
    captureBeforeSubmit: () => capture(page, testInfo, "admin-review-workspace"),
  });

  await logout(page);
  await page.getByRole("link", { name: "案例库" }).click();
  await page.getByPlaceholder("搜索案例标题、内容...").fill(title);
  await page.getByRole("button", { name: "搜索" }).click();

  const publicCard = page.locator(".case-card").filter({ hasText: title });
  await expect(publicCard).toBeVisible();
  await publicCard.getByRole("button", { name: "查看详情" }).click();
  await expect(page.getByRole("heading", { name: title })).toBeVisible();
  await expect(page.getByRole("heading", { name: "来源材料" })).toBeVisible();
  await expect(page.getByText(DEFAULT_AUDIT_CASE_SOURCE)).toBeVisible();
  await expect(page.getByText("作者 AI 自查意见")).toHaveCount(0);
  await capture(page, testInfo, "public-approved-search-result");
  await page.getByRole("button", { name: "返回案例库" }).click();
}
