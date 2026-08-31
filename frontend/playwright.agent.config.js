import { defineConfig, devices } from "@playwright/test";

function isolatedBaseUrl() {
  const value = process.env.PLAYWRIGHT_BASE_URL;
  if (!value || new URL(value).hostname !== "agent-gateway") {
    throw new Error("Agent E2E 只能连接隔离网关");
  }
  return value;
}

export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  outputDir: "test-results",
  reporter: [["line"], ["json", { outputFile: "test-results/report.json" }]],
  testMatch: "**/agent-chat.spec.js",
  use: {
    baseURL: isolatedBaseUrl(),
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    ...devices["Desktop Chrome"],
  },
});
