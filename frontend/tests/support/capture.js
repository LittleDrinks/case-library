import { expect } from "@playwright/test";

export async function capture(page, testInfo, name) {
  await expect(page.locator(".toast")).toHaveCount(0, { timeout: 4000 });
  await page.screenshot({
    path: testInfo.outputPath(`${name}-${testInfo.project.name}.png`),
    fullPage: true,
  });
}
