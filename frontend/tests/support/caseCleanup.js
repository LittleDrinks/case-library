export async function cleanupAuditCases(page, titlePrefix = "Audit案例 ") {
  const token = await page.evaluate(() => localStorage.getItem("case_library_auth_token"));
  const headers = token ? { Authorization: `Bearer ${token}` } : {};
  const response = await page.request.get("/api/cases?status=all&limit=100", { headers });
  if (!response.ok()) return;

  const payload = await response.json();
  const cases = Array.isArray(payload.data) ? payload.data : [];
  for (const item of cases.filter((c) => c.title?.startsWith(titlePrefix))) {
    await page.request.delete(`/api/cases/${item.id}`, { headers });
  }
}
