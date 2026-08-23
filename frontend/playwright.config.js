import { defineConfig, devices } from "@playwright/test";

function isolatedBaseUrl() {
  const value = process.env.PLAYWRIGHT_BASE_URL;
  if (!value || new URL(value).hostname !== "frontend") {
    throw new Error("Playwright E2E 只能连接 Docker 隔离前端");
  }
  return value;
}

export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: "line",
  use: {
    baseURL: isolatedBaseUrl(),
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    ...devices["Desktop Chrome"],
  },
});
