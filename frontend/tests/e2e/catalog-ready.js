import { expect } from "@playwright/test";

export async function waitForCatalogSynced(request, query = "", timeout = 30_000) {
  let status;
  const deadline = Date.now() + timeout;
  await expect.poll(async () => {
    const response = await request.get("/api/search", {
      params: { q: query, kind: "all", pageSize: 20 },
      timeout: Math.max(1, deadline - Date.now()),
    });
    status = response.status();
    return status;
  }, { message: "等待检索目录同步完成", timeout, intervals: [500, 1_000, 2_000] }).not.toBe(503);
  expect(status, "检索接口返回非同步错误").toBe(200);
}

export async function openCatalogFirstScreen(page, url, assertReady) {
  await waitForCatalogSynced(page.context().request);
  await page.goto(url);
  await assertReady();
}
