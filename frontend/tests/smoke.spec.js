import { test, expect } from "@playwright/test";
import { execFileSync } from "child_process";
import { join, dirname } from "path";
import { fileURLToPath } from "url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = join(__dirname, "..", "..");

const TEST_USER = "smoke_user";
const TEST_USER_PASS = "SmokePass123!";
const TEST_ADMIN = "smoke_admin";
const TEST_ADMIN_PASS = "SmokePass123!";

const FORCE_PWD_USER = "force_pwd_user";
const FORCE_PWD_PASS = "ForcePwd123!";
const FORCE_PWD_NEW_PASS = "NewForcePwd456!";
const DOCKER_COMPOSE_FILE = process.env.SMOKE_E2E_COMPOSE_FILE || "";
const DOCKER_COMPOSE_ARGS = DOCKER_COMPOSE_FILE ? ["-f", DOCKER_COMPOSE_FILE] : [];

/**
 * Run a command inside the running `app` Compose service.
 */
function dockerExec(cmd) {
  return execFileSync(
    "docker",
    ["compose", ...DOCKER_COMPOSE_ARGS, "exec", "-T", "app", "sh", "-lc", cmd],
    {
    encoding: "utf-8",
    cwd: REPO_ROOT,
    timeout: 30000,
    }
  );
}

async function cardLikeCount(caseCard) {
  const text = await caseCard
    .locator(".case-stats-row span")
    .filter({ hasText: /^点赞\s+\d+$/ })
    .innerText();
  const match = text.match(/点赞\s+(\d+)/);
  return match ? Number(match[1]) : 0;
}

test.beforeAll(async () => {
  // Clean up any stale test accounts from a previous interrupted run
  try {
    dockerExec(`python backend/account_admin.py delete --username ${TEST_USER}`);
  } catch {}
  try {
    dockerExec(`python backend/account_admin.py delete --username ${TEST_ADMIN}`);
  } catch {}
  try {
    dockerExec(`python backend/account_admin.py delete --username ${FORCE_PWD_USER}`);
  } catch {}

  // Create deterministic test accounts with must_change_password=false
  dockerExec(
    `python backend/account_admin.py create --username ${TEST_USER} --password ${TEST_USER_PASS} --role normal --nickname SmokeUser --must-change-password false --status active`
  );
  dockerExec(
    `python backend/account_admin.py create --username ${TEST_ADMIN} --password ${TEST_ADMIN_PASS} --role admin --nickname SmokeAdmin --must-change-password false --status active`
  );

  // Create deterministic test account that requires forced password change
  dockerExec(
    `python backend/account_admin.py create --username ${FORCE_PWD_USER} --password ${FORCE_PWD_PASS} --role normal --nickname ForcePwdUser --must-change-password true --status active`
  );
});

test.afterAll(async () => {
  try {
    dockerExec(`python backend/account_admin.py delete --username ${TEST_USER}`);
  } catch {}
  try {
    dockerExec(`python backend/account_admin.py delete --username ${TEST_ADMIN}`);
  } catch {}
  try {
    dockerExec(`python backend/account_admin.py delete --username ${FORCE_PWD_USER}`);
  } catch {}
});

test(
  "login -> create/submit case -> admin review -> approved case visible publicly",
  async ({ page }, testInfo) => {
    const uniqueTitle = `Smoke测试 ${Date.now()}`;

    // Auto-accept any browser dialogs (alerts from window.alert)
    page.on("dialog", (dialog) => dialog.accept());

    // ==========================================
    // Step 1: Login as normal user
    // ==========================================
    await page.goto("/");
    await expect(page.getByRole("button", { name: "登录" })).toBeVisible();
    await page.getByRole("button", { name: "登录" }).click();

    await page.getByLabel("用户名").fill(TEST_USER);
    await page.getByLabel("密码").fill(TEST_USER_PASS);
    await page.locator(".modal-panel").getByRole("button", { name: "登录" }).click();

    await expect(page.locator(".user-name")).toContainText("SmokeUser");

    // ==========================================
    // Step 2: Navigate to create case wizard
    // ==========================================
    await page.getByRole("link", { name: "创建案例" }).click();
    await expect(page.getByText("填写基本信息")).toBeVisible();

    // -- Step 1: Basic info --
    await page.getByLabel(/案例标题/).fill(uniqueTitle);
    await page.getByLabel(/所属部门\/学院/).fill("测试学院");
    await page.getByRole("button", { name: "继续" }).click();

    // -- Step 2: Content --
    await expect(page.getByText("编写案例内容")).toBeVisible();
    await page.locator("#ccf-content").fill(
      "这是一篇用于冒烟测试的案例正文。案例内容包含背景、问题、分析与反思等部分，以确保测试流程能够完整运行。"
    );
    await page.getByRole("button", { name: "继续" }).click();

    // -- Step 3: Classification --
    await expect(page.getByText("选择案例分类")).toBeVisible();
    await page.locator("#ccf-type").selectOption("TYPE_A");
    await page.locator("#ccf-theme").selectOption("铸魂育人");
    await page.getByRole("button", { name: "继续" }).click();

    // -- Step 4: Pre-submit self-check --
    await expect(
      page.getByRole("heading", { name: "提交前自查" })
    ).toBeVisible();
    await expect(page.getByText("运行全部自查")).toBeVisible();
    await page.getByRole("button", { name: "运行此项" }).first().click();
    await expect(page.getByText("AI 审核功能未启用")).toBeVisible();
    await page.getByRole("button", { name: "继续" }).click();

    // -- Step 5: Submit --
    await expect(page.getByText("确认并提交")).toBeVisible();
    await expect(
      page.getByText("提交后案例将进入专家人工审核流程")
    ).toBeVisible();
    await page.getByRole("button", { name: "正式提交案例" }).click();

    // Wait for submit alert to be accepted and wizard to reset
    await expect(page.getByText("填写基本信息")).toBeVisible();

    // ==========================================
    // Step 3: Logout and login as admin
    // ==========================================
    await page.getByRole("button", { name: "退出" }).click();
    await expect(page.getByRole("button", { name: "登录" })).toBeVisible();

    await page.getByRole("button", { name: "登录" }).click();
    await page.getByLabel("用户名").fill(TEST_ADMIN);
    await page.getByLabel("密码").fill(TEST_ADMIN_PASS);
    await page.locator(".modal-panel").getByRole("button", { name: "登录" }).click();

    await expect(page.locator(".user-name")).toContainText("SmokeAdmin");

    // ==========================================
    // Step 4: Admin review and approve
    // ==========================================
    await page.getByRole("link", { name: "审核管理" }).click();
    await expect(page.getByRole("tab", { name: "待审核" })).toHaveAttribute(
      "aria-selected",
      "true"
    );

    // Find the case card with our unique title
    const caseCard = page.locator(".case-card").filter({ hasText: uniqueTitle });
    await expect(caseCard).toBeVisible();

    await caseCard.getByRole("button", { name: "审核" }).click();

    // Fill review modal
    await page.locator("#review-comment").fill("审核通过，测试用例。");
    await page.getByLabel("通过").check();
    await page.getByRole("button", { name: "提交审核" }).click();

    // Wait for modal to close after review submission
    await expect(page.locator(".modal-overlay")).toHaveCount(0);

    // ==========================================
    // Step 5: Verify public library visibility
    // ==========================================
    await page.getByRole("link", { name: "案例库" }).click();
    await expect(
      page.getByPlaceholder("搜索案例标题、内容...")
    ).toBeVisible();

    await page.getByPlaceholder("搜索案例标题、内容...").fill(uniqueTitle);
    await page.getByRole("button", { name: "搜索" }).click();

    // The approved case should appear in the public library
    const publicCaseCard = page
      .locator(".case-card")
      .filter({ hasText: uniqueTitle });
    await expect(publicCaseCard).toBeVisible();

    // Public visitors can like and unlike a case, with the visible count updating.
    const initialLikeCount = await cardLikeCount(publicCaseCard);
    expect(initialLikeCount).toBeGreaterThanOrEqual(0);

    await expect(
      publicCaseCard.getByRole("button", { name: "点赞", exact: true })
    ).toBeVisible();
    await publicCaseCard
      .getByRole("button", { name: "点赞", exact: true })
      .click();
    await expect(
      publicCaseCard.getByRole("button", { name: "已点赞", exact: true })
    ).toBeVisible();
    await expect(publicCaseCard.locator(".case-stats-row")).toContainText(
      `点赞 ${initialLikeCount + 1}`
    );

    await publicCaseCard
      .getByRole("button", { name: "已点赞", exact: true })
      .click();
    await expect(
      publicCaseCard.getByRole("button", { name: "点赞", exact: true })
    ).toBeVisible();
    await expect(publicCaseCard.locator(".case-stats-row")).toContainText(
      `点赞 ${initialLikeCount}`
    );

    // ==========================================
    // Step 6: Global header search finds the approved case
    // ==========================================
    // Skip on mobile where .global-search is hidden by responsive CSS.
    if (testInfo.project.name === "chromium-desktop") {
      // Exercise the global header search form in App.vue (distinct from the
      // local case-library search field) to locate the approved case.
      await page
        .locator(".global-search")
        .getByLabel("搜索案例")
        .fill(uniqueTitle);
      await page
        .locator(".global-search")
        .getByRole("button", { name: "查找案例" })
        .click();

      // Should land on/remain on the case library view with the case visible
      await expect(page).toHaveURL(/#library/);
      await expect(
        page.locator(".case-card").filter({ hasText: uniqueTitle })
      ).toBeVisible();
    }

    // Capture a success screenshot for UI review, distinguished by project name
    const screenshotPath = testInfo.outputPath(
      `smoke-success-${testInfo.project.name}.png`
    );
    await page.screenshot({ path: screenshotPath, fullPage: true });
  }
);

test(
  "mobile create-case layout regression",
  async ({ page }, testInfo) => {
    test.skip(
      testInfo.project.name !== "chromium-mobile",
      "mobile-only regression"
    );

    page.on("dialog", (dialog) => dialog.accept());

    await page.goto("/");
    await expect(page.getByRole("button", { name: "登录" })).toBeVisible();
    await page.getByRole("button", { name: "登录" }).click();

    await page.getByLabel("用户名").fill(TEST_USER);
    await page.getByLabel("密码").fill(TEST_USER_PASS);
    await page
      .locator(".modal-panel")
      .getByRole("button", { name: "登录" })
      .click();

    // On mobile .user-name is hidden; use avatar as login indicator
    await expect(page.locator(".user-avatar")).toBeVisible();

    // Navigate to create case wizard
    await page.getByRole("link", { name: "创建案例" }).click();
    await expect(page.getByText("填写基本信息")).toBeVisible();

    // Verify header nav label "案例库" is not truncated
    const libraryLink = page
      .locator(".main-nav .nav-link")
      .filter({ hasText: "案例库" });
    await expect(libraryLink).toBeVisible();
    const isNotTruncated = await libraryLink.evaluate(
      (el) => el.clientWidth >= el.scrollWidth
    );
    expect(isNotTruncated).toBe(true);

    // Fill step 1 and advance to step 2
    await page.getByLabel(/案例标题/).fill("Mobile Regression Test");
    await page.getByLabel(/所属部门\/学院/).fill("测试学院");
    await page.getByRole("button", { name: "继续" }).click();
    await expect(page.getByText("编写案例内容")).toBeVisible();

    // Deliberately scroll down
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
    const scrollYBefore = await page.evaluate(() => window.scrollY);
    expect(scrollYBefore).toBeGreaterThan(0);

    // Fill content and advance to step 3
    await page
      .locator("#ccf-content")
      .fill("这是用于移动端回归测试的案例正文内容。");
    await page.getByRole("button", { name: "继续" }).click();
    await expect(page.getByText("选择案例分类")).toBeVisible();

    // Verify scroll resets to top after step transition
    await page.waitForFunction(() => window.scrollY === 0);
    const scrollYAfter = await page.evaluate(() => window.scrollY);
    expect(scrollYAfter).toBe(0);
  }
);

test(
  "classification helper provides local suggestion",
  async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("button", { name: "登录" })).toBeVisible();
    await page.getByRole("button", { name: "登录" }).click();

    await page.getByLabel("用户名").fill(TEST_USER);
    await page.getByLabel("密码").fill(TEST_USER_PASS);
    await page.locator(".modal-panel").getByRole("button", { name: "登录" }).click();

    await page.getByRole("link", { name: "创建案例" }).click();
    await expect(page.getByText("填写基本信息")).toBeVisible();

    await page.getByLabel(/案例标题/).fill("社会实践数字育人案例");
    await page.getByLabel(/所属部门\/学院/).fill("测试学院");
    await page.getByRole("button", { name: "继续" }).click();

    await expect(page.getByText("编写案例内容")).toBeVisible();
    await page
      .locator("#ccf-content")
      .fill("本案例围绕社会实践活动中的数字技术应用，记录实践育人过程。");
    await page.getByRole("button", { name: "继续" }).click();

    await expect(page.getByText("选择案例分类")).toBeVisible();
    await page.getByRole("button", { name: "打开 AI 分类助手" }).click();
    await expect(
      page.getByText("AI 分类助手（本地建议）")
    ).toBeVisible();

    await page.getByPlaceholder("输入问题…").fill("帮我推荐案例类型和主题");
    await page.getByRole("button", { name: "获取建议" }).click();

    const helperResponse = page.getByRole("status");
    await expect(helperResponse).toContainText("建议类型");
    await expect(helperResponse).toContainText("实践育人案例");
    await expect(helperResponse).toContainText("实践育人");
  }
);

test(
  "save draft appears in my submissions",
  async ({ page }) => {
    const uniqueTitle = `Draft测试 ${Date.now()}`;

    await page.goto("/");
    await expect(page.getByRole("button", { name: "登录" })).toBeVisible();
    await page.getByRole("button", { name: "登录" }).click();

    await page.getByLabel("用户名").fill(TEST_USER);
    await page.getByLabel("密码").fill(TEST_USER_PASS);
    await page.locator(".modal-panel").getByRole("button", { name: "登录" }).click();

    await page.getByRole("link", { name: "创建案例" }).click();
    await expect(page.getByText("填写基本信息")).toBeVisible();

    await page.getByLabel(/案例标题/).fill(uniqueTitle);
    await page.getByLabel(/所属部门\/学院/).fill("测试学院");
    await page.getByRole("button", { name: "继续" }).click();

    await expect(page.getByText("编写案例内容")).toBeVisible();
    await page
      .locator("#ccf-content")
      .fill("这是用于草稿保存回归测试的案例正文内容。");
    await page.getByRole("button", { name: "继续" }).click();

    await expect(page.getByText("选择案例分类")).toBeVisible();
    await page.locator("#ccf-type").selectOption("TYPE_A");
    await page.locator("#ccf-theme").selectOption("铸魂育人");

    const saveDialogPromise = page.waitForEvent("dialog");
    await page.getByRole("button", { name: "保存草稿" }).click();
    const saveDialog = await saveDialogPromise;
    expect(saveDialog.message()).toContain("草稿已保存");
    await saveDialog.accept();

    await page.getByRole("link", { name: "我的提交" }).click();
    await page.getByRole("tab", { name: "草稿" }).click();

    const draftCard = page
      .locator(".case-card")
      .filter({ hasText: uniqueTitle });
    await expect(draftCard).toBeVisible();
    await expect(draftCard.locator(".status-pill")).toContainText("草稿");

    await draftCard.getByRole("button", { name: "删除" }).click();
    const deleteDialogPromise = page.waitForEvent("dialog");
    await page
      .locator(".confirm-panel")
      .getByRole("button", { name: "删除" })
      .click();
    const deleteDialog = await deleteDialogPromise;
    expect(deleteDialog.message()).toContain("案例删除成功");
    await deleteDialog.accept();
    await expect(draftCard).toHaveCount(0);
  }
);

test(
  "rejected review feedback appears in my submissions",
  async ({ page }) => {
    const uniqueTitle = `Reject测试 ${Date.now()}`;
    const rejectComment = `请补充课堂反馈 ${Date.now()}`;

    page.on("dialog", (dialog) => dialog.accept());

    await page.goto("/");
    await expect(page.getByRole("button", { name: "登录" })).toBeVisible();
    await page.getByRole("button", { name: "登录" }).click();

    await page.getByLabel("用户名").fill(TEST_USER);
    await page.getByLabel("密码").fill(TEST_USER_PASS);
    await page.locator(".modal-panel").getByRole("button", { name: "登录" }).click();

    await page.getByRole("link", { name: "创建案例" }).click();
    await expect(page.getByText("填写基本信息")).toBeVisible();

    await page.getByLabel(/案例标题/).fill(uniqueTitle);
    await page.getByLabel(/所属部门\/学院/).fill("测试学院");
    await page.getByRole("button", { name: "继续" }).click();

    await expect(page.getByText("编写案例内容")).toBeVisible();
    await page
      .locator("#ccf-content")
      .fill("这是用于驳回审核反馈回归测试的案例正文内容。");
    await page.getByRole("button", { name: "继续" }).click();

    await expect(page.getByText("选择案例分类")).toBeVisible();
    await page.locator("#ccf-type").selectOption("TYPE_A");
    await page.locator("#ccf-theme").selectOption("铸魂育人");
    await page.getByRole("button", { name: "继续" }).click();

    await expect(
      page.getByRole("heading", { name: "提交前自查" })
    ).toBeVisible();
    await page.getByRole("button", { name: "继续" }).click();

    await expect(page.getByText("确认并提交")).toBeVisible();
    await page.getByRole("button", { name: "正式提交案例" }).click();
    await expect(page.getByText("填写基本信息")).toBeVisible();

    await page.getByRole("button", { name: "退出" }).click();
    await page.getByRole("button", { name: "登录" }).click();
    await page.getByLabel("用户名").fill(TEST_ADMIN);
    await page.getByLabel("密码").fill(TEST_ADMIN_PASS);
    await page.locator(".modal-panel").getByRole("button", { name: "登录" }).click();

    await page.getByRole("link", { name: "审核管理" }).click();
    const reviewCard = page
      .locator(".case-card")
      .filter({ hasText: uniqueTitle });
    await expect(reviewCard).toBeVisible();
    await reviewCard.getByRole("button", { name: "审核" }).click();
    await page.locator("#review-comment").fill(rejectComment);
    await page.getByLabel("需修改").check();
    await page.getByRole("button", { name: "提交审核" }).click();
    await expect(page.locator(".modal-overlay")).toHaveCount(0);

    await page.getByRole("button", { name: "退出" }).click();
    await page.getByRole("button", { name: "登录" }).click();
    await page.getByLabel("用户名").fill(TEST_USER);
    await page.getByLabel("密码").fill(TEST_USER_PASS);
    await page.locator(".modal-panel").getByRole("button", { name: "登录" }).click();

    await page.getByRole("link", { name: "我的提交" }).click();
    await page.getByRole("tab", { name: "需修改" }).click();

    const revisionCard = page
      .locator(".case-card")
      .filter({ hasText: uniqueTitle });
    await expect(revisionCard).toBeVisible();
    await expect(revisionCard.locator(".status-pill")).toContainText("需修改");

    await revisionCard.getByRole("button", { name: "查看详情" }).click();
    await expect(revisionCard.locator(".detail-review")).toContainText(rejectComment);

    await revisionCard.getByRole("button", { name: "删除" }).click();
    await page
      .locator(".confirm-panel")
      .getByRole("button", { name: "删除" })
      .click();
    await expect(revisionCard).toHaveCount(0);
  }
);

test(
  "admin hide and show approved case visibility",
  async ({ page }) => {
    const uniqueTitle = `Visibility测试 ${Date.now()}`;

    page.on("dialog", (dialog) => dialog.accept());

    await page.goto("/");
    await expect(page.getByRole("button", { name: "登录" })).toBeVisible();
    await page.getByRole("button", { name: "登录" }).click();

    await page.getByLabel("用户名").fill(TEST_USER);
    await page.getByLabel("密码").fill(TEST_USER_PASS);
    await page.locator(".modal-panel").getByRole("button", { name: "登录" }).click();

    await page.getByRole("link", { name: "创建案例" }).click();
    await expect(page.getByText("填写基本信息")).toBeVisible();

    await page.getByLabel(/案例标题/).fill(uniqueTitle);
    await page.getByLabel(/所属部门\/学院/).fill("测试学院");
    await page.getByRole("button", { name: "继续" }).click();

    await expect(page.getByText("编写案例内容")).toBeVisible();
    await page
      .locator("#ccf-content")
      .fill("这是用于管理员隐藏展示回归测试的案例正文内容。");
    await page.getByRole("button", { name: "继续" }).click();

    await expect(page.getByText("选择案例分类")).toBeVisible();
    await page.locator("#ccf-type").selectOption("TYPE_A");
    await page.locator("#ccf-theme").selectOption("铸魂育人");
    await page.getByRole("button", { name: "继续" }).click();

    await expect(
      page.getByRole("heading", { name: "提交前自查" })
    ).toBeVisible();
    await page.getByRole("button", { name: "继续" }).click();

    await expect(page.getByText("确认并提交")).toBeVisible();
    await page.getByRole("button", { name: "正式提交案例" }).click();
    await expect(page.getByText("填写基本信息")).toBeVisible();

    await page.getByRole("button", { name: "退出" }).click();
    await page.getByRole("button", { name: "登录" }).click();
    await page.getByLabel("用户名").fill(TEST_ADMIN);
    await page.getByLabel("密码").fill(TEST_ADMIN_PASS);
    await page.locator(".modal-panel").getByRole("button", { name: "登录" }).click();

    await page.getByRole("link", { name: "审核管理" }).click();
    const pendingCard = page
      .locator(".case-card")
      .filter({ hasText: uniqueTitle });
    await expect(pendingCard).toBeVisible();
    await pendingCard.getByRole("button", { name: "审核" }).click();
    await page.locator("#review-comment").fill("审核通过，用于可见性测试。");
    await page.getByLabel("通过").check();
    await page.getByRole("button", { name: "提交审核" }).click();
    await expect(page.locator(".modal-overlay")).toHaveCount(0);

    await page.getByRole("tab", { name: "已通过" }).click();
    const approvedCard = page
      .locator(".case-card")
      .filter({ hasText: uniqueTitle });
    await expect(approvedCard).toBeVisible();
    await approvedCard.getByRole("button", { name: "隐藏" }).click();
    await expect(approvedCard.locator(".pill-hidden")).toContainText("已隐藏");
    await expect(
      approvedCard.getByRole("button", { name: "展示" })
    ).toBeVisible();

    await page.getByRole("link", { name: "案例库" }).click();
    await page.getByPlaceholder("搜索案例标题、内容...").fill(uniqueTitle);
    await page.getByRole("button", { name: "搜索" }).click();
    await expect(
      page.locator(".case-card").filter({ hasText: uniqueTitle })
    ).toHaveCount(0);

    await page.getByRole("link", { name: "审核管理" }).click();
    await page.getByRole("tab", { name: "已通过" }).click();
    await expect(approvedCard).toBeVisible();
    await approvedCard.getByRole("button", { name: "展示" }).click();
    await expect(approvedCard.locator(".pill-visible")).toContainText("未隐藏");

    await page.getByRole("link", { name: "案例库" }).click();
    await page.getByPlaceholder("搜索案例标题、内容...").fill(uniqueTitle);
    await page.getByRole("button", { name: "搜索" }).click();
    await expect(
      page.locator(".case-card").filter({ hasText: uniqueTitle })
    ).toBeVisible();

    await page.getByRole("link", { name: "审核管理" }).click();
    await page.getByRole("tab", { name: "已通过" }).click();
    await expect(approvedCard).toBeVisible();
    await approvedCard.getByRole("button", { name: "删除" }).click();
    await page
      .locator(".confirm-panel")
      .getByRole("button", { name: "删除" })
      .click();
    await expect(approvedCard).toHaveCount(0);
  }
);

test(
  "forced password change workflow",
  async ({ page }, testInfo) => {
    test.skip(
      testInfo.project.name !== "chromium-desktop",
      "desktop-only: asserts .user-name which is hidden on mobile"
    );

    page.on("dialog", (dialog) => dialog.accept());

    // ==========================================
    // Step 1: Login as user with must_change_password=true
    // ==========================================
    await page.goto("/");
    await expect(page.getByRole("button", { name: "登录" })).toBeVisible();
    await page.getByRole("button", { name: "登录" }).click();

    await page.getByLabel("用户名").fill(FORCE_PWD_USER);
    await page.getByLabel("密码").fill(FORCE_PWD_PASS);
    await page.locator(".modal-panel").getByRole("button", { name: "登录" }).click();

    // ==========================================
    // Step 2: Verify forced password change modal appears
    // ==========================================
    await expect(
      page.getByRole("heading", { name: "修改初始密码" })
    ).toBeVisible();
    await expect(
      page.getByText("您的账户当前使用的是初始密码")
    ).toBeVisible();

    // ==========================================
    // Step 3: Fill and submit password change form
    // ==========================================
    await page.locator("#pc-old").fill(FORCE_PWD_PASS);
    await page.locator("#pc-new").fill(FORCE_PWD_NEW_PASS);
    await page.locator("#pc-confirm").fill(FORCE_PWD_NEW_PASS);
    await page.getByRole("button", { name: "确认修改" }).click();

    // Modal should close and user remains logged in
    await expect(page.locator(".modal-overlay")).toHaveCount(0);
    await expect(page.locator(".user-name")).toContainText("ForcePwdUser");

    // ==========================================
    // Step 4: Logout and verify password change took effect
    // ==========================================
    await page.getByRole("button", { name: "退出" }).click();
    await expect(page.getByRole("button", { name: "登录" })).toBeVisible();

    // Old password should no longer work
    await page.getByRole("button", { name: "登录" }).click();
    await page.getByLabel("用户名").fill(FORCE_PWD_USER);
    await page.getByLabel("密码").fill(FORCE_PWD_PASS);
    await page.locator(".modal-panel").getByRole("button", { name: "登录" }).click();
    await expect(page.locator(".modal-panel .error-msg")).toBeVisible();

    // Close modal and retry with new password
    await page.locator(".modal-panel .close-btn").click();
    await page.getByRole("button", { name: "登录" }).click();
    await page.getByLabel("用户名").fill(FORCE_PWD_USER);
    await page.getByLabel("密码").fill(FORCE_PWD_NEW_PASS);
    await page.locator(".modal-panel").getByRole("button", { name: "登录" }).click();

    // Should log in successfully without forced password modal
    await expect(page.locator(".user-name")).toContainText("ForcePwdUser");
    await expect(
      page.getByRole("heading", { name: "修改初始密码" })
    ).not.toBeVisible();
  }
);
