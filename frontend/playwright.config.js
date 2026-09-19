import { defineConfig, devices } from "@playwright/test";
import { cucumberReporter, defineBddConfig } from "playwright-bdd";

function isolatedBaseUrl() {
  const value = process.env.PLAYWRIGHT_BASE_URL;
  const host = value && new URL(value).hostname;
  if (!value || !["frontend", "agent-gateway", "agent-tracer-gateway", "127.0.0.1", "localhost"].includes(host)) {
    throw new Error("Playwright E2E 只能连接 Docker 隔离服务或本机显式代理");
  }
  return value;
}

const bddTestDir = defineBddConfig({
  features: "./tests/bdd/features/**/*.feature",
  steps: "./tests/bdd/steps/**/*.js",
  outputDir: "./.features-gen",
  language: "zh-CN",
  sourceMaps: true,
});

export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: false,
  workers: 2,
  retries: 0,
  outputDir: "test-results",
  reporter: [
    ["line"],
    ["json", { outputFile: "test-results/report.json" }],
    cucumberReporter("html", {
      outputFile: "test-results/cucumber-report/index.html",
      externalAttachments: true,
    }),
    cucumberReporter("json", {
      outputFile: "test-results/cucumber-report/report.json",
    }),
  ],
  use: {
    baseURL: isolatedBaseUrl(),
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    ...devices["Desktop Chrome"],
  },
  projects: [
    { name: "generic", testIgnore: "**/agent-*.spec.js" },
    { name: "bdd", testDir: bddTestDir, fullyParallel: false, workers: 1 },
    { name: "agent", testMatch: ["**/agent-chat.spec.js", "**/agent-threads.spec.js", "**/agent-source-proof.spec.js"] },
    { name: "agent-tracer", testMatch: ["**/agent-tracer.spec.js", "**/agent-annotation-rounds.spec.js"] },
    { name: "sidebar", testMatch: "**/agent-sidebar.spec.js", grepInvert: /真实运行：Thinking/ },
    { name: "sidebar-tracer", testMatch: "**/agent-sidebar.spec.js", grep: /真实运行：Thinking/ },
  ],
});
