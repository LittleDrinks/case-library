import { expect } from "@playwright/test";

export async function openAiTab(page) {
  const rail = page.locator(".assistant-rail");
  const tab = rail.getByRole("button", { name: "AI", exact: true });
  await expect(tab).toBeVisible();
  const shouldOpen = await rail.evaluate((node) => (
    node.classList.contains("collapsed")
    || (matchMedia("(max-width: 800px)").matches && !node.classList.contains("open"))
    || node.querySelector('[aria-label="AI"]').getAttribute("aria-pressed") !== "true"
  ));
  if (shouldOpen) await tab.click();
  await expect(tab).toHaveAttribute("aria-pressed", "true");
}
