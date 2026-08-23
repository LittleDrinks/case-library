import { expect, test } from "@playwright/test";

const PUBLIC_CASE = "钱伟长图书馆——科学家精神的大思政课堂";
const OTHER_PUBLIC_CASE = "《智能控制》：高挑战项目牵引新工科育人";
const PRIVATE_CASE = "供应链中断情境下的抉择：科技自立自强思想实验";
const PENDING_CASE = "生成式人工智能进课堂：使用边界与课堂治理研讨";

async function login(page, username, password) {
  await page.goto("/#/login");
  await page.getByLabel("用户名").fill(username);
  await page.getByLabel("密码").fill(password);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page).toHaveURL(/#\/$/);
}

async function searchFor(page, query) {
  await page.getByRole("link", { name: "资源检索", exact: true }).click();
  await expect(page).toHaveURL(/#\/search$/);
  const search = page.getByLabel("搜索公开案例");
  await search.fill(query);
  await search.press("Enter");
}

async function authSession(request) {
  return (await request.get("/api/auth/session")).json();
}

async function lifecycle(request, caseId, command) {
  const auth = await authSession(request);
  const current = await (await request.get(`/api/cases/${caseId}`)).json();
  const response = await request.post(`/api/cases/${caseId}/lifecycle`, {
    headers: { "X-CSRF-Token": auth.csrfToken },
    data: { command, revision: current.revision },
  });
  expect(response.ok()).toBe(true);
}

async function createCase(request, title) {
  const auth = await authSession(request);
  const response = await request.post("/api/cases", {
    headers: { "X-CSRF-Token": auth.csrfToken }, data: { title },
  });
  expect(response.ok()).toBe(true);
  return response.json();
}

async function expectInsideViewport(locator, width) {
  const boxes = await locator.evaluateAll((nodes) => nodes.map((node) => {
    const { left, right } = node.getBoundingClientRect();
    return { left, right, clipped: node.scrollWidth > node.clientWidth };
  }));
  expect(boxes.every(({ left, right, clipped }) => left >= 0 && right <= width && !clipped)).toBe(true);
}

test("匿名用户在首页发现推荐并检索公开案例", async ({ page }) => {
  await page.goto("/#/");

  await expect(page.getByRole("heading", { name: "平台动态" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "时政要闻" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "平台公告" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "推荐案例" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "推荐素材" })).toBeVisible();
  await expect(page.getByRole("link", { name: PUBLIC_CASE })).toBeVisible();
  await expect(page.getByText("高等学校课程思政建设指导纲要", { exact: false })).toBeVisible();
  await expect(page.getByText(PRIVATE_CASE)).toHaveCount(0);
  await expect(page.getByText("暂时没有可展示的新闻")).toBeVisible();
  await expect(page.getByText("暂无公告")).toBeVisible();
  await searchFor(page, "钱伟长");
  await expect(page.getByRole("link", { name: PUBLIC_CASE })).toBeVisible();
  await expect(page.getByRole("link", { name: OTHER_PUBLIC_CASE })).toHaveCount(0);
});

test("管理员登录后落在首页并可切换到我的案例", async ({ page }) => {
  await login(page, "admin", "admin123");

  await expect(page.getByRole("link", { name: "首页", exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: "资源检索", exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: "管理后台", exact: true })).toBeVisible();
  await page.getByRole("link", { name: "我的案例", exact: true }).click();
  await expect(page).toHaveURL(/#\/my-cases$/);
  await expect(page.getByRole("heading", { name: "我的案例", exact: true })).toBeVisible();
  await expect(page.getByText(PUBLIC_CASE)).toBeVisible();
});

test("管理员从管理后台发现待审案例并进入审核工作台", async ({ page }) => {
  await login(page, "admin", "admin123");
  await page.getByRole("link", { name: "管理后台", exact: true }).click();

  await expect(page).toHaveURL(/#\/admin$/);
  await expect(page.getByRole("heading", { name: "案例审核" })).toBeVisible();
  const row = page.getByRole("article", { name: `待审核：${PENDING_CASE}` });
  await row.getByRole("link", { name: "审核", exact: true }).click();
  await expect(page).toHaveURL(/#\/admin\/review\/c-pending-1$/);
  await expect(page.locator(".workspace-crumb")).toContainText("审核管理");
});

test("教师从我的案例新建默认案例并进入作者工作台", async ({ page }) => {
  await login(page, "user", "user123");
  await page.getByRole("link", { name: "我的案例", exact: true }).click();

  await page.getByRole("button", { name: "新建案例", exact: true }).click();

  await expect(page).toHaveURL(/#\/workbench\/c-[a-f0-9]{12}$/);
  await expect(page.getByLabel("案例标题")).toHaveValue("未命名案例");
  await expect(page.locator(".canvas-editor")).toHaveAttribute("contenteditable", "true");
});

test("教师按案例状态看到明确入口", async ({ page }) => {
  await login(page, "user", "user123");
  await page.getByRole("link", { name: "我的案例", exact: true }).click();
  const draft = page.locator(".case-card", { hasText: PRIVATE_CASE });
  const pending = page.locator(".case-card", { hasText: PENDING_CASE });

  await expect(draft.getByRole("link", { name: "继续编辑" })).toBeVisible();
  await expect(pending.getByRole("link", { name: "查看提交" })).toBeVisible();
  await draft.getByRole("link", { name: "继续编辑" }).click();
  await expect(page).toHaveURL(/#\/workbench\/c-draft-1$/);
});

test("教师在审核开始后看到查看审核入口", async ({ page }) => {
  const marker = `审核入口 ${Date.now()}`;
  await login(page, "user", "user123");
  const created = await createCase(page.context().request, marker);
  await lifecycle(page.context().request, created.id, "submit");
  await page.getByRole("button", { name: "退出登录" }).click();
  await login(page, "admin", "admin123");
  await lifecycle(page.context().request, created.id, "start");
  await page.getByRole("button", { name: "退出登录" }).click();
  await login(page, "user", "user123");
  await page.goto("/#/my-cases");

  const reviewing = page.locator(".case-card", { hasText: marker });
  await expect(reviewing.getByRole("link", { name: "查看审核" })).toBeVisible();
});

test("已发布案例从我的案例和工作台进入公开页", async ({ page }) => {
  await login(page, "admin", "admin123");
  await page.goto("/#/my-cases");
  const published = page.locator(".case-card", { hasText: PUBLIC_CASE });

  await published.getByRole("link", { name: "查看公开页" }).click();
  await expect(page).toHaveURL(/#\/cases\/c-02$/);
  await expect(page.getByRole("link", { name: "进入工作台" })).toBeVisible();
  await page.goto("/#/workbench/c-02");
  const publicLink = page.locator(".workspace-header").getByRole("link", { name: "查看公开页" });
  await expect(publicLink).toBeVisible();
  await publicLink.click();
  await expect(page).toHaveURL(/#\/cases\/c-02$/);
});

test("匿名用户从公开案例卡进入独立只读详情", async ({ page }) => {
  await page.goto("/#/");

  await page.getByRole("link", { name: PUBLIC_CASE }).click();

  await expect(page).toHaveURL(/#\/cases\/c-02$/);
  await expect(page.getByRole("heading", { level: 1, name: PUBLIC_CASE })).toBeVisible();
  await expect(page.getByRole("heading", { name: "案例信息" })).toBeVisible();
  await expect(page.getByRole("link", { name: "导出 DOCX" })).toBeVisible();
  await expect(page.getByRole("link", { name: "进入工作台" })).toHaveCount(0);
  await expect(page.locator(".workspace-header")).toHaveCount(0);
  await expect(page.getByRole("navigation", { name: "辅助面板" })).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "素材", exact: true })).toBeVisible();
});

test("390px 首页无水平溢出且主导航可用", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await login(page, "admin", "admin123");
  const navigation = page.getByRole("navigation", { name: "主导航" }).getByRole("link");

  await expectInsideViewport(navigation, 390);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  await page.getByRole("link", { name: "我的案例", exact: true }).click();
  await expect(page).toHaveURL(/#\/my-cases$/);
  await page.getByRole("link", { name: "首页", exact: true }).click();
  await expect(page).toHaveURL(/#\/$/);
});
