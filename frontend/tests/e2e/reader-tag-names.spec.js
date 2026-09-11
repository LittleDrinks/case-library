import { expect, test } from "@playwright/test";

const READER_TAGS = ["科学家精神", "爱国主义教育", "文化自信", "大思政课建设"];

async function openPublicCase(page) {
  await page.goto("/#/cases/c-02");
  await expect(page.locator("textarea.document-title")).toHaveValue(/钱伟长图书馆/);
}

async function assertRealTagNames(page) {
  const tags = page.getByLabel("案例标签");
  for (const name of READER_TAGS) await expect(tags).toContainText(name);
  await expect(tags).not.toContainText("tag-seed");
}

async function capture(page, testInfo, name) {
  await page.screenshot({ path: testInfo.outputPath(name), fullPage: false });
}

test("匿名访客公开阅读看到真实标签名称而非内部 ID", async ({ page }, testInfo) => {
  await openPublicCase(page);
  await assertRealTagNames(page);
  await capture(page, testInfo, "anonymous-reader-tags.png");
});

test("公开阅读目录加载失败展示错误与重试，不回退内部 ID", async ({ page }, testInfo) => {
  await page.route("**/api/tag-groups", (route) => route.abort());
  await openPublicCase(page);
  const tags = page.locator(".case-tags");
  await expect(tags).toContainText("标签目录加载失败");
  await expect(tags).not.toContainText("tag-seed");
  await capture(page, testInfo, "reader-catalog-failed.png");

  await page.unroute("**/api/tag-groups");
  await tags.getByRole("button", { name: "重试" }).click();
  await assertRealTagNames(page);
  await capture(page, testInfo, "reader-catalog-retry.png");
});

test("阅读页切换到工作台编辑页标签名称仍正确", async ({ page }, testInfo) => {
  await openPublicCase(page);
  await page.goto("/#/login");
  await page.getByLabel("用户名").fill("user");
  await page.getByLabel("密码").fill("user123");
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page).toHaveURL(/#\/$/);
  await page.goto("/#/workbench/c-02");
  await expect(page.locator("textarea.document-title")).toHaveValue(/钱伟长图书馆/);
  await assertRealTagNames(page);
  await expect(page.locator("textarea.document-title")).toHaveAttribute("readonly", "");
  await capture(page, testInfo, "workbench-tags.png");
});
