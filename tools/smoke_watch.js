#!/usr/bin/env node
// WP5 自动盯源 + 众筹冒烟：加载真实 app/seed.js + app/data.js + app/js/util.js + app/js/store.js，
// 打真实服务端（默认 http://127.0.0.1:18077）。覆盖：盯源 CRUD、手动扫描（本地静态页模拟源，
// AI 条目抽取）、URL+指纹去重、候选卡入库（多方验证附注）→ 候选 → admin 确认 → 可检索、忽略、
// 三种贡献提交→先审后发（kn_link 通过后体现在 recommendFor）、/api/my/impact 聚合。
// 需要服务端 AI 已配置（条目抽取依赖 /api/ai/chat 同源的 llm_call）。
// 用法：node tools/smoke_watch.js [baseUrl]
"use strict";
const fs = require("fs");
const path = require("path");
const { spawn } = require("child_process");

const ROOT = path.join(__dirname, "..");
const BASE = process.argv[2] || "http://127.0.0.1:18077";
const SRC_PORT = 18099; // 本地静态页模拟盯源栏目
const SRC_DIR = "/tmp/smoke_watch_src";
const RUN = String(Date.now());

// ------------------------------------------------------------ 浏览器环境垫片
const mem = {};
global.localStorage = {
  getItem: (k) => (k in mem ? mem[k] : null),
  setItem: (k, v) => { mem[k] = String(v); },
  removeItem: (k) => { delete mem[k]; },
};
global.window = global;
global.location = { hash: "" };
const rawFetch = global.fetch;
global.fetch = (url, opts) => rawFetch(String(url).startsWith("/") ? BASE + url : url, opts);

for (const f of ["app/seed.js", "app/data.js", "app/js/util.js", "app/js/store.js"]) {
  eval(fs.readFileSync(path.join(ROOT, f), "utf-8"));
}
window.U.toast = () => {};
const Store = window.Store;

let pass = 0, fail = 0;
function ok(cond, name, extra) {
  if (cond) { pass++; console.log("PASS  " + name); }
  else { fail++; console.log("FAIL  " + name + (extra ? "  -> " + extra : "")); }
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// ------------------------------------------------------------ 本地静态页模拟源
let srcServer = null;
async function ensureSrcServer() {
  fs.mkdirSync(SRC_DIR, { recursive: true });
  fs.writeFileSync(path.join(SRC_DIR, "index.html"), `<!DOCTYPE html><html><head><meta charset="utf-8"><title>冒烟栏目</title></head><body><ul>
<li><a href="/a1-${RUN}.html">高校思政课改革创新推进会召开 冒烟${RUN}</a></li>
<li><a href="/a2-${RUN}.html">人工智能赋能高校教育教学改革观察 冒烟${RUN}</a></li>
<li><a href="/a3-${RUN}.html">科学家精神融入课程思政的实践路径研究 冒烟${RUN}</a></li>
<li><a href="/a4-${RUN}.html">科学家精神融入课程思政实践路径探析 冒烟${RUN}</a></li>
<li><a href="/nav">首页</a></li>
</ul></body></html>`);
  const up = await rawFetch(`http://127.0.0.1:${SRC_PORT}/index.html`)
    .then((r) => r.ok).catch(() => false);
  if (up) return; // 上一轮遗留的静态服务直接复用（按请求读文件，内容已更新）
  srcServer = spawn("/usr/bin/python3", ["-m", "http.server", String(SRC_PORT), "--directory", SRC_DIR],
    { stdio: "ignore" });
  for (let i = 0; i < 30; i++) {
    await sleep(300);
    const ok2 = await rawFetch(`http://127.0.0.1:${SRC_PORT}/index.html`)
      .then((r) => r.ok).catch(() => false);
    if (ok2) return;
  }
  throw new Error("本地静态源启动失败");
}

function cleanup() {
  if (srcServer) { try { srcServer.kill(); } catch (e) { /* ignore */ } }
}
process.on("exit", cleanup);

// 直接打 API 的小助手（带当前登录 token）
async function api(method, p, body) {
  const resp = await fetch(BASE + p, {
    method,
    headers: Object.assign({ "Content-Type": "application/json" }, Store.authHeaders()),
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  let d = null;
  try { d = await resp.json(); } catch (e) { /* ignore */ }
  return { status: resp.status, d };
}

async function main() {
  const constants = await fetch(BASE + "/api/constants").then((r) => r.json()).catch(() => null);
  ok(constants && constants.ok, "服务可达 " + BASE);
  if (!constants || !constants.ok) process.exit(1);
  ok(constants.aiConfigured, "服务端 AI 已配置（盯源条目抽取依赖）");
  if (!constants.aiConfigured) { console.log("\n%d PASS, %d FAIL", pass, fail + 1); process.exit(1); }
  await ensureSrcServer();

  // 0. 权限：非 admin 不能管盯源 / 审贡献
  await Store.login("u-chen");
  Store.setUser("u-chen");
  let r = await api("GET", "/api/admin/watch/sources");
  ok(r.status === 403, "非 admin 访问盯源管理被拒（403）", String(r.status));

  // 1. 盯源 CRUD（admin）
  await Store.login("u-admin");
  Store.setUser("u-admin");
  const srcUrl = `http://127.0.0.1:${SRC_PORT}/index.html`;
  r = await api("POST", "/api/admin/watch/sources",
    { name: "冒烟演示源", url: srcUrl, keywords: ["思政", "教育", "科学家精神"] });
  ok(r.status === 200 && r.d.ok && r.d.source.id, "创建盯源", JSON.stringify(r.d));
  const sid = r.d && r.d.source && r.d.source.id;
  r = await api("POST", "/api/admin/watch/sources", { name: "重复", url: srcUrl });
  ok(r.status === 400, "同 URL 盯源创建被拒", String(r.status));
  r = await api("PATCH", "/api/admin/watch/sources/" + sid, { keywords: ["思政"], enabled: false });
  ok(r.status === 200 && r.d.source.enabled === false && r.d.source.keywords.join() === "思政",
    "PATCH 盯源（关键词 + 停用）", JSON.stringify(r.d && r.d.source));
  r = await api("PATCH", "/api/admin/watch/sources/" + sid, { enabled: true });
  ok(r.status === 200 && r.d.source.enabled === true, "PATCH 盯源（重新启用）");
  r = await api("GET", "/api/admin/watch/sources");
  ok(r.d.sources.some((s) => s.id === sid), "盯源列表含新源");

  // 2. 手动触发扫描 → AI 抽取候选卡；重复扫描去重
  r = await api("POST", "/api/admin/watch/run", { sourceId: sid });
  const added = r.d && r.d.added;
  ok(r.status === 200 && r.d.ok && added >= 3, "手动扫描产生候选卡（AI 抽取）",
    JSON.stringify(r.d && r.d.results));
  r = await api("GET", "/api/admin/watch/sources");
  const srcNow = r.d.sources.find((s) => s.id === sid);
  ok(srcNow && srcNow.lastRunAt && srcNow.lastItemCount === added,
    "源记录上次运行时间与新增条数", JSON.stringify(srcNow));
  r = await api("POST", "/api/admin/watch/run", { sourceId: sid });
  ok(r.d.ok && r.d.added === 0 && r.d.results[0].note === "本次无新增",
    "重复扫描不产生重复（URL+指纹去重）", JSON.stringify(r.d && r.d.results));

  r = await api("GET", "/api/admin/watch/items?status=" + encodeURIComponent("待审"));
  const pend = (r.d.items || []).filter((x) => x.sourceId === sid);
  ok(pend.length === added && pend.every((x) => x.url.includes(RUN) && x.status === "待审"),
    "待审候选卡落库且归属演示源", pend.map((x) => x.title).join(" | "));
  const it3 = pend.find((x) => x.url.includes("/a3-"));
  const it4 = pend.find((x) => x.url.includes("/a4-"));

  // 3. 候选卡入库（同事件多方验证附注）→ 素材候选 → admin 确认 → 可检索
  // AI 抽取有取舍（4 条候选一般抽 3-4 条），断言自适应：a3/a4 相似对都在才验多方验证
  const importItem = it3 || pend[0];
  const ignoreItem = pend.find((x) => x.id !== importItem.id && (!it3 || x.id !== it4.id));
  r = await api("POST", `/api/admin/watch/items/${importItem.id}/import`, { grade: "X" });
  ok(r.status === 400, "入库 grade 取值校验（X → 400）", String(r.status));
  r = await api("POST", `/api/admin/watch/items/${importItem.id}/import`, { grade: "B" });
  ok(r.status === 200 && r.d.ok && r.d.material.status === "候选" && r.d.material.grade === "B",
    "候选卡入库 → 素材「候选」（默认 B 级）", JSON.stringify(r.d && r.d.error));
  const impMat = r.d.material;
  ok(!(it3 && it4) || /多方验证/.test(impMat.summary),
    "同事件其余报道作「多方验证」附注写入摘要" + (it3 && it4 ? "" : "（本轮 AI 未同时抽到相似对，跳过）"),
    impMat.summary);
  r = await api("POST", `/api/admin/watch/items/${importItem.id}/import`, { grade: "B" });
  ok(r.status === 409, "重复入库被拒（409）", String(r.status));
  await Store.syncMaterials();
  ok(await Store.batchUpdateMaterials([impMat.id], { status: "正常" }), "admin 批量确认候选入库");
  const sr = await Store.search(impMat.title.slice(0, 10), { kind: "materials" });
  ok(sr.materials.some((e) => e.item.id === impMat.id), "确认后检索命中入库素材");
  r = await api("PATCH", `/api/admin/watch/items/${ignoreItem.id}`, { status: "已忽略" });
  ok(r.status === 200 && r.d.item.status === "已忽略", "候选卡忽略");
  r = await api("GET", "/api/admin/watch/items?status=" + encodeURIComponent("待审"));
  ok(!r.d.items.some((x) => x.id === ignoreItem.id), "忽略后不再出现在待审列表");

  // 4. 众筹贡献：link / kn_link 提交 → 待审 → admin 通过/驳回
  await Store.login("u-chen");
  Store.setUser("u-chen");
  const cbUrl1 = "http://example.com/cb1-" + RUN + ".html";
  r = await api("POST", "/api/contributions", {
    kind: "link",
    payload: { url: cbUrl1, title: "冒烟贡献：课程思政示范课建设经验 " + RUN, summary: "示范课建设经验", grade: "B" },
  });
  ok(r.status === 200 && r.d.contribution.status === "待审", "贡献 a：素材链接提交 → 待审");
  const cbLink = r.d.contribution;
  r = await api("POST", "/api/contributions", {
    kind: "link", payload: { url: impMat.sourceUrl, title: "重复链接" },
  });
  ok(r.status === 409 && r.d.code === "dup", "贡献链接 URL 查重（已在库 → 409）", String(r.status));
  r = await api("POST", "/api/contributions", {
    kind: "link", payload: { url: "not-a-url", title: "坏链接" },
  });
  ok(r.status === 400, "贡献链接格式校验（400）", String(r.status));
  const cbUrl2 = "http://example.com/cb2-" + RUN + ".html";
  r = await api("POST", "/api/contributions", {
    kind: "link", payload: { url: cbUrl2, title: "冒烟贡献：待驳回 " + RUN },
  });
  const cbReject = r.d.contribution;

  // 挑一个全库无人引用的 kn 节（避免共引打分干扰），做 kn_link 关联
  await Store.login("u-admin");
  Store.setUser("u-admin");
  await Store.syncCases();
  const citedKn = new Set();
  Store.db.cases.forEach((c) => (c.citations || []).forEach((ref) => {
    const t = typeof ref === "string" ? ref : ref.target;
    if (t && t.startsWith("kn-")) citedKn.add(t);
  }));
  const freeKn = (Store.db.knowledge.find((k) => !citedKn.has(k.id)) || {}).id;
  ok(!!freeKn, "存在未被引用的教材节供 kn_link 验证", String(freeKn));
  const linkMatId = "m-kcsz"; // 任意正常素材：该 kn 无人引用，通过前不应被推荐
  await Store.login("u-chen");
  Store.setUser("u-chen");
  r = await api("POST", "/api/contributions", {
    kind: "kn_link", payload: { knId: freeKn, materialId: linkMatId },
  });
  ok(r.status === 200 && r.d.contribution.status === "待审", "贡献 b：知识点-素材关联提交 → 待审");
  const cbKn = r.d.contribution;
  r = await api("POST", "/api/contributions", {
    kind: "kn_link", payload: { knId: "kn-99-99", materialId: linkMatId },
  });
  ok(r.status === 400, "kn_link 知识点存在性校验（400）", String(r.status));

  // 验证 kn_link 通过前后 recommendFor 差异
  const probe = await Store.addCase({
    title: "kn_link 推荐验证案例 " + RUN, typeId: "ct-general", audience: "ug",
    blocks: [{ kind: "p", text: "验证用" }],
    citations: [{ target: freeKn, quote: "知识点" }],
  });
  const recBefore = await Store.recommendedMaterials(probe.id);
  ok(!recBefore.some((m) => m.id === linkMatId),
    "kn_link 通过前 recommendFor 不含关联素材", recBefore.map((m) => m.id).slice(0, 5).join(","));

  // 本人仅见自己的贡献；非 admin 审核被拒
  r = await api("GET", "/api/contributions");
  ok(r.d.contributions.length >= 3 && r.d.contributions.every((c) => c.userId === "u-chen"),
    "仅本人可见自己的贡献列表");
  r = await api("POST", `/api/contributions/${cbLink.id}/review`, { action: "approve" });
  ok(r.status === 403, "非 admin 审核贡献被拒（403）", String(r.status));

  await Store.login("u-admin");
  Store.setUser("u-admin");
  r = await api("POST", `/api/contributions/${cbLink.id}/review`, { action: "approve" });
  ok(r.status === 200 && r.d.contribution.status === "通过" && r.d.material
    && r.d.material.status === "候选" && r.d.contribution.payload.materialId === r.d.material.id,
    "admin 通过 link 贡献 → 走入库闸落素材「候选」", JSON.stringify(r.d && r.d.error));
  const contribMat = r.d.material;
  r = await api("POST", `/api/contributions/${cbKn.id}/review`, { action: "approve" });
  ok(r.status === 200 && r.d.contribution.status === "通过", "admin 通过 kn_link 贡献");
  r = await api("POST", `/api/contributions/${cbReject.id}/review`,
    { action: "reject", reason: "来源不可靠" });
  ok(r.status === 200 && r.d.contribution.status === "驳回"
    && r.d.contribution.payload.reviewNote === "来源不可靠",
    "admin 驳回贡献 → 状态驳回 + 驳回说明", JSON.stringify(r.d && r.d.contribution));
  r = await api("POST", `/api/contributions/${cbLink.id}/review`, { action: "approve" });
  ok(r.status === 409, "重复审核被拒（409）", String(r.status));

  await Store.login("u-chen");
  Store.setUser("u-chen");
  const recAfter = await Store.recommendedMaterials(probe.id);
  ok(recAfter.some((m) => m.id === linkMatId),
    "kn_link 通过后 recommendFor 体现该关联", recAfter.map((m) => m.id).slice(0, 5).join(","));
  await api("DELETE", "/api/cases/" + probe.id); // 清理验证案例

  // 5. /api/my/impact：素材贡献被引 + 案例被收藏/点赞聚合
  const impact0 = await Store.fetchMyImpact();
  ok(impact0 && typeof impact0.caseLikes === "number" && typeof impact0.materialsCited === "number",
    "impact 返回聚合字段", JSON.stringify(impact0));
  // admin 点赞 + 收藏陈静的 c-draft-1（草稿仅作者/admin 可见）
  await Store.login("u-admin");
  Store.setUser("u-admin");
  await Store.syncCases();
  const chenCase = Store.db.cases.find((c) => c.id === "c-draft-1");
  ok(await Store.likeCase(chenCase) && await Store.toggleFav(chenCase), "admin 点赞+收藏陈静案例");
  // admin 确认贡献素材入库 → 陈静在案例中引用它 → 被引计数 +1
  await Store.syncMaterials();
  ok(await Store.batchUpdateMaterials([contribMat.id], { status: "正常" }), "贡献素材确认入库");
  await Store.login("u-chen");
  Store.setUser("u-chen");
  await Store.syncMaterials();
  await Store.syncCases();
  const mine = Store.db.cases.find((c) => c.id === "c-draft-1");
  Store.cite(mine, contribMat.id);
  await sleep(2500); // 案例防抖 400ms + 服务端重算
  const impact1 = await Store.fetchMyImpact();
  ok(impact1.caseLikes === impact0.caseLikes + 1, "impact 案例被点赞 +1",
    impact0.caseLikes + "→" + impact1.caseLikes);
  ok(impact1.caseFavorites === impact0.caseFavorites + 1, "impact 案例被收藏 +1",
    impact0.caseFavorites + "→" + impact1.caseFavorites);
  ok(impact1.materialsCited === impact0.materialsCited + 1, "impact 素材贡献被引 +1",
    impact0.materialsCited + "→" + impact1.materialsCited);
  ok(impact1.contributedMaterials >= 1, "impact 已入库贡献素材计数", String(impact1.contributedMaterials));
  // 清理：撤引用、取消点赞/收藏
  Store.uncite(mine, contribMat.id);
  await sleep(2500);
  await Store.login("u-admin");
  Store.setUser("u-admin");
  await Store.syncCases();
  const chenCase2 = Store.db.cases.find((c) => c.id === "c-draft-1");
  await Store.likeCase(chenCase2);
  await Store.toggleFav(chenCase2);

  // 6. 清理：删除演示盯源 → 候选卡联动清除
  await Store.login("u-admin");
  Store.setUser("u-admin");
  r = await api("DELETE", "/api/admin/watch/sources/" + sid);
  ok(r.status === 200 && r.d.ok, "删除演示盯源");
  r = await api("GET", "/api/admin/watch/sources");
  ok(!r.d.sources.some((s) => s.id === sid), "盯源列表不再含演示源");
  r = await api("GET", "/api/admin/watch/items");
  ok(!(r.d.items || []).some((x) => x.sourceId === sid), "候选卡随源联动清除");

  console.log("\n%d PASS, %d FAIL", pass, fail);
  process.exit(fail ? 1 : 0);
}

main().catch((e) => { console.error("冒烟执行异常:", e); cleanup(); process.exit(1); });
