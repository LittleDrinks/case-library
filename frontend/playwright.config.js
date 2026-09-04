import { defineConfig, devices } from "@playwright/test";

function isolatedBaseUrl() {
  const value = process.env.PLAYWRIGHT_BASE_URL;
  const host = value && new URL(value).hostname;
  if (!value || !["frontend", "agent-gateway", "agent-tracer-gateway"].includes(host)) {
    throw new Error("Playwright E2E 只能连接 Docker 隔离服务");
  }
  return value;
}

export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: false,
  workers: 2,
  retries: 0,
  outputDir: "test-results",
  reporter: [["line"], ["json", { outputFile: "test-results/report.json" }]],
  use: {
    baseURL: isolatedBaseUrl(),
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    ...devices["Desktop Chrome"],
  },
  projects: [
    { name: "generic", testIgnore: "**/agent-*.spec.js" },
    { name: "agent", testMatch: ["**/agent-chat.spec.js", "**/agent-threads.spec.js"] },
    { name: "agent-tracer", testMatch: "**/agent-tracer.spec.js" },
  ],
});
