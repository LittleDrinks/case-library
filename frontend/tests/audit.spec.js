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
  await expect(page.locator(".toast")).toHaveCount(0, { timeout: 4000 });
  await page.screenshot({
    path: testInfo.outputPath(`${name}-${testInfo.project.name}.png`),
    fullPage: true,
  });
}

async function cleanupAuditCases(page, titlePrefix = "Audit案例 ") {
  const token = await page.evaluate(() => localStorage.getItem("case_library_auth_token"));
  const headers = token ? { Authorization: `Bearer ${token}` } : {};
  const response = await page.request.get("/api/cases?status=all&limit=100", { headers });
  if (!response.ok()) return;
  const payload = await response.json();
  const cases = Array.isArray(payload.data) ? payload.data : [];
  for (const item of cases.filter((c) => c.title?.startsWith(titlePrefix))) {
    await page.request.delete(`/api/cases/${item.id}`, { headers });
  }
}

test.describe("manual audit candidate flows", () => {
  test("mobile create flow keeps critical screens readable", async ({ page }, testInfo) => {
    test.skip(
      testInfo.project.name !== "chromium-mobile",
      "mobile-only visual regression for create flow"
    );

    await page.goto("/");
    await login(page, USER);
    await page.getByRole("link", { name: "创建案例" }).click();

    await expect(page.getByText("填写基本信息")).toBeVisible();
    await expect(page.locator(".wizard-main")).toBeInViewport();
    await expect(page.locator("#ccf-title")).toBeVisible();
    await capture(page, testInfo, "mobile-create-step-1");

    await page.getByLabel(/案例标题/).fill(`移动端视觉审计 ${Date.now()}`);
    await page.getByLabel(/所属部门\/学院/).fill("马克思主义学院");
    await page.getByRole("button", { name: "继续" }).scrollIntoViewIfNeeded();
    await page.getByRole("button", { name: "继续" }).click();

    await expect(page.getByText("编写案例内容")).toBeVisible();
    await expect(page.locator("#ccf-content")).toBeVisible();
    await expect(page.locator("#ccf-source")).toBeVisible();
    await capture(page, testInfo, "mobile-create-step-2");

    await page.locator("#ccf-content").fill(
      "移动端创建流程视觉审计正文，覆盖输入框宽度、按钮换行和页面滚动。"
    );
    await page.locator("#ccf-source").fill("移动端来源材料审计文本。");
    await page.getByRole("button", { name: "继续" }).scrollIntoViewIfNeeded();
    await page.getByRole("button", { name: "继续" }).click();

    await expect(page.getByText("选择案例分类")).toBeVisible();
    await expect(page.locator("#ccf-type")).toBeVisible();
    await expect(page.locator("#ccf-theme")).toBeVisible();
    await capture(page, testInfo, "mobile-create-step-3");
  });

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
          form: {
            title: "旧草稿标题",
            author: "过期作者",
            department: "马克思主义学院",
            content: "旧草稿正文",
            source_material: "旧来源材料",
            type: "TYPE_A",
            theme: "铸魂育人",
          },
          savedAt: Date.now(),
        })
      );
    });

    await login(page, USER);
    await page.getByRole("link", { name: "创建案例" }).click();

    await expect(page.getByLabel("作者姓名")).toHaveValue(USER.nickname);
    await expect(page.getByLabel("作者姓名")).not.toHaveValue("过期作者");
    await expect(page.getByLabel(/案例标题/)).toHaveValue("旧草稿标题");
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

    await login(page, ADMIN);
    await cleanupAuditCases(page);
    await logout(page);

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
    await expect(teacherPendingCard.getByText("E2E 来源材料：学院新闻与课堂反馈摘录。").first()).toBeVisible();
    await expect(teacherPendingCard.getByRole("button", { name: "复制版本" }).first()).toBeVisible();
    await capture(page, testInfo, "teacher-version-history");

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
    await expect(page.getByText("E2E 来源材料：学院新闻与课堂反馈摘录。")).toBeVisible();
    await expect(page.getByText("作者 AI 自查意见")).toHaveCount(0);
    await capture(page, testInfo, "public-approved-search-result");
    await page.getByLabel("关闭").click();
    await login(page, ADMIN);
    await cleanupAuditCases(page, title);
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
    await expect(page.getByText("填写基本信息")).toBeVisible();
    await page.getByLabel(/案例标题/).fill(title);
    await page.getByLabel(/所属部门\/学院/).fill("马克思主义学院");
    await page.getByRole("button", { name: "继续" }).click();

    await expect(page.getByText("编写案例内容")).toBeVisible();
    await page.locator("#ccf-content").fill(initialContent);
    await page.locator("#ccf-source").fill(sourceMaterial);
    await page.getByRole("button", { name: "继续" }).click();

    await expect(page.getByText("选择案例分类")).toBeVisible();
    await page.locator("#ccf-type").selectOption("TYPE_A");
    await page.locator("#ccf-theme").selectOption("铸魂育人");
    await page.getByRole("button", { name: "继续" }).click();

    await expect(page.getByRole("heading", { name: "提交前自查" })).toBeVisible();
    await page.getByRole("button", { name: "生成只读审核版本" }).click();
    await expect(page.getByText("100% 已完成")).toBeVisible();
    await expect(page.getByText(/已生成 v2 只读审核版本/)).toBeVisible();
    await expect(page.getByText("AI 段落批注：来源材料要补齐时间和对象。")).toBeVisible();
    await page.getByRole("button", { name: "继续" }).click();
    await expect(page.getByText("确认并提交")).toBeVisible();
    await page.getByRole("button", { name: "正式提交案例" }).click();
    await expect(page.getByText("填写基本信息")).toBeVisible();

    await logout(page);
    await login(page, ADMIN);
    await page.getByRole("link", { name: "审核管理" }).click();
    const pendingCard = page.locator(".case-card").filter({ hasText: title });
    await expect(pendingCard).toBeVisible();
    await pendingCard.getByRole("button", { name: "审核" }).click();
    await expect(page.locator("#review-version")).toHaveValue(/^\d+$/);
    await page.locator("#review-comment").fill("退回修改：来源材料不足。");
    await page.locator("#paragraph-id").selectOption("p2");
    await page.locator("#paragraph-category").selectOption("source");
    await page.locator("#paragraph-severity").selectOption("important");
    await page.locator("#paragraph-message").fill(adminParagraphComment);
    await page.locator("#paragraph-suggestion").fill(adminSuggestion);
    await page.getByLabel("需修改").check();
    await page.getByRole("button", { name: "提交审核" }).click();
    await expect(page.locator(".modal-overlay")).toHaveCount(0);

    await logout(page);
    await login(page, USER);
    await page.getByRole("link", { name: "我的提交" }).click();
    await page.getByRole("tab", { name: "需修改" }).click();
    const revisionCard = page.locator(".case-card").filter({ hasText: title });
    await expect(revisionCard).toBeVisible();
    await revisionCard.getByRole("button", { name: "查看详情" }).click();
    await expect(revisionCard.getByText("人工段落批注", { exact: true })).toBeVisible();
    await expect(revisionCard.getByText(adminParagraphComment)).toBeVisible();
    await expect(revisionCard.getByText(adminSuggestion)).toBeVisible();
    await revisionCard.getByRole("button", { name: "复制版本" }).first().click();
    await expect(page.getByText(/v\d+ 已复制/)).toBeVisible();

    await revisionCard.getByRole("button", { name: "重新提交" }).click();
    const resubmitDialog = page.getByRole("dialog", { name: "重新提交案例" });
    await expect(resubmitDialog).toBeVisible();
    await page.locator("#ms-edit-content").fill(revisedContent);
    await page.locator("#ms-edit-source").fill(`${sourceMaterial}\n补充：2026 年课堂反馈摘要。`);
    await resubmitDialog.getByRole("button", { name: "重新提交" }).click();
    await expect(page.getByText("案例已重新提交，请等待专家审核")).toBeVisible();

    await logout(page);
    await login(page, ADMIN);
    await page.getByRole("link", { name: "审核管理" }).click();
    const resubmittedCard = page.locator(".case-card").filter({ hasText: title });
    await expect(resubmittedCard).toBeVisible();
    await resubmittedCard.getByRole("button", { name: "查看详情" }).click();
    await expect(resubmittedCard.locator(".detail-content-body").first()).toContainText(
      "已根据人工批注补充学院新闻时间"
    );
    await resubmittedCard.getByRole("button", { name: "审核" }).click();
    await page.locator("#review-comment").fill("审核通过：退回意见已修改。");
    await page.getByLabel("通过").check();
    await page.getByRole("button", { name: "提交审核" }).click();
    await expect(page.locator(".modal-overlay")).toHaveCount(0);

    await logout(page);
    await page.getByRole("link", { name: "案例库" }).click();
    await page.getByPlaceholder("搜索案例标题、内容...").fill(title);
    await page.getByRole("button", { name: "搜索" }).click();
    const publicCard = page.locator(".case-card").filter({ hasText: title });
    await expect(publicCard).toBeVisible();
    await publicCard.getByRole("button", { name: "查看详情" }).click();
    const publicDialog = page.getByRole("dialog", { name: title });
    await expect(publicDialog.getByText("已根据人工批注补充学院新闻时间")).toBeVisible();
    await expect(publicDialog.getByText(sourceMaterial)).toBeVisible();
    await expect(page.getByText(adminParagraphComment)).toHaveCount(0);
    await expect(page.getByText("AI 段落批注：来源材料要补齐时间和对象。")).toHaveCount(0);
    await page.getByLabel("关闭").click();

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
    const detailDialog = page.getByRole("dialog", { name: "公开字段白名单审计案例" });
    await expect(detailDialog.getByText("公开正文只包含案例内容，不应展示任何审核内部材料。")).toBeVisible();
    await expect(detailDialog.getByText("公开来源材料：课堂记录摘录。")).toBeVisible();
    await expect(detailDialog.getByText("公开标签")).toBeVisible();

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
    const homeCard = page.locator(".case-card").filter({ hasText: publicCase.title }).first();
    await expect(homeCard).toBeVisible();
    await expect(homeCard.getByText("浏览 11")).toBeVisible();
    await expect(homeCard.getByText("点赞 3")).toBeVisible();
    await homeCard.click();

    const detailDialog = page.getByRole("dialog", { name: publicCase.title });
    await expect(detailDialog.getByText(publicCase.content)).toBeVisible();
    await expect(detailDialog.getByText(publicCase.source_material)).toBeVisible();
    await expect(detailDialog.getByText("首页标签")).toBeVisible();

    await expect(page.getByText("HOME_LEAK_AI_REVIEW_SHOULD_NOT_RENDER")).toHaveCount(0);
    await expect(page.getByText("HOME_LEAK_MODEL_SHOULD_NOT_RENDER")).toHaveCount(0);
    await expect(page.getByText("HOME_LEAK_ADMIN_SHOULD_NOT_RENDER")).toHaveCount(0);
    await expect(page.getByText("HOME_LEAK_PARAGRAPH_SHOULD_NOT_RENDER")).toHaveCount(0);
  });
});
