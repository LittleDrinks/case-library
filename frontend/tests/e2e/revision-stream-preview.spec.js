import { expect, test } from "@playwright/test";

for (const terminalStatus of ["completed", "cancelled"]) {
test(`生成期间展开预览，结束状态 ${terminalStatus} 正确收敛`, async ({ page }) => {
  const original = "课前阅读材料；分组讨论";
  const replacement = "课前阅读材料，课堂围绕问题分组讨论。";
  const artifact = { id: "stream-artifact", kind: "range", status: "pending", target: { from: 1, to: original.length + 1, quote: original }, replacement, reason: "具体描述课堂活动", sources: [] };
  let complete = false;
  let releaseStream;
  const gate = new Promise((resolve) => { releaseStream = resolve; });
  const run = { id: "stream-run", status: "active", assistantMessageId: "stream-message" };
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    let body = [];
    if (path.endsWith("/events")) {
      await gate;
      await route.fulfill({ status: 204 });
      return;
    }
    if (path === "/api/auth/session") body = { user: { id: "stream-owner", role: "user", name: "验收教师" }, csrfToken: "fixture" };
    else if (path === "/api/cases/stream-case") body = {
      id: "stream-case", ownerId: "stream-owner", title: "流式建议验收", revision: 1, workflowStatus: "draft", tagIds: [], availableActions: [],
      document: { type: "doc", content: [{ type: "paragraph", content: [{ type: "text", text: original }] }] },
    };
    else if (path.endsWith("/agent/thread") || path.endsWith("/agent/threads/stream-thread")) body = {
      id: "stream-thread", eventSeq: complete ? 2 : 1, activeRun: complete ? null : run, latestRun: { ...run, status: complete ? terminalStatus : "active" },
      artifacts: complete && terminalStatus === "completed" ? [artifact] : [], writes: [], messages: [{ id: "stream-message", role: "assistant", runId: run.id, parts: [
        { type: "tool-propose_revision", state: "output-available", toolCallId: "stream-tool", input: {}, output: { artifactId: artifact.id, ...artifact.target, replacement, reason: artifact.reason, sources: [] } },
        { type: "text", text: complete ? "已提出建议。" : "正在说明修改内容…" },
      ] }],
    };
    else body = auxiliaryResponse(path);
    await route.fulfill({ json: body });
  });
  await page.setViewportSize({ width: 1600, height: 1000 });
  await page.goto("/#/workbench/stream-case");
  const card = page.getByTestId("revision-suggestion");
  await expect(card.locator(".revision-suggestion-status")).toHaveText("生成中");
  // 在浏览器逐帧采样，确保展开有中间高度且保持卡片顶部稳定。
  await card.evaluate((element) => {
    window.revisionFrames = [];
    const start = performance.now();
    function sample() {
      const rect = element.getBoundingClientRect();
      window.revisionFrames.push({ height: rect.height, y: rect.y });
      if (performance.now() - start < 400) requestAnimationFrame(sample);
    }
    requestAnimationFrame(sample);
    element.querySelector(".revision-suggestion-head").click();
  });
  await expect(page.locator(".revision-preview-new")).toHaveText(replacement);
  await expect(card.getByTestId("agent-accept")).toBeDisabled();
  await expect.poll(() => page.evaluate(() => window.revisionFrames.length)).toBeGreaterThan(8);
  const frames = await page.evaluate(() => window.revisionFrames);
  expect(new Set(frames.map((frame) => Math.round(frame.height))).size).toBeGreaterThan(3);
  expect(Math.max(...frames.map((frame) => frame.y)) - Math.min(...frames.map((frame) => frame.y))).toBeLessThan(2);
  complete = true;
  releaseStream();
  if (terminalStatus === "completed") {
    await expect(card.locator(".revision-suggestion-status")).toHaveText("待确认");
    await expect(card.getByTestId("agent-accept")).toBeEnabled();
    await expect(card).toHaveClass(/expanded/);
  } else {
    await expect(card).toHaveCount(0);
    await expect(page.locator(".revision-preview-new")).toHaveCount(0);
  }
});
}

function auxiliaryResponse(path) {
  if (path.endsWith("/sources")) return { entries: [] };
  if (path.endsWith("/history")) return { versions: [], events: [] };
  if (path === "/api/ai/settings") return { configured: true };
  return [];
}
