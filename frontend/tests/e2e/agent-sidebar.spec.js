import { expect, test } from "@playwright/test";

const CASE_ID = "c-draft-1";

async function login(page) {
  await page.goto(`/#/login?redirect=/workbench/${CASE_ID}`);
  await page.getByLabel("用户名").fill("user");
  await page.getByLabel("密码").fill("user123");
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`#\\/workbench\\/${CASE_ID}$`));
}

async function openChat(page) {
  await page.getByLabel("辅助面板").getByRole("button", { name: "对话", exact: true }).click();
  await expect(page.locator(".agent-chat-panel")).toBeVisible();
  await expect.poll(() => page.locator(".assistant-rail").evaluate((node) => node.getBoundingClientRect().height)).toBeGreaterThan(300);
}

async function layout(page) {
  return page.evaluate(() => {
    const rail = document.querySelector(".assistant-rail").getBoundingClientRect();
    const panel = document.querySelector(".agent-chat-panel");
    const conversation = document.querySelector(".ai-conversation");
    const composer = document.querySelector(".assistant-composer").getBoundingClientRect();
    return {
      railBottom: rail.bottom, viewport: innerHeight, railHeight: rail.height,
      panelOverflow: getComputedStyle(panel).overflow,
      conversationOverflow: getComputedStyle(conversation).overflowY,
      composerBottom: composer.bottom, widthOverflow: document.documentElement.scrollWidth - innerWidth,
    };
  });
}

async function assertLayout(page, screenshot) {
  const box = await layout(page);
  expect(Math.abs(box.railBottom - box.viewport)).toBeLessThanOrEqual(1);
  expect(box.railHeight).toBeGreaterThan(300);
  expect(box.panelOverflow).toBe("hidden");
  expect(box.conversationOverflow).toBe("auto");
  expect(box.composerBottom).toBeLessThanOrEqual(box.railBottom + 1);
  expect(box.widthOverflow).toBeLessThanOrEqual(1);
  await page.screenshot({ path: screenshot });
}

async function assertReducedMotion(page) {
  expect(await page.evaluate(() => matchMedia("(prefers-reduced-motion: reduce)").matches)).toBe(true);
  expect(await page.evaluate(() => {
    const details = document.createElement("details");
    details.className = "agent-reasoning streaming";
    details.innerHTML = "<summary>测试</summary>";
    document.body.append(details);
    const animation = getComputedStyle(details.querySelector("summary")).animationName;
    details.remove();
    return animation;
  })).toBe("none");
}

test("AI 侧栏固定布局、线程视图、移动端和 reduced motion", async ({ page }) => {
  test.setTimeout(60_000);
  await page.setViewportSize({ width: 1440, height: 900 });
  await login(page);
  await openChat(page);
  await assertLayout(page, "test-results/agent-sidebar-desktop.png");
  await page.getByTestId("agent-thread-list-open").click();
  await expect(page.getByTestId("agent-thread-list")).toBeVisible();
  await expect(page.locator(".agent-thread-rows")).toHaveCSS("overflow-y", "auto");
  await page.screenshot({ path: "test-results/agent-sidebar-threads.png" });
  await page.getByTestId("agent-thread-back").click();
  await page.emulateMedia({ reducedMotion: "reduce" });
  await assertReducedMotion(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.reload();
  await openChat(page);
  await assertLayout(page, "test-results/agent-sidebar-mobile.png");
});
