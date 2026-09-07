import { expect } from "@playwright/test";

const SYNC_NOTICE = "检索目录正在同步";

// 目录同步窗口内 /api/search 以 503 应答；用真实检索请求有界轮询直到就绪。
export async function waitForCatalogSynced(request, query = "", timeout = 30_000) {
  await expect.poll(async () => {
    const response = await request.get("/api/search", {
      params: { q: query, kind: "all", pageSize: 20 },
    });
    return response.status();
  }, { message: "等待检索目录同步完成", timeout, intervals: [500, 1_000, 2_000] }).toBe(200);
}

// 目录就绪后优先点击同步提示内的可见重试按钮；视图没有重试按钮时整页重载。
async function recoverFromCatalogSync(page) {
  await waitForCatalogSynced(page.context().request, "", 20_000);
  const retry = page.getByRole("alert").filter({ hasText: SYNC_NOTICE })
    .getByRole("button", { name: "重试", exact: true });
  if (await retry.isVisible()) await retry.click();
  else await page.reload();
}

// 打开依赖检索目录的首屏；仅在出现明确同步提示时按有界期限恢复，随后断言首屏目标。
// toPass 自身默认 timeout=0，必须显式传重试期限；整体硬上限 45s + 最坏一次在途恢复。
export async function openCatalogFirstScreen(page, url, assertReady) {
  await page.goto(url);
  const syncing = page.getByRole("alert").filter({ hasText: SYNC_NOTICE });
  await expect(async () => {
    if (await syncing.isVisible()) await recoverFromCatalogSync(page);
    await assertReady();
  }, { message: "检索目录同步窗口结束后首屏仍未就绪" })
    .toPass({ timeout: 45_000, intervals: [500, 1_000, 2_000] });
}
