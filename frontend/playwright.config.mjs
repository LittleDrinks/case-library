/** @type {import('@playwright/test').PlaywrightTestConfig} */
export default {
  testDir: "./tests",
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: 1,
  reporter: "list",
  outputDir: process.env.PLAYWRIGHT_OUTPUT_DIR || "../agent-runs/screenshots",
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL || "http://localhost:18080",
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    video: process.env.PLAYWRIGHT_VIDEO || "on-first-retry",
  },
  projects: [
    {
      name: "chromium-desktop",
      use: {
        browserName: "chromium",
        viewport: { width: 1280, height: 720 },
        deviceScaleFactor: 1,
      },
    },
    {
      name: "chromium-mobile",
      use: {
        browserName: "chromium",
        viewport: { width: 375, height: 667 },
        deviceScaleFactor: 2,
        isMobile: true,
        hasTouch: true,
      },
    },
  ],
};
