import { test, expect } from "@playwright/test";
import { login, logout } from "./support/auth.js";
import {
  approveAuditCaseAndVerifyPublicSearch,
  confirmAndSubmitCase,
  createAndSubmitAuditCase,
  expectPendingSubmission,
  submitAdminReview,
} from "./support/auditFlow.js";
import { cleanupAuditCases } from "./support/caseCleanup.js";
import { capture } from "./support/capture.js";

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

test.describe("manual audit candidate flows", () => {
  test("mobile create flow keeps critical screens readable", async ({ page }, testInfo) => {
    test.skip(
      testInfo.project.name !== "chromium-mobile",
      "mobile-only visual regression for create flow"
    );

    await page.goto("/");
    await login(page, USER);
    await page.getByRole("link", { name: "创建案例" }).click();

    await expect(page.getByText("填写案例基本信息")).toBeVisible();
    await expect(page.locator(".wizard-main")).toBeInViewport();
    await expect(page.locator("#ccf-title")).toBeVisible();
    await capture(page, testInfo, "mobile-create-step-1");

    await page.getByLabel(/案例标题/).fill(`移动端视觉审计 ${Date.now()}`);
    await page.getByLabel(/所属部门\/学院/).fill("马克思主义学院");
    await page.getByRole("button", { name: "继续" }).scrollIntoViewIfNeeded();
    await page.getByRole("button", { name: "继续" }).click();

    await expect(page.getByText("撰写案例内容")).toBeVisible();
    await expect(page.locator("#ccf-content")).toBeVisible();
    await expect(page.locator("#ccf-source")).toBeVisible();
    await capture(page, testInfo, "mobile-create-step-2");

    await page.locator("#ccf-content").fill(
      "移动端创建流程视觉审计正文，覆盖输入框宽度、按钮换行和页面滚动。"
    );
    await page.locator("#ccf-source").fill("移动端来源材料审计文本。");
    await page.getByRole("button", { name: "继续" }).scrollIntoViewIfNeeded();
    await page.getByRole("button", { name: "继续" }).click();

    await expect(page.getByText("选择分类")).toBeVisible();
    await expect(page.getByRole("button", { name: "思政课教学案例" })).toBeVisible();
    await expect(page.getByRole("button", { name: "铸魂育人" })).toBeVisible();
    await capture(page, testInfo, "mobile-create-step-3");
  });

  test("default admin seed account reaches home without password change", async ({ page }, testInfo) => {
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

    await expect(page.getByRole("heading", { name: "欢迎来到强国有我思政案例库" })).toBeVisible();
    await expect(page.locator(".user-name")).toContainText("小李");
    await expect(page.getByRole("heading", { name: "修改初始密码" })).toHaveCount(0);
    await capture(page, testInfo, "default-admin-home");
  });

  test("create flow author identity follows current login, not stale draft", async ({
    page,
  }, testInfo) => {
    test.skip(
      testInfo.project.name !== "chromium-desktop",
      "desktop-only author identity regression"
    );

    await page.goto("/");
    await page.evaluate(() => {
      localStorage.setItem(
        "case_library_create_case_draft",
        JSON.stringify({
          username: "old_author",
          form: {
            title: "旧草稿标题",
            author: "过期作者",
            department: "马克思主义学院",
            content: "旧草稿正文",
            source_material: "旧来源材料",
            type: "TYPE_A",
            theme: "铸魂育人",
          },
          caseId: 999999,
          latestReviewVersionId: 888888,
          savedAt: Date.now(),
        })
      );
    });
    let staleUpdateRequests = 0;
    await page.route("**/api/cases/999999", async (route) => {
      staleUpdateRequests += 1;
      await route.fulfill({
        status: 500,
        contentType: "application/json",
        body: JSON.stringify({
          success: false,
          detail: "stale caseId should not be used",
        }),
      });
    });

    await login(page, USER);
    await page.getByRole("link", { name: "创建案例" }).click();

    await expect(page.getByLabel("作者姓名")).toHaveValue(USER.nickname);
    await expect(page.getByLabel("作者姓名")).not.toHaveValue("过期作者");
    await expect(page.getByLabel(/案例标题/)).toHaveValue("旧草稿标题");

    // #92：进入创建案例入口后，旧 draft 的 caseId 不应被复用。
    const draftAfterEntry = await page.evaluate(() =>
      JSON.parse(localStorage.getItem("case_library_create_case_draft"))
    );
    expect(draftAfterEntry.caseId).not.toBe(999999);
    expect(draftAfterEntry.latestReviewVersionId).not.toBe(888888);

    await page.getByRole("button", { name: "保存草稿" }).click();
    await expect(page.getByText("草稿已保存")).toBeVisible();
    expect(staleUpdateRequests).toBe(0);
    const draft = await page.evaluate(() =>
      JSON.parse(localStorage.getItem("case_library_create_case_draft"))
    );
    expect(draft.username).toBe(USER.username);
    expect(draft.caseId).not.toBe(999999);
    expect(draft.latestReviewVersionId).not.toBe(888888);
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

    await test.step("capture public home before authentication", async () => {
      await capture(page, testInfo, "home-public");
    });

    await test.step("admin cleanup existing audit cases", async () => {
      await login(page, ADMIN);
      await cleanupAuditCases(page);
      await logout(page);
    });

    await test.step("author creates, AI-reviews, submits, and checks version history", async () => {
      await login(page, USER);
      await capture(page, testInfo, "home-authenticated-user");
      await createAndSubmitAuditCase(page, testInfo, { title });
    });

    await test.step("admin approves submitted case and public search hides review internals", async () => {
      await approveAuditCaseAndVerifyPublicSearch(page, testInfo, {
        admin: ADMIN,
        title,
      });
    });

    await test.step("admin cleanup created audit case", async () => {
      await login(page, ADMIN);
      await cleanupAuditCases(page, title);
    });
  });

  test("admin returns a submitted version and author resubmits after copying comments", async ({
    page,
  }, testInfo) => {
    test.skip(
      testInfo.project.name !== "chromium-desktop",
      "desktop-only revision-required acceptance path"
    );

    const title = `Audit案例 退回再提交 ${Date.now()}`;
    const initialContent = [
      "退回再提交审计案例第一段，说明教学背景和课堂目标。",
      "退回再提交审计案例第二段，暂缺来源材料中的时间和对象。",
    ].join("\n");
    const revisedContent = [
      initialContent,
      "已根据人工批注补充学院新闻时间、参与对象和课堂反馈摘要。",
    ].join("\n");
    const sourceMaterial = "退回再提交来源材料：学院新闻、课堂反馈、访谈记录。";
    const adminParagraphComment = "人工段落批注：请补充来源材料中的时间和参与对象。";
    const adminSuggestion = "补充学院新闻日期、参与学生和课堂反馈摘要。";

    await page.context().grantPermissions(["clipboard-read", "clipboard-write"]);
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
                { paragraph_id: "p1", text: "退回再提交审计案例第一段，说明教学背景和课堂目标。" },
                { paragraph_id: "p2", text: "退回再提交审计案例第二段，暂缺来源材料中的时间和对象。" },
              ],
              source_material: sourceMaterial,
            },
            comments: [
              {
                id: "c-revision",
                paragraph_id: "p2",
                category: "source",
                severity: "important",
                message: "AI 段落批注：来源材料要补齐时间和对象。",
                suggestion: "提交前补充来源材料摘录。",
              },
            ],
            summary: {
              suggested_next_steps: ["补充来源材料摘录。"],
            },
          },
        }),
      });
    });

    await page.goto("/");
    await login(page, ADMIN);
    await cleanupAuditCases(page);
    await logout(page);

    await login(page, USER);
    await page.getByRole("link", { name: "创建案例" }).click();
    await expect(page.getByText("填写案例基本信息")).toBeVisible();
    await page.getByLabel(/案例标题/).fill(title);
    await page.getByLabel(/所属部门\/学院/).fill("马克思主义学院");
    await page.getByRole("button", { name: "继续" }).click();

    await expect(page.getByText("撰写案例内容")).toBeVisible();
    await page.locator("#ccf-content").fill(initialContent);
    await page.locator("#ccf-source").fill(sourceMaterial);
    await page.getByRole("button", { name: "继续" }).click();

    await expect(page.getByText("选择分类")).toBeVisible();
    await page.getByRole("button", { name: "思政课教学案例" }).click();
    await page.getByRole("button", { name: "铸魂育人" }).click();
    await page.getByRole("button", { name: "继续" }).click();

    await expect(page.getByRole("heading", { name: "AI 智能内容审核" })).toBeVisible();
    await page.getByRole("button", { name: "生成自查建议" }).click();
    await expect(page.getByText("100%")).toBeVisible();
    await expect(page.getByText(/已生成 v2 只读审核版本/)).toBeVisible();
    await expect(page.getByText("AI 段落批注：来源材料要补齐时间和对象。")).toBeVisible();
    await page.getByRole("button", { name: "继续" }).click();
    await expect(page.getByText("确认并提交")).toBeVisible();
    await confirmAndSubmitCase(page);
    await expectPendingSubmission(page, title);

    await logout(page);
    await login(page, ADMIN);
    await page.getByRole("link", { name: "审核管理" }).click();
    const pendingCard = page.locator(".case-card").filter({ hasText: title });
    await expect(pendingCard).toBeVisible();
    await pendingCard.getByRole("button", { name: "审核" }).click();
    await submitAdminReview(page, {
      status: "reject",
      comment: "退回修改：来源材料不足。",
      paragraphId: "p2",
      paragraphMessage: adminParagraphComment,
      paragraphSuggestion: adminSuggestion,
    });

    await logout(page);
    await login(page, USER);
    await page.getByRole("link", { name: "我的提交" }).click();
    await page.getByRole("tab", { name: "需修改" }).click();
    const revisionCard = page.locator(".case-card").filter({ hasText: title });
    await expect(revisionCard).toBeVisible();
    await revisionCard.getByRole("button", { name: "查看详情" }).click();
    await page.getByRole("button", { name: "显示审核结果" }).click();
    await expect(page.getByText("人工段落批注", { exact: true })).toBeVisible();
    await expect(page.getByText(adminParagraphComment)).toBeVisible();
    await expect(page.getByText(adminSuggestion)).toBeVisible();
    await page.getByRole("button", { name: "复制" }).first().click();
    await expect(page.getByText(/v\d+ 已复制/)).toBeVisible();

    await page.getByRole("button", { name: "修改案例" }).click();
    await expect(page).toHaveURL(/#create\?draft=/);
    await expect(page.getByRole("heading", { name: "撰写案例内容" })).toBeVisible();
    await page.locator("#ccf-content").fill(revisedContent);
    await page.locator("#ccf-source").fill(`${sourceMaterial}\n补充：2026 年课堂反馈摘要。`);
    await page.getByRole("button", { name: "继续" }).click();
    await expect(page.getByText("选择分类")).toBeVisible();
    await page.getByRole("button", { name: "继续" }).click();
    await expect(page.getByRole("heading", { name: "AI 智能内容审核" })).toBeVisible();
    await page.getByRole("button", { name: "继续" }).click();
    await expect(page.getByText("确认并提交")).toBeVisible();
    await confirmAndSubmitCase(page);
    await expectPendingSubmission(page, title);

    await logout(page);
    await login(page, ADMIN);
    await page.getByRole("link", { name: "审核管理" }).click();
    const revisedPendingCard = page.locator(".case-card").filter({ hasText: title });
    await expect(revisedPendingCard).toBeVisible();
    await revisedPendingCard.getByRole("button", { name: "查看详情" }).click();
    await expect(page.getByRole("heading", { name: title })).toBeVisible();
    await expect(page.getByText("已根据人工批注补充学院新闻时间")).toBeVisible();
    await page.getByRole("button", { name: "返回审核列表" }).click();
    await revisedPendingCard.getByRole("button", { name: "审核" }).click();
    await submitAdminReview(page, {
      status: "approve",
      comment: "审核通过：退回意见已修改。",
    });
    await logout(page);

    await page.getByRole("link", { name: "案例库" }).click();
    await page.getByPlaceholder("搜索案例标题、内容...").fill(title);
    await page.getByRole("button", { name: "搜索" }).click();
    const publicCard = page.locator(".case-card").filter({ hasText: title });
    await expect(publicCard).toBeVisible();
    await publicCard.getByRole("button", { name: "查看详情" }).click();
    await expect(page.getByRole("heading", { name: title })).toBeVisible();
    await expect(page.getByText("已根据人工批注补充学院新闻时间")).toBeVisible();
    await expect(page.getByText(sourceMaterial)).toBeVisible();
    await expect(page.getByText("补充：2026 年课堂反馈摘要。")).toBeVisible();
    await expect(page.getByText(adminParagraphComment)).toHaveCount(0);
    await expect(page.getByText("AI 段落批注：来源材料要补齐时间和对象。")).toHaveCount(0);

    await login(page, ADMIN);
    await cleanupAuditCases(page, title);
  });

  test("public library does not render leaked review internals", async ({ page }, testInfo) => {
    test.skip(
      testInfo.project.name !== "chromium-desktop",
      "desktop-only public leakage regression"
    );

    const publicCase = {
      id: "leak-public-case",
      title: "公开字段白名单审计案例",
      type: "TYPE_A",
      theme: "铸魂育人",
      author: "公开作者",
      department: "马克思主义学院",
      created_at: "2026-06-11T02:00:00Z",
      view_count: 7,
      like_count: 2,
      content: "公开正文只包含案例内容，不应展示任何审核内部材料。",
      source_material: "公开来源材料：课堂记录摘录。",
      keywords: ["公开标签"],
      ai_reviews: [
        {
          prompt_id: "workflow/leak",
          answer: "LEAK_AI_REVIEW_ANSWER_SHOULD_NOT_RENDER",
          model: "LEAK_MODEL_SHOULD_NOT_RENDER",
          prompt: "LEAK_PROMPT_SHOULD_NOT_RENDER",
        },
      ],
      latest_review_version_id: 999,
      submitted_version_id: 998,
      reviewed_version_id: 997,
      paragraph_comments: [
        { paragraph_id: "p1", message: "LEAK_PARAGRAPH_COMMENT_SHOULD_NOT_RENDER" },
      ],
      admin_comments: [
        {
          reviewer: "admin",
          comments: [
            { paragraph_id: "p1", message: "LEAK_ADMIN_COMMENT_SHOULD_NOT_RENDER" },
          ],
        },
      ],
    };

    await page.route("**/api/cases**", async (route) => {
      const url = new URL(route.request().url());
      if (url.pathname === "/api/cases" && url.searchParams.get("status") === "approved") {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ success: true, data: [publicCase], total: 1 }),
        });
        return;
      }

      if (url.pathname === "/api/cases/leak-public-case") {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ success: true, data: publicCase }),
        });
        return;
      }

      await route.continue();
    });

    await page.goto("/");
    await page.getByRole("link", { name: "案例库" }).click();
    await expect(page.getByText("公开字段白名单审计案例")).toBeVisible();
    await page.getByRole("button", { name: "查看详情" }).click();
    await expect(page.getByRole("heading", { name: "公开字段白名单审计案例" })).toBeVisible();
    await expect(page.getByText("公开正文只包含案例内容，不应展示任何审核内部材料。")).toBeVisible();
    await expect(page.getByText("公开来源材料：课堂记录摘录。")).toBeVisible();
    await expect(page.getByText("公开标签")).toBeVisible();

    await expect(page.getByText("LEAK_AI_REVIEW_ANSWER_SHOULD_NOT_RENDER")).toHaveCount(0);
    await expect(page.getByText("LEAK_MODEL_SHOULD_NOT_RENDER")).toHaveCount(0);
    await expect(page.getByText("LEAK_PROMPT_SHOULD_NOT_RENDER")).toHaveCount(0);
    await expect(page.getByText("LEAK_PARAGRAPH_COMMENT_SHOULD_NOT_RENDER")).toHaveCount(0);
    await expect(page.getByText("LEAK_ADMIN_COMMENT_SHOULD_NOT_RENDER")).toHaveCount(0);
  });

  test("home public detail renders source material without review internals", async ({
    page,
  }, testInfo) => {
    test.skip(
      testInfo.project.name !== "chromium-desktop",
      "desktop-only public home detail regression"
    );

    const publicCase = {
      id: "home-public-source-case",
      title: "首页公开来源材料审计案例",
      type: "TYPE_A",
      theme: "强国建设",
      author: "公开作者",
      department: "马克思主义学院",
      created_at: "2026-06-11T02:30:00Z",
      view_count: 11,
      like_count: 3,
      content: "首页公开详情应展示正文，并保持审核内部信息不可见。",
      source_material: "首页公开来源材料：学院新闻与课堂反馈摘录。",
      keywords: ["首页标签"],
      ai_reviews: [
        {
          answer: "HOME_LEAK_AI_REVIEW_SHOULD_NOT_RENDER",
          model: "HOME_LEAK_MODEL_SHOULD_NOT_RENDER",
        },
      ],
      admin_comments: [
        {
          reviewer: "admin",
          comments: [{ paragraph_id: "p1", message: "HOME_LEAK_ADMIN_SHOULD_NOT_RENDER" }],
        },
      ],
      paragraph_comments: [
        { paragraph_id: "p1", message: "HOME_LEAK_PARAGRAPH_SHOULD_NOT_RENDER" },
      ],
    };

    await page.route("**/api/statistics", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          success: true,
          data: {
            total_cases: 1,
            total_views: 11,
            total_likes: 3,
            by_type: { TYPE_A: 1 },
            by_theme: { 强国建设: 1 },
          },
        }),
      });
    });

    await page.route("**/api/trending**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ success: true, data: [publicCase] }),
      });
    });

    await page.route("**/api/latest**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ success: true, data: [publicCase] }),
      });
    });

    await page.route("**/api/cases/home-public-source-case**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ success: true, data: publicCase }),
      });
    });

    await page.goto("/");
    const latestCases = page.getByLabel("最新案例");
    const homeCard = latestCases.locator(".case-card").filter({ hasText: publicCase.title });
    await expect(homeCard).toBeVisible();
    await expect(homeCard.getByText("浏览 11")).toBeVisible();
    await expect(homeCard.getByText("点赞 3")).toBeVisible();
    await homeCard.getByRole("heading", { name: publicCase.title }).click();

    await expect(page.getByRole("heading", { name: publicCase.title, level: 1 })).toBeVisible();
    await expect(page.getByText(publicCase.content)).toBeVisible();
    await expect(page.getByText(publicCase.source_material)).toBeVisible();
    await expect(page.getByText("首页标签")).toBeVisible();

    await expect(page.getByText("HOME_LEAK_AI_REVIEW_SHOULD_NOT_RENDER")).toHaveCount(0);
    await expect(page.getByText("HOME_LEAK_MODEL_SHOULD_NOT_RENDER")).toHaveCount(0);
    await expect(page.getByText("HOME_LEAK_ADMIN_SHOULD_NOT_RENDER")).toHaveCount(0);
    await expect(page.getByText("HOME_LEAK_PARAGRAPH_SHOULD_NOT_RENDER")).toHaveCount(0);
  });
});
