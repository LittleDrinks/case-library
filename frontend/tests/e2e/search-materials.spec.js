import { expect, test } from "@playwright/test";

async function login(page) {
  await page.goto("/#/login?redirect=/workbench/c-draft-1");
  await page.getByLabel("用户名").fill("user");
  await page.getByLabel("密码").fill("user123");
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page).toHaveURL(/#\/workbench\/c-draft-1$/);
}

async function clearMaterials(request) {
  const auth = await (await request.get("/api/auth/session")).json();
  let current = await (await request.get("/api/cases/c-draft-1")).json();
  const rows = await (await request.get("/api/cases/c-draft-1/materials")).json();
  for (const row of rows) {
    const response = await request.delete(
      `/api/cases/c-draft-1/materials/${encodeURIComponent(row.id)}?revision=${current.revision}`,
      { headers: { "X-CSRF-Token": auth.csrfToken } },
    );
    expect(response.ok()).toBe(true);
    current = await (await request.get("/api/cases/c-draft-1")).json();
  }
}

function watchRequests(page, path) {
  const requests = [];
  page.on("request", (request) => {
    if (request.url().includes(path)) requests.push(request.url());
  });
  return requests;
}

async function search(page, query) {
  await waitForSearchReady(page, query);
  await page.getByLabel("搜索公开案例").fill(query);
  await page.getByRole("button", { name: "检索", exact: true }).click();
}

async function waitForSearchReady(page, query) {
  await expect.poll(async () => {
    const response = await page.context().request.get("/api/search", {
      params: { q: query, kind: "all", pageSize: 20 },
    });
    return response.ok();
  }, { timeout: 45_000 }).toBe(true);
}

function queryRequests(requests, query) {
  return requests.filter((url) => new URL(url).searchParams.get("q") === query);
}

async function assertOneSearchRequest(page, requests) {
  await expect(page.getByRole("region", { name: "检索结果" })).toBeVisible();
  requests.length = 0;
  const response = page.waitForResponse(/\/api\/search\?q=%E6%80%9D%E6%94%BF/);
  await search(page, "思政");
  expect((await response).ok()).toBe(true);
  await page.evaluate(() => new Promise((resolve) => {
    requestAnimationFrame(() => requestAnimationFrame(resolve));
  }));
  expect(queryRequests(requests, "思政")).toHaveLength(1);
}

async function assertAnonymousAI(page, chatRequests) {
  const answer = page.getByRole("region", { name: "AI 回答" });
  await expect(answer).toContainText("未生成 AI 解读（省流模式）");
  expect(chatRequests).toEqual([]);
  await page.getByRole("button", { name: "生成 AI 解读" }).click();
  await expect(answer.getByRole("link", { name: "登录后生成 AI 回答" })).toBeVisible();
  await expect(page.getByRole("list", { name: "AI 回答引用来源" })).toHaveCount(0);
}

async function assertNoSearchAI(page, settingsRequests, chatRequests) {
  await expect(page.getByRole("region", { name: "AI 回答" })).toHaveCount(0);
  expect(settingsRequests).toEqual([]);
  expect(chatRequests).toEqual([]);
}

async function submitBlankDirectorySearch(page) {
  const blankSearch = expectSearchPageRequest(page, "all", false);
  await page.getByLabel("搜索公开案例").fill("   ");
  await page.getByRole("button", { name: "检索", exact: true }).click();
  await blankSearch;
  await expect(page).toHaveURL(/#\/search$/);
}

async function browseEmptyDirectory(page) {
  const caseTab = expectSearchPageRequest(page, "case", false);
  await page.getByRole("tab", { name: /案例/ }).click();
  await caseTab;
  await page.getByRole("button", { name: "高级筛选" }).click();
  const filtered = page.waitForResponse((response) => (
    new URL(response.url()).searchParams.getAll("typeName").length === 1
  ));
  await page.getByRole("group", { name: "案例类型" }).getByLabel(/校本实践类/).check();
  await filtered;
  const allTab = expectSearchPageRequest(page, "all", false);
  await page.getByRole("tab", { name: /全部/ }).click();
  await allTab;
}

async function pageEmptyDirectory(page) {
  const nextPage = expectSearchPageRequest(page, "all", true);
  await page.getByRole("button", { name: "下一页" }).click();
  await nextPage;
}

async function assertGraph(page) {
  await page.getByRole("button", { name: "图谱", exact: true }).click();
  await expect(page.getByRole("region", { name: "当前检索结果图谱" })).toBeVisible();
  await expect(page.getByRole("button", { name: /案例.*钱伟长图书馆/ })).toBeVisible();
  await expect(page.getByRole("list", { name: "图谱关系列表" })).toContainText(
    /钱伟长图书馆——科学家精神的大思政课堂.*共同主题.*科学家精神/,
  );
}

test("空查询只浏览目录，不触发 AI", async ({ page }) => {
  test.setTimeout(60_000);
  const chatRequests = watchRequests(page, "/api/ai/chat");
  const settingsRequests = watchRequests(page, "/api/ai/settings");
  await waitForSearchReady(page, "");
  await page.goto("/#/search");
  await expect(page.getByRole("region", { name: "检索结果" })).toBeVisible();
  await assertNoSearchAI(page, settingsRequests, chatRequests);
  await submitBlankDirectorySearch(page);
  await browseEmptyDirectory(page);
  await expect(page.getByRole("tab", { name: /知识/ })).toBeVisible();
  await expect(page.getByRole("button", { name: "高级筛选" })).toBeVisible();
  await pageEmptyDirectory(page);
  await assertNoSearchAI(page, settingsRequests, chatRequests);
});

test("普通关键词保留省流提示和手动生成入口", async ({ page }) => {
  const searchRequests = watchRequests(page, "/api/search");
  const chatRequests = watchRequests(page, "/api/ai/chat");
  const settingsRequests = watchRequests(page, "/api/ai/settings");
  await page.goto("/#/search");
  await assertOneSearchRequest(page, searchRequests);
  await assertAnonymousAI(page, chatRequests);
  await assertGraph(page);
  expect(settingsRequests).toEqual([]);
});

test("问题式检索自动进入 AI 解读流程", async ({ page }) => {
  const chatRequests = watchRequests(page, "/api/ai/chat");
  const settingsRequests = watchRequests(page, "/api/ai/settings");
  await page.goto("/#/search");
  await search(page, "如何");
  await expect(page.getByRole("link", { name: "登录后生成 AI 回答" })).toBeVisible();
  await expect(page.getByRole("button", { name: "生成 AI 解读" })).toHaveCount(0);
  await expect(page.getByRole("list", { name: "AI 回答引用来源" })).toHaveCount(0);
  expect(chatRequests).toEqual([]);
  expect(settingsRequests).toEqual([]);
});

async function assertCaseFacets(page) {
  await page.getByRole("tab", { name: /案例/ }).click();
  await page.getByRole("button", { name: "高级筛选" }).click();
  const filtered = page.waitForResponse((response) => {
    const params = new URL(response.url()).searchParams;
    return params.getAll("typeName").length === 2 && !params.has("cursor");
  });
  await page.getByRole("group", { name: "案例类型" }).getByLabel(/校本实践类/).check();
  await page.getByRole("group", { name: "案例类型" }).getByLabel(/科技创新与科技报国类/).check();
  await filtered;
  await expect(page.getByRole("button", { name: "移除筛选：校本实践类" })).toBeVisible();
  await expect(page.getByRole("button", { name: "移除筛选：科技创新与科技报国类" })).toBeVisible();
  await expect(page.getByRole("region", { name: "检索结果" }).getByRole("article")).toHaveCount(3);
  await page.reload();
  await expect(page.getByRole("button", { name: "移除筛选：校本实践类" })).toBeVisible();
}

async function assertMaterialFacets(page) {
  await page.getByRole("button", { name: "清空筛选" }).click();
  await expect(page.getByRole("region", { name: "检索结果" }).getByRole("article")).toHaveCount(4);
  await page.getByRole("tab", { name: /素材/ }).click();
  await page.getByRole("button", { name: "高级筛选" }).click();
  await page.getByRole("group", { name: "信源等级" }).getByLabel(/原始权威来源/).check();
  await expect(page.getByRole("button", { name: "移除筛选：原始权威来源" })).toBeVisible();
}

test("高级筛选支持页签分面、多选 chips 和清空", async ({ page }) => {
  await page.goto("/#/search?q=思政");
  await assertCaseFacets(page);
  await assertMaterialFacets(page);
});

test("知识检索展示章节且不伪造外部链接", async ({ page }) => {
  await page.goto("/#/search?q=生成式人工智能");
  await page.getByRole("tab", { name: /知识/ }).click();
  const result = page.getByRole("region", { name: "检索结果" }).getByRole("article").first();
  await expect(result.locator(":scope > span")).toHaveText("知识");
  await expect(result.locator("small")).toContainText(/第[一二三四五六七八九十]+章/);
  await expect(result.getByRole("link")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "高级筛选" })).toHaveCount(0);
  await expect(page.getByRole("group", { name: "更新时间" })).toHaveCount(0);
});

async function expectSearchPageRequest(page, kind, hasCursor) {
  const response = await page.waitForResponse((candidate) => {
    const url = new URL(candidate.url());
    return url.pathname === "/api/search"
      && url.searchParams.get("kind") === kind
      && url.searchParams.has("cursor") === hasCursor;
  });
  expect(response.ok()).toBe(true);
  return response;
}

async function expectCursorAbsentFromUrl(page) {
  const hash = await page.evaluate(() => location.hash);
  expect(new URLSearchParams(hash.split("?")[1] || "").has("cursor")).toBe(false);
}

async function browseKeywordPages(page) {
  const firstPage = expectSearchPageRequest(page, "knowledge", false);
  await page.getByRole("tab", { name: /知识/ }).click();
  await firstPage;
  await expect(page.getByText(/第 1 页 · 共/)).toBeVisible();
  const secondPage = expectSearchPageRequest(page, "knowledge", true);
  await page.getByRole("button", { name: "下一页" }).click();
  await secondPage;
  await expect(page.getByText(/第 2 页 · 共/)).toBeVisible();
  await expectCursorAbsentFromUrl(page);
}

async function browseKeywordKind(page) {
  const changedScope = expectSearchPageRequest(page, "case", false);
  await page.getByRole("tab", { name: /案例/ }).click();
  const changedPayload = await (await changedScope).json();
  expect(changedPayload).toMatchObject({ page: 1, metadataIncluded: true });
}

test("公共检索按页签请求对应类型并翻页", async ({ page }) => {
  const chatRequests = watchRequests(page, "/api/ai/chat");
  const settingsRequests = watchRequests(page, "/api/ai/settings");
  await page.goto("/#/search?q=马克思");
  await browseKeywordPages(page);
  await browseKeywordKind(page);
  expect(chatRequests).toEqual([]);
  expect(settingsRequests).toEqual([]);
});

test("登录但未配置 AI 时检索提供设置入口", async ({ page }) => {
  await login(page);
  await page.goto("/#/search?q=思政");
  await page.getByRole("button", { name: "生成 AI 解读" }).click();
  await expect(page.getByRole("region", { name: "AI 回答" })).toContainText("当前账号尚未配置可用模型");
  await expect(page.getByRole("link", { name: "配置 AI 模型" })).toHaveAttribute("href", "#/ai-settings");
});

test("公共检索两种视图在手机端无横向溢出", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/#/search?q=思政");
  for (const mode of ["列表", "图谱"]) {
    await page.getByRole("button", { name: mode, exact: true }).click();
    expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(1);
  }
  await page.getByRole("button", { name: "列表", exact: true }).click();
  await page.getByRole("tab", { name: /案例/ }).click();
  await page.getByRole("button", { name: "高级筛选" }).click();
  await page.getByRole("group", { name: "案例类型" }).getByLabel(/校本实践类/).check();
  expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(1);
});

async function selectMaterial(page, title) {
  await page.getByLabel(`选择${title}`).check();
  await page.getByRole("button", { name: "加入当前案例" }).click();
  await expect(page.getByText("已加入 1 条素材")).toBeVisible();
  await page.getByRole("link", { name: "返回当前案例" }).click();
}

async function assertMaterialAttached(page, title) {
  await expect(page).toHaveURL(/#\/workbench\/c-draft-1$/);
  await page.getByLabel("辅助面板").getByRole("button", { name: "附件" }).click();
  await page.getByRole("button", { name: /素材 1/ }).click();
  await expect(page.getByText(title, { exact: true })).toBeVisible();
}

test("作者从工作台进入带案例上下文的素材掌控台", async ({ page }) => {
  await login(page);
  await clearMaterials(page.context().request);
  await page.reload();
  await page.getByLabel("辅助面板").getByRole("button", { name: "附件" }).click();
  await page.getByRole("link", { name: "打开素材掌控台" }).click();
  await expect(page).toHaveURL(/#\/materials\?caseId=c-draft-1$/);
  await expect(page.getByRole("heading", { name: "素材掌控台" })).toBeVisible();
  await expect(page.getByRole("group", { name: "来源权威性" })).toBeVisible();
  await expect(page.getByRole("group", { name: "素材类型" })).toBeVisible();
  await expect(page.getByRole("group", { name: "使用条件" })).toBeVisible();
  await expect(page.getByLabel("仅可对外使用")).toBeVisible();
  const title = "高等学校课程思政建设指导纲要（教高〔2020〕3号）";
  await page.getByLabel("搜索素材").fill(title);
  await page.getByRole("button", { name: "搜索", exact: true }).click();
  await expect(page.getByText(title, { exact: true })).toBeVisible();
  await selectMaterial(page, title);
  await assertMaterialAttached(page, title);
});

test("素材掌控台筛选全库并可切回当前案例素材", async ({ page }) => {
  await login(page);
  await page.goto("/#/materials?caseId=c-draft-1");
  const original = page.waitForResponse((response) => (
    new URL(response.url()).searchParams.get("authority") === "original"
  ));
  await page.getByRole("group", { name: "来源权威性" }).getByLabel("原始权威").check();
  await original;
  await expect(page.getByText("左侧条件筛选当前页")).toHaveCount(0);
  const mounted = page.waitForResponse((response) => (
    new URL(response.url()).searchParams.get("mountedInCaseId") === "c-draft-1"
  ));
  await page.getByRole("button", { name: /当前案例候选/ }).click();
  await mounted;
});

test("素材掌控台在手机端无横向溢出", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await login(page);
  await page.goto("/#/materials?caseId=c-draft-1");
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - innerWidth);
  expect(overflow).toBeLessThanOrEqual(1);
});

test("素材掌控台按 50 条分页并保持手机端无溢出", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await login(page);
  await page.goto("/#/materials?caseId=c-draft-1");
  await expect(page.getByText(/第 1 页 · 共/)).toBeVisible();
  const secondPage = expectSearchPageRequest(page, "material", true);
  await page.getByRole("button", { name: "下一页" }).click();
  await secondPage;
  await expect(page.getByText(/第 2 页 · 共/)).toBeVisible();
  await expectCursorAbsentFromUrl(page);
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - innerWidth);
  expect(overflow).toBeLessThanOrEqual(1);
});
