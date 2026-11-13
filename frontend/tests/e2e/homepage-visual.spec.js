import { expect, test } from "@playwright/test";

const BRAND = "“强国有我”思政案例库";

const DEMO = {
  background: "rgb(246, 244, 239)",
  brand: "rgb(186, 28, 34)",
  card: "rgb(255, 255, 255)",
  header: "rgba(255, 255, 255, 0.92)",
  ink: "rgb(38, 34, 31)",
  line: "rgb(233, 227, 218)",
};
const DESKTOP_PAPER = { borderRadius: "2px", padding: "56px 48px 72px" };
const MOBILE_PAPER = { borderRadius: "2px", padding: "30px 24px 72px" };

async function openHome(page, width, height) {
  await page.setViewportSize({ width, height });
  await page.goto("/#/");
  await expect(page.getByRole("region", { name: "平台动态" })).toBeVisible();
  await expect(page.getByRole("region", { name: "推荐案例" })).toBeVisible();
}

async function loginAsAdmin(page) {
  await page.goto("/#/login");
  await page.getByLabel("用户名").fill("admin");
  await page.getByLabel("密码").fill("admin123");
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page).toHaveURL(/#\/$/);
}

async function expectBrand(page) {
  await expect(page).toHaveTitle(BRAND);
  const brand = page.getByRole("link", { name: `${BRAND}首页` });
  await expect(brand).toBeVisible();
  await expect(brand).toHaveText(BRAND);
}

async function expectWorkbenchBrand(page) {
  await expect(page).toHaveTitle(BRAND);
  const brand = page.locator('.workbench-brand-link');
  await expect(brand).toBeVisible();
  await expect(brand).toHaveAttribute('href', '#/');
  await expect(brand.getByRole('img', { name: '上海大学' })).toBeVisible();
  await expect(brand).toContainText('思政教学案例库');
}

async function expectWorkspaceHeader(page) {
  const header = page.locator('.workspace-header');
  await expect(header).toBeVisible();
  await expectStyles(header, {
    backgroundColor: 'rgba(255, 255, 255, 0.97)', borderBottomColor: DEMO.line,
  });
  expect((await boxOf(header)).height).toBeLessThanOrEqual(64);
  await expect(page.locator('.site-header')).toHaveCount(0);
}

async function expectLoginBrand(page) {
  await page.goto("/#/login");
  await expect(page).toHaveTitle(BRAND);
  await expect(page.getByRole("heading", { name: BRAND })).toBeVisible();
}

async function expectHomeBrand(page) {
  await openHome(page, 1024, 1000);
  await expectBrand(page);
  await expect(page.getByRole("heading", { name: `${BRAND}首页` })).toBeVisible();
}

async function expectCaseDetailBrand(page) {
  await page.goto("/#/cases/c-02");
  await expect(page.locator(".workspace-header")).toBeVisible();
  await expect(page.locator(".canvas-editor")).toHaveAttribute("contenteditable", "false");
  await expectWorkbenchBrand(page);
}

async function expectPrivateRouteBrand(page) {
  await loginAsAdmin(page);
  await page.goto("/#/workbench/c-02");
  await expect(page.locator(".workbench-page")).toBeVisible();
  await expectWorkbenchBrand(page);
  await page.goto("/#/admin");
  await expect(page.getByRole("heading", { name: "管理后台" })).toBeVisible();
  await expectBrand(page);
}

async function expectNoOverflow(page, width) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
}

async function expectDesktopLoginVisual(page) {
  await expectLoginBrand(page);
  await expectStyles(page.locator(".login-panel"), {
    backgroundColor: DEMO.card, borderRadius: "7px",
  });
  await expect(page.locator(".login-submit")).toHaveCSS("background-color", DEMO.brand);
}

async function expectMobileLoginVisual(page) {
  await expectLoginBrand(page);
  await expectStyles(page.locator(".login-page"), {
    backgroundColor: DEMO.card, padding: "64px 18px 18px",
  });
  await expect(page.locator(".login-panel")).toHaveCSS("border-left-width", "0px");
  await expectNoOverflow(page, 390);
}

async function openCaseDetail(page) {
  await page.goto("/#/cases/c-02");
  await expect(page.locator(".document-paper")).toBeVisible();
  await expect(page.locator(".canvas-editor")).toHaveAttribute("contenteditable", "false");
  await expectWorkbenchBrand(page);
}

async function expectDesktopCaseDetail(page) {
  await openCaseDetail(page);
  await expectWorkspaceHeader(page);
  await expect(page.locator(".outline-wrap")).toBeVisible();
  await expectStyles(page.locator(".canvas-workspace"), { display: "grid" });
  await expectStyles(page.locator(".document-paper"), DESKTOP_PAPER);
}

async function expectMobileCaseDetail(page) {
  await openCaseDetail(page);
  await expectWorkspaceHeader(page);
  await expect(page.locator(".outline-wrap")).toBeVisible();
  await expectStyles(page.locator(".canvas-workspace"), { display: "grid" });
  await expectStyles(page.locator(".assistant-rail"), { position: "absolute" });
  await expectStyles(page.locator(".document-paper"), MOBILE_PAPER);
  await expectNoOverflow(page, 390);
}

async function openWorkbench(page) {
  await page.goto("/#/workbench/c-02");
  await expect(page.locator(".document-paper")).toBeVisible();
  await expectWorkbenchBrand(page);
}

async function expectDesktopWorkbench(page) {
  await openWorkbench(page);
  await expectWorkspaceHeader(page);
  await expect(page.locator(".outline-wrap")).toBeVisible();
  await expectStyles(page.locator(".canvas-workspace"), { display: "grid" });
  await expectStyles(page.locator(".document-paper"), DESKTOP_PAPER);
}

async function expectMobileWorkbench(page) {
  await openWorkbench(page);
  await expectWorkspaceHeader(page);
  await expect(page.locator(".outline-wrap")).toBeVisible();
  await expectStyles(page.locator(".canvas-workspace"), { display: "grid" });
  await expectStyles(page.locator(".assistant-rail"), { position: "absolute" });
  await expectStyles(page.locator(".document-paper"), MOBILE_PAPER);
  await expectNoOverflow(page, 390);
}

async function openAdminDashboard(page) {
  await page.goto("/#/admin");
  await expect(page.getByRole("heading", { name: "管理后台" })).toBeVisible();
  await expect(page.locator(".admin-queue").first()).toBeVisible();
  await expectBrand(page);
}

async function expectDesktopAdminDashboard(page) {
  await openAdminDashboard(page);
  await expectDesktopHeader(page);
  const sidebar = await boxOf(page.getByRole("navigation", { name: "管理工具" }));
  const content = await boxOf(page.locator(".admin-content"));
  expect(sidebar.x + sidebar.width).toBeLessThan(content.x);
  await expect(page.getByRole("link", { name: "管理概览", exact: true })).toHaveAttribute("aria-current", "page");
  await expectNoOverflow(page, 1600);
}

async function expectMobileAdminDashboard(page) {
  await openAdminDashboard(page);
  await expectMobileHeader(page);
  const sidebar = await boxOf(page.getByRole("navigation", { name: "管理工具" }));
  const content = await boxOf(page.locator(".admin-content"));
  expect(sidebar.y + sidebar.height).toBeLessThan(content.y);
  await expect(page.getByRole("navigation", { name: "管理工具" }).getByRole("link")).toHaveCount(5);
  await expectNoOverflow(page, 390);
}

async function boxOf(locator) {
  await expect(locator).toBeVisible();
  const box = await locator.boundingBox();
  expect(box).not.toBeNull();
  return box;
}

async function stylesOf(locator, properties) {
  return locator.evaluate((node, names) => {
    const style = getComputedStyle(node);
    return Object.fromEntries(names.map((name) => [name, style[name]]));
  }, properties);
}

async function expectStyles(locator, expected) {
  const actual = await stylesOf(locator, Object.keys(expected));
  expect(actual).toEqual(expected);
}

function expectNear(actual, expected, tolerance = 1) {
  expect(Math.abs(actual - expected)).toBeLessThanOrEqual(tolerance);
}

async function expectDesktopHeader(page) {
  const header = page.locator(".site-header");
  expectNear((await boxOf(header)).height, 58);
  expectNear((await boxOf(header.getByRole("img", { name: "上海大学" }))).height, 32);
  await expectStyles(header, {
    backgroundColor: DEMO.header,
    borderBottomColor: DEMO.line,
    columnGap: "26px",
    paddingLeft: "22px",
    paddingRight: "22px",
    position: "sticky",
  });
}

async function expectMobileHeader(page) {
  const header = page.locator(".site-header");
  const brand = page.getByRole("link", { name: `${BRAND}首页` });
  const navigation = page.getByRole("navigation", { name: "主导航" });
  const [headerBox, brandBox, navigationBox] = await Promise.all([
    boxOf(header), boxOf(brand), boxOf(navigation),
  ]);
  expect(headerBox.height).toBeGreaterThanOrEqual(80);
  expect(navigationBox.y).toBeGreaterThan(brandBox.y + brandBox.height);
  expectNear(navigationBox.x, 12);
  expectNear(navigationBox.width, 366);
  expectNear((await boxOf(brand.getByRole("img", { name: "上海大学" }))).height, 26);
  await expectMobileHeaderStyles(header);
  await expect(brand.locator("span")).toBeVisible();
  await expect(navigation.getByText("首页", { exact: true })).toBeVisible();
  await expect(navigation.getByText("资源检索", { exact: true })).toBeVisible();
}

async function expectMobileHeaderStyles(header) {
  await expectStyles(header, {
    backgroundColor: DEMO.header,
    borderBottomColor: DEMO.line,
    columnGap: "10px",
    padding: "0px 12px 8px",
    position: "sticky",
    rowGap: "10px",
  });
}

async function expectCampusHome(page, width) {
  const hero = page.locator('.home-hero');
  const search = page.getByRole('search');
  await expect(hero.locator('img')).toBeVisible();
  expect(await hero.locator('img').evaluate(image => image.complete && image.naturalWidth > 0)).toBe(true);
  await expect(page.getByRole('textbox', { name: '检索全库资源' })).toBeVisible();
  const [heroBox, searchBox, weekBox] = await Promise.all([
    boxOf(hero), boxOf(search), boxOf(page.getByRole('region', { name: '平台动态' })),
  ]);
  expect(searchBox.x).toBeGreaterThan(heroBox.x);
  expect(searchBox.x + searchBox.width).toBeLessThan(heroBox.x + heroBox.width);
  expect(searchBox.y).toBeGreaterThan(heroBox.y);
  expect(searchBox.y + searchBox.height).toBeLessThan(heroBox.y + heroBox.height);
  expect(weekBox.y).toBeGreaterThanOrEqual(heroBox.y + heroBox.height);
  await expect(page.locator('.home-hero-stats > div')).toHaveCount(3);
  await expectNoOverflow(page, width);
}

for (const width of [1600, 1024]) {
  test(`${width}px 首页呈现校园搜索、动态条和双列推荐`, async ({ page }) => {
    await openHome(page, width, 1000);
    await expectCampusHome(page, width);
    const [cases, materials] = await Promise.all([
      boxOf(page.getByRole('region', { name: '推荐案例' })),
      boxOf(page.getByRole('region', { name: '推荐素材' })),
    ]);
    expectNear(cases.y, materials.y);
    expect(materials.x).toBeGreaterThan(cases.x + cases.width);
    expect(cases.width).toBeGreaterThan(materials.width);
  });
}

test('390px 首页保留搜索和统计，推荐内容改为单列且不横向溢出', async ({ page }) => {
  await openHome(page, 390, 844);
  await expectCampusHome(page, 390);
  const [cases, materials] = await Promise.all([
    boxOf(page.getByRole('region', { name: '推荐案例' })),
    boxOf(page.getByRole('region', { name: '推荐素材' })),
  ]);
  expectNear(cases.x, materials.x);
  expectNear(cases.width, materials.width);
  expect(materials.y).toBeGreaterThanOrEqual(cases.y + cases.height);
});

test("首页、登录、详情、工作台和管理后台使用统一品牌", async ({ page }) => {
  await expectLoginBrand(page);
  await expectHomeBrand(page);
  await expectCaseDetailBrand(page);
  await expectPrivateRouteBrand(page);
});

test("登录页在桌面和 390px 保持品牌与表单布局", async ({ page }) => {
  await page.setViewportSize({ width: 1024, height: 800 });
  await expectDesktopLoginVisual(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await expectMobileLoginVisual(page);
});

test("公开案例详情在桌面和 390px 保持阅读布局", async ({ page }) => {
  await page.setViewportSize({ width: 1600, height: 1000 });
  await expectDesktopCaseDetail(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await expectMobileCaseDetail(page);
});

test("管理员工作台和后台在桌面和 390px 保持品牌布局", async ({ page }) => {
  await page.setViewportSize({ width: 1600, height: 1000 });
  await loginAsAdmin(page);
  await expectDesktopWorkbench(page);
  await expectDesktopAdminDashboard(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await expectMobileWorkbench(page);
  await expectMobileAdminDashboard(page);
});

test("工作台和管理导入页共享暖纸红全局主题", async ({ page }) => {
  await loginAsAdmin(page);
  await page.goto("/#/workbench/c-02");
  await expectStyles(page.locator(".workbench-page"), { backgroundColor: DEMO.background });
  await expectWorkspaceHeader(page);
  await page.goto("/#/admin/material-imports");
  await expectStyles(page.locator(".admin-page"), { backgroundColor: DEMO.background });
  await expect(page.locator(".material-import-form")).toHaveCSS("border-top-color", DEMO.line);
  await expect(page.locator(".material-import-submit")).toHaveCSS("background-color", DEMO.brand);
  const active = page.getByRole("link", { name: "管理后台", exact: true });
  await expect(active).toHaveCSS("border-radius", "999px");
  await expect(active).toHaveCSS("background-color", "rgb(248, 238, 237)");
});
