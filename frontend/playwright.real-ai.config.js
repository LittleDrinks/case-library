import { defineConfig, devices } from "@playwright/test";

const baseURL = process.env.PLAYWRIGHT_BASE_URL;
if (!baseURL || new URL(baseURL).hostname !== "frontend") {
  throw new Error("真实 AI E2E 只能连接隔离 Compose 前端");
}

export default defineConfig({
  testDir: "./tests/e2e",
  testMatch: "real-ai-account-flow.spec.js",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 180_000,
  expect: { timeout: 15_000 },
  outputDir: "test-results/playwright",
  reporter: [["./tests/e2e/real-ai-safe-reporter.js"]],
  use: {
    baseURL,
    trace: "off",
    screenshot: "off",
    video: "off",
    ...devices["Desktop Chrome"],
  },
});
