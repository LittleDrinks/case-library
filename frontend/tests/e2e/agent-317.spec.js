import { expect, test } from "@playwright/test";

const CASE_ID = "case-317-browser";
const THREAD_ID = "thread-317-browser";
const RUN_ID = "run-317-browser";
const USER_MESSAGE_ID = "message-317-user";
const ASSISTANT_MESSAGE_ID = "message-317-assistant";
const REASON_ERROR = "修订必须给出具体修改理由，且不能为空白";
const OVERLAP_ERROR = "同一轮的多个修订目标不能重叠";
const RETRY_SUFFIX = "\n\nFix the errors and try again.";

function completedSnapshot() {
  const startedAt = "2026-09-26T00:00:00.000Z";
  const run = {
    id: RUN_ID,
    status: "completed",
    userMessageId: USER_MESSAGE_ID,
    assistantMessageId: ASSISTANT_MESSAGE_ID,
    startedAt,
    finishedAt: "2026-09-26T00:00:02.000Z",
  };
  return {
    id: THREAD_ID,
    title: "浏览器状态夹具",
    eventSeq: 4,
    messages: [
      {
        id: USER_MESSAGE_ID,
        runId: RUN_ID,
        role: "user",
        metadata: {},
        parts: [{ type: "text", text: "请生成修订建议" }],
      },
      {
        id: ASSISTANT_MESSAGE_ID,
        runId: RUN_ID,
        role: "assistant",
        metadata: {},
        parts: [{ type: "text", text: "本轮已结束" }],
      },
    ],
    runs: [run],
    latestRun: run,
    activeRun: null,
    artifacts: [],
    writes: [],
  };
}

function staleActiveSnapshot() {
  const snapshot = completedSnapshot();
  const run = { ...snapshot.latestRun, status: "active", finishedAt: null };
  return {
    ...snapshot,
    eventSeq: 2,
    messages: [snapshot.messages[0]],
    runs: [run],
    latestRun: run,
    activeRun: run,
  };
}

function failedSnapshot() {
  const snapshot = completedSnapshot();
  const run = { ...snapshot.latestRun, status: "failed" };
  snapshot.messages = [{
    ...snapshot.messages[0],
    parts: [{ type: "text", text: "当前失败消息" }],
  }];
  snapshot.runs = [run];
  snapshot.latestRun = run;
  return snapshot;
}

function staleRetrySnapshot() {
  const snapshot = failedSnapshot();
  const run = { ...snapshot.latestRun, status: "active", finishedAt: null };
  snapshot.eventSeq = 2;
  snapshot.messages = [{
    ...snapshot.messages[0],
    parts: [{ type: "text", text: "旧版陈旧消息" }],
  }];
  snapshot.runs = [run];
  snapshot.latestRun = run;
  snapshot.activeRun = run;
  return snapshot;
}

function revisionFailureSnapshot(errorText = `${REASON_ERROR}${RETRY_SUFFIX}`) {
  const snapshot = completedSnapshot();
  snapshot.messages[1].parts = [{
    type: "tool-propose_revision",
    toolCallId: "tool-call-317",
    state: "output-error",
    input: { start: 1, end: 8, replacement: "修订后的文字" },
    errorText,
  }];
  return snapshot;
}

function directWriteSnapshot() {
  const snapshot = completedSnapshot();
  snapshot.messages[1].parts = [{
    type: "tool-write_document",
    toolCallId: "tool-call-write-317",
    state: "output-available",
    input: { scope: "document" },
    output: { status: "written", id: "write-317" },
  }];
  return snapshot;
}

async function mountPanel(page, snapshotForThread, onStreamRequest = () => {}) {
  const readSnapshot = typeof snapshotForThread === "function"
    ? snapshotForThread : () => structuredClone(snapshotForThread);
  await page.route("**/agent-317-component", (route) => route.fulfill({
    contentType: "text/html",
    body: "<!doctype html><html><body><div id=\"test-root\"></div></body></html>",
  }));
  await page.route("**/api/**", async (route) => {
    const { pathname } = new URL(route.request().url());
    if (pathname === `/api/cases/${CASE_ID}/agent/thread`) {
      await route.fulfill({ json: await readSnapshot() });
    } else if (pathname === `/api/cases/${CASE_ID}/agent/threads/${THREAD_ID}`) {
      await route.fulfill({ json: await readSnapshot() });
    } else if (pathname === "/api/ai/settings") {
      await route.fulfill({ json: { configured: true, model: "fixture" } });
    } else if (pathname === "/api/skills") {
      await route.fulfill({ json: [] });
    } else if (pathname === `/api/cases/${CASE_ID}/agent/thread/${THREAD_ID}/stream`) {
      onStreamRequest(route.request().postDataJSON());
      await route.fulfill({ status: 503, json: { detail: "deterministic browser fixture" } });
    } else {
      await route.fulfill({ status: 404, json: { detail: "not found" } });
    }
  });

  await page.goto("/agent-317-component");
  await page.evaluate(async () => {
    const [
      { createApp, h, provide, reactive },
      { default: AgentChatPanel },
      { CONVERSATION_SOURCES_KEY, createConversationSources },
    ] = await Promise.all([
      import("/node_modules/.vite/deps/vue.js"),
      import("/src/components/AgentChatPanel.vue"),
      import("/src/composables/useConversationSources.js"),
    ]);
    const caseRecord = reactive({
      id: "case-317-browser",
      revision: 1,
      title: "浏览器状态夹具",
      ownerId: "user-317",
      workflowStatus: "draft",
      document: { type: "doc", content: [{ type: "paragraph", content: [] }] },
    });
    const app = createApp({
      setup() {
        provide(CONVERSATION_SOURCES_KEY, createConversationSources());
        return () => h(AgentChatPanel, { caseRecord, open: true });
      },
    });
    app.mount("#test-root");
    window.bumpCaseRevision = () => { caseRecord.revision += 1; };
  });
  await expect(page.locator(".agent-chat-panel")).toBeVisible();
}

test("late refresh snapshots cannot unfreeze a completed run timer", async ({ page }) => {
  let threadReads = 0;
  await mountPanel(page, () => {
    threadReads += 1;
    return threadReads === 1 ? completedSnapshot() : staleActiveSnapshot();
  });

  const panel = page.locator(".agent-chat-panel");
  const status = page.locator(".ai-status");
  await expect(panel).toHaveAttribute("data-event-seq", "4");
  await expect(panel).toHaveAttribute("data-run-status", "completed");
  await expect(status).toContainText("耗时 2.0s");

  await page.evaluate(() => window.bumpCaseRevision());
  await expect.poll(() => threadReads).toBe(2);
  await expect(panel).toHaveAttribute("data-event-seq", "4");
  await expect(panel).toHaveAttribute("data-run-status", "completed");
  await page.waitForTimeout(1200);
  await expect(status).toContainText("耗时 2.0s");
});

test("retry rebuild keeps the newest message when its snapshot response is stale", async ({ page }) => {
  let threadReads = 0;
  let submitted;
  await mountPanel(page, () => {
    threadReads += 1;
    return threadReads === 1 ? failedSnapshot() : staleRetrySnapshot();
  }, (request) => { submitted = request; });

  await page.getByTestId("agent-retry").click();
  await expect.poll(() => submitted).toBeDefined();
  const submittedText = submitted.messages
    .flatMap((message) => message.parts || [])
    .filter((part) => part.type === "text")
    .map((part) => part.text)
    .join("\n");
  expect(submittedText).toContain("当前失败消息");
  expect(submittedText).not.toContain("旧版陈旧消息");
});

test("revision tool validation gives its domain reason and keeps the diagnostic", async ({ page }) => {
  await mountPanel(page, revisionFailureSnapshot());

  const trace = page.locator('[data-testid="agent-tool-trace"]');
  await expect(trace).toBeVisible();
  await trace.locator("summary").first().click();
  const alert = trace.getByRole("alert");
  await expect(alert).toContainText(REASON_ERROR);
  await expect(alert).toContainText("本轮已结束，可重试这条消息");
  await expect(alert).not.toContainText("请补充具体修改理由");

  const log = trace.getByTestId("agent-tool-log");
  await expect(log).toBeVisible();
  await log.locator("summary").click();
  await expect(log.locator("pre")).toHaveText(`${REASON_ERROR}${RETRY_SUFFIX}`);
});

test("overlapping revision targets show their tool error reason and keep the diagnostic", async ({ page }) => {
  await mountPanel(page, revisionFailureSnapshot(`${OVERLAP_ERROR}${RETRY_SUFFIX}`));

  const trace = page.locator('[data-testid="agent-tool-trace"]');
  await expect(trace).toBeVisible();
  await trace.locator("summary").first().click();
  const alert = trace.getByRole("alert");
  await expect(alert).toContainText(OVERLAP_ERROR);
  await expect(alert).toContainText("本轮已结束，可重试这条消息");

  const log = trace.getByTestId("agent-tool-log");
  await expect(log).toBeVisible();
  await log.locator("summary").click();
  await expect(log.locator("pre")).toHaveText(`${OVERLAP_ERROR}${RETRY_SUFFIX}`);
});

test("successful document writes show a concrete state consistent with the result", async ({ page }) => {
  await mountPanel(page, directWriteSnapshot());

  const trace = page.locator('[data-testid="agent-tool-trace"]');
  await expect(trace).toBeVisible();
  const summary = trace.locator("summary").first();
  await expect(summary).toContainText("直接写入正文 · 已写入");
  await expect(summary).not.toContainText("结果状态未知");
  await summary.click();
  await expect(trace.locator(".agent-tool-line").last()).toHaveText("已写入正文，可撤销");
});
