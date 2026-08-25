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
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await expectBrand(page);
}

async function expectPrivateRouteBrand(page) {
  await loginAsAdmin(page);
  await page.goto("/#/workbench/c-02");
  await expect(page.locator(".workbench-page")).toBeVisible();
  await expectBrand(page);
  await page.goto("/#/admin");
  await expect(page.getByRole("heading", { name: "管理后台" })).toBeVisible();
  await expectBrand(page);
}

async function boxOf(locator) {
  await expect(locator).toBeVisible();
  const box = await locator.boundingBox();
  expect(box).not.toBeNull();
  return box;
}

async function boxesOf(locator, count) {
  await expect(locator).toHaveCount(count);
  return locator.evaluateAll((nodes) => nodes.map((node) => {
    const { x, y, width, height } = node.getBoundingClientRect();
    return { x, y, width, height };
  }));
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

function expectHorizontalGap(left, right, expected) {
  expectNear(right.x - left.x - left.width, expected);
}

function expectVerticalGap(upper, lower, expected) {
  expectNear(lower.y - upper.y - upper.height, expected);
}

function expectAlignedTop(boxes) {
  boxes.forEach((box) => expectNear(box.y, boxes[0].y));
}

async function expectCardSurface(locator) {
  await expectStyles(locator, {
    backgroundColor: DEMO.card,
    borderLeftColor: DEMO.line,
    borderLeftStyle: "solid",
    borderLeftWidth: "1px",
    borderRadius: "10px",
  });
}

async function expectDynamicSurfaces(cards) {
  for (let index = 0; index < 3; index += 1) {
    await expectCardSurface(cards.nth(index));
    await expectStyles(cards.nth(index), { padding: "18px 20px" });
  }
}

async function expectDesktopHeader(page) {
  const header = page.getByRole("banner");
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

async function expectMainFrame(page, width) {
  const main = page.locator("#main-content");
  const box = await boxOf(main);
  expectNear(box.width, Math.min(width, 1200));
  expectNear(box.x, (width - box.width) / 2);
  await expectStyles(main, {
    padding: "24px 20px 40px",
  });
  await expectStyles(page.locator(".home-page"), {
    backgroundColor: DEMO.background,
    color: DEMO.ink,
  });
}

async function expectDesktopDynamics(page) {
  const region = page.getByRole("region", { name: "平台动态" });
  const cards = region.getByRole("article");
  const boxes = await boxesOf(cards, 3);
  expectAlignedTop(boxes);
  boxes.forEach((box) => expectNear(box.height, boxes[0].height));
  expectHorizontalGap(boxes[0], boxes[1], 14);
  expectHorizontalGap(boxes[1], boxes[2], 14);
  expectNear(boxes[0].width / boxes[2].width, 1.1, 0.01);
  expectNear(boxes[1].width / boxes[2].width, 1.2, 0.01);
  await expectDynamicSurfaces(cards);
}

async function expectDesktopRecommendations(page) {
  const dynamics = page.getByRole("region", { name: "平台动态" }).getByRole("article").first();
  const recommendation = page.getByRole("region", { name: "推荐案例" });
  const materials = page.getByRole("region", { name: "推荐素材" });
  const [dynamicBox, recommendationBox, materialBox] = await Promise.all([
    boxOf(dynamics), boxOf(recommendation), boxOf(materials),
  ]);
  expectAlignedTop([recommendationBox, materialBox]);
  expectHorizontalGap(recommendationBox, materialBox, 18);
  expectNear(recommendationBox.width / materialBox.width, 2, 0.01);
  expectVerticalGap(dynamicBox, recommendationBox, 18);
  await expectCardSurface(recommendation);
  await expectCardSurface(materials);
  await expect(page.getByRole("link", { name: "检索全部" })).toHaveCSS("color", DEMO.brand);
}

async function expectMobileHeader(page) {
  const header = page.getByRole("banner");
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

async function expectMobileMain(page) {
  const main = page.locator("#main-content");
  const box = await boxOf(main);
  expectNear(box.x, 0);
  expectNear(box.width, 390);
  await expectStyles(main, { padding: "24px 20px 40px" });
  await expectStyles(page.locator(".home-page"), {
    backgroundColor: DEMO.background,
    color: DEMO.ink,
  });
}

async function expectMobileDynamics(page) {
  const cards = page.getByRole("region", { name: "平台动态" }).getByRole("article");
  const boxes = await boxesOf(cards, 3);
  boxes.forEach((box) => expectNear(box.x, 20));
  boxes.forEach((box) => expectNear(box.width, 350));
  expectVerticalGap(boxes[0], boxes[1], 14);
  expectVerticalGap(boxes[1], boxes[2], 14);
  await expectDynamicSurfaces(cards);
}

async function expectMobileRecommendations(page) {
  const dynamics = page.getByRole("region", { name: "平台动态" }).getByRole("article");
  const recommendation = page.getByRole("region", { name: "推荐案例" });
  const materials = page.getByRole("region", { name: "推荐素材" });
  const boxes = await Promise.all([
    boxOf(dynamics.nth(2)), boxOf(recommendation), boxOf(materials),
  ]);
  boxes.slice(1).forEach((box) => expectNear(box.x, 20));
  boxes.slice(1).forEach((box) => expectNear(box.width, 350));
  expectVerticalGap(boxes[0], boxes[1], 18);
  expectVerticalGap(boxes[1], boxes[2], 18);
  await expectCardSurface(recommendation);
  await expectCardSurface(materials);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
}

for (const width of [1600, 1024]) {
  test(`${width}px 首页延续 demo-v2.1-final 的桌面视觉与 2:1 布局`, async ({ page }) => {
    await openHome(page, width, 1000);
    await expectDesktopHeader(page);
    await expectMainFrame(page, width);
    await expectDesktopDynamics(page);
    await expectDesktopRecommendations(page);
  });
}

test("390px 首页按旧 demo 折为两行头部和单列内容", async ({ page }) => {
  await openHome(page, 390, 844);
  await expectMobileHeader(page);
  await expectMobileMain(page);
  await expectMobileDynamics(page);
  await expectMobileRecommendations(page);
});

test("首页、登录、详情、工作台和管理后台使用统一品牌", async ({ page }) => {
  await expectLoginBrand(page);
  await expectHomeBrand(page);
  await expectCaseDetailBrand(page);
  await expectPrivateRouteBrand(page);
});

test("工作台和管理导入页共享暖纸红全局主题", async ({ page }) => {
  await loginAsAdmin(page);
  await page.goto("/#/workbench/c-02");
  await expectStyles(page.locator(".workbench-page"), { backgroundColor: DEMO.background });
  await expectStyles(page.locator(".site-header"), {
    backgroundColor: DEMO.header, borderBottomColor: DEMO.line,
  });
  await page.goto("/#/admin/material-imports");
  await expectStyles(page.locator(".admin-page"), { backgroundColor: DEMO.background });
  await expect(page.locator(".material-import-form")).toHaveCSS("border-top-color", DEMO.line);
  await expect(page.locator(".material-import-submit")).toHaveCSS("background-color", DEMO.brand);
  const active = page.getByRole("link", { name: "管理后台", exact: true });
  await expect(active).toHaveCSS("border-radius", "999px");
  await expect(active).toHaveCSS("background-color", "rgb(248, 238, 237)");
});
