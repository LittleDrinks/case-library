import { expect, test } from "@playwright/test";

const original = "课前阅读材料，分组讨论。";
const replacement = "先阅读材料，再分组讨论。";
const documentFor = (text) => ({ type: "doc", content: [{ type: "paragraph", content: [{ type: "text", text }] }] });

test("修订卡片内应用、撤销、刷新、再次应用和再次撤销保持一致", async ({ page }) => {
  const caseRecord = { id: "revision-case", ownerId: "revision-owner", title: "修订操作验收", revision: 1,
    workflowStatus: "draft", document: documentFor(original), tagIds: [], availableActions: [] };
  const artifact = { id: "revision-artifact", kind: "range", status: "pending", threadId: "revision-thread", runId: "revision-run",
    target: { from: 1, to: original.length + 1, quote: original }, replacement, reason: "调整语序", sources: [], baseRevision: 1 };
  let write = null;
  const run = { id: "revision-run", status: "completed", assistantMessageId: "revision-message" };
  const snapshot = () => ({ id: "revision-thread", eventSeq: caseRecord.revision, artifacts: [artifact], writes: write ? [write] : [], runs: [run], latestRun: run, activeRun: null,
    messages: [{ id: "revision-message", role: "assistant", runId: run.id, parts: [
      { type: "tool-propose_revision", toolCallId: "revision-tool", state: "output-available", output: { artifactId: artifact.id } },
      { type: "text", text: "请确认修改建议。" },
    ] }] });
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    let body = [];
    if (path === "/api/auth/session") body = { user: { id: "revision-owner", role: "user", name: "验收教师" }, csrfToken: "fixture" };
    else if (path === "/api/cases/revision-case") body = caseRecord;
    else if (path.endsWith("/agent/thread") || path.endsWith("/agent/threads/revision-thread")) body = snapshot();
    else if (path.endsWith("/decision") || path.endsWith("/redo")) {
      if (path.endsWith("/redo")) expect(route.request().postDataJSON().revision).toBe(caseRecord.revision);
      caseRecord.document = documentFor(replacement);
      caseRecord.revision++;
      artifact.status = "accepted";
      artifact.writeId = "revision-write";
      write = { id: artifact.writeId, status: "written", scope: "selection", revision: caseRecord.revision };
      body = { case: caseRecord, artifact, write, applied: true,
        steps: [{ stepType: "replace", from: 1, to: original.length + 1, slice: { content: [{ type: "text", text: replacement }] } }] };
    } else if (path.endsWith("/undo")) {
      caseRecord.document = documentFor(original);
      caseRecord.revision++;
      write.status = "undone";
      body = { case: caseRecord, write };
    } else if (path.endsWith("/sources")) body = { entries: [] };
    else if (path.endsWith("/history")) body = { versions: [], events: [] };
    else if (path === "/api/ai/settings") body = { configured: true };
    await route.fulfill({ json: body });
  });
  await page.setViewportSize({ width: 1600, height: 1000 });
  await page.goto("/#/workbench/revision-case");
  const card = page.getByTestId("revision-suggestion");
  await card.locator(".revision-suggestion-head").click();
  await expect(page.locator(".revision-preview-new")).toHaveText(replacement);
  const before = await card.boundingBox();
  await card.getByTestId("agent-accept").click();
  await expect(page.locator(".ProseMirror p")).toHaveText(replacement);
  await expect(card.locator(".revision-suggestion-status")).toHaveText("已应用");
  await expect(card.getByTestId("agent-undo-revision")).toBeVisible();
  await card.getByTestId("agent-refine").click();
  await expect(page.getByTestId("composer-revision")).toBeVisible();
  await page.getByRole("button", { name: "移除微调上下文" }).click();
  await expect(card).toHaveClass(/expanded/);
  expect(Math.abs((await card.boundingBox()).y - before.y)).toBeLessThan(2);
  await card.getByTestId("agent-undo-revision").click();
  await expect(page.locator(".ProseMirror p")).toHaveText(original);
  await expect(card.locator(".revision-suggestion-status")).toHaveText("已撤销");
  await expect(card.getByTestId("agent-redo-revision")).toBeVisible();
  await page.reload();
  await expect(card.locator(".revision-suggestion-status")).toHaveText("已撤销");
  await card.locator(".revision-suggestion-head").click();
  await expect(page.locator(".revision-preview-new")).toHaveText(replacement);
  await card.getByTestId("agent-redo-revision").click();
  await expect(page.locator(".ProseMirror p")).toHaveText(replacement);
  await card.getByTestId("agent-undo-revision").click();
  await expect(page.locator(".ProseMirror p")).toHaveText(original);
  await expect(card.getByTestId("agent-redo-revision")).toBeVisible();
});
