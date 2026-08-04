#!/usr/bin/env node
// WP2 素材闭环冒烟：加载真实 app/seed.js + app/data.js + app/js/util.js + app/js/store.js，
// 打真实服务端（默认 http://127.0.0.1:18077）。覆盖：素材同步、收藏、推荐、候选确认、
// 查重提示、批量操作、被引计数服务端维护。
// 用法：node tools/smoke_materials.js [baseUrl]
"use strict";
const fs = require("fs");
const path = require("path");

const ROOT = path.join(__dirname, "..");
const BASE = process.argv[2] || "http://127.0.0.1:18077";

// ------------------------------------------------------------ 浏览器环境垫片
const mem = {};
global.localStorage = {
  getItem: (k) => (k in mem ? mem[k] : null),
  setItem: (k, v) => { mem[k] = String(v); },
  removeItem: (k) => { delete mem[k]; },
};
global.window = global;
global.location = { hash: "" };
// store.js 用相对路径 fetch，node 需要绝对 URL
const rawFetch = global.fetch;
global.fetch = (url, opts) => rawFetch(String(url).startsWith("/") ? BASE + url : url, opts);

for (const f of ["app/seed.js", "app/data.js", "app/js/util.js", "app/js/store.js"]) {
  eval(fs.readFileSync(path.join(ROOT, f), "utf-8"));
}
window.U.toast = () => {}; // node 无 DOM，静默提示
const Store = window.Store;
const U = window.U;

// ------------------------------------------------------------ 测试框架
let pass = 0, fail = 0;
function ok(cond, name, extra) {
  if (cond) { pass++; console.log("PASS  " + name); }
  else { fail++; console.log("FAIL  " + name + (extra ? "  -> " + extra : "")); }
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function main() {
  // 0. 服务可达
  const constants = await fetch(BASE + "/api/constants").then((r) => r.json()).catch(() => null);
  ok(constants && constants.ok, "服务可达 " + BASE);
  if (!constants || !constants.ok) process.exit(1);

  // 1. 素材同步（admin 全量 77 条；seed 灌库）
  await Store.login("u-admin");
  await Store.syncMaterials();
  ok(Store.db.materials.length === 77, "素材 seed 入库 77 条", "实际 " + Store.db.materials.length);
  const kcsz = Store.db.materials.find((m) => m.id === "m-kcsz");
  ok(kcsz && kcsz.grade === "A" && /定级/.test(kcsz.gradeReason || ""), "credibility→grade 映射（high→A + 定级依据）");
  ok(kcsz && kcsz.citedCount >= 1 && !!kcsz.lastCitedAt, "被引计数服务端维护（m-kcsz citedCount=%s）".replace("%s", kcsz && kcsz.citedCount));
  const kc4 = Store.db.materials.find((m) => m.id === "m-kc4");
  ok(kc4 && kc4.dormant === true, "待淘汰服务端计算（m-kc4 满 30 天未被引）");

  // 2. 切到普通教师
  await Store.login("u-chen");
  await Store.syncMaterials();
  await Store.syncCases();
  ok(Store.visibleMaterials().length > 0, "普通账号素材同步 + 可见性过滤");
  ok(!!Store.materialById("m-kcsz"), "materialById 正常");

  // 3. 素材收藏（个人层）
  const mk = Store.materialById("m-kxjsh");
  ok(await Store.toggleFavMat(mk) && Store.isFavMat(mk), "素材收藏 on");
  ok(await Store.toggleFavMat(mk) && !Store.isFavMat(mk), "素材收藏 off");

  // 4. 上下文推荐（recommendFor）+ 排除已引用
  const draft = Store.db.cases.find((c) => c.id === "c-draft-1");
  const rec = await Store.recommendedMaterials("c-draft-1");
  ok(rec.length > 0, "recommendFor 返回推荐素材", "0 条");
  const citedTargets = (draft.citations || []).map((r) => r.target);
  ok(rec.every((m) => !citedTargets.includes(m.id) && m.status === "正常"), "推荐排除已引用且仅正常态");

  // 5. 最近引用（recentCitedBy，从本人案例引用派生）
  const recent = await Store.recentCitedMaterials();
  ok(recent.some((m) => m.id === "m-zmt"), "recentCitedBy 含 c-pending-1 引用的 m-zmt", recent.map((m) => m.id).join(","));

  // 6. 采集入库闸：必填校验 → 候选 → admin 确认 → 检索可见
  const url1 = "http://example.com/smoke-" + Date.now();
  const bad = await Store.addMaterial({ title: "冒烟缺字段", grade: "A", sourceUrl: url1, publishedAt: "2026-08-05" });
  ok(!bad.ok && /必填/.test(bad.error || ""), "入库必填校验（缺 gradeReason 被拒）");
  const payload = {
    title: "冒烟采集 靛蓝染整技艺传承谱系考察", grade: "B", gradeReason: "田野调查一手记录",
    sourceUrl: url1, publishedAt: "2026-08-05", excerpt: "靛蓝染整技艺传承谱系考察记录全文。",
  };
  const c1 = await Store.addMaterial(payload);
  ok(c1.ok && c1.material.status === "候选" && c1.material.grade === "B", "新采集（B 级）直接落候选");
  const mid = c1.material.id;
  let r = await Store.search("靛蓝染整技艺", { kind: "materials" });
  ok(!r.materials.some((e) => e.item.id === mid), "候选不进检索语料");
  const dup = await Store.addMaterial(Object.assign({}, payload, { title: "换个标题再采同一链接" }));
  ok(!dup.ok && dup.code === "dup", "同 URL 采集被拒");
  // admin 批量确认入库
  await Store.login("u-admin");
  await Store.syncMaterials();
  ok(await Store.batchUpdateMaterials([mid], { status: "正常" }), "批量 PATCH 确认候选入库");
  await Store.login("u-chen");
  await Store.syncMaterials();
  r = await Store.search("靛蓝染整技艺", { kind: "materials" });
  ok(r.materials.some((e) => e.item.id === mid), "确认后检索命中该素材");

  // 7. 相似度查重提示 top-3（真重复）+ force 放行
  const sim = await Store.addMaterial({
    title: "高等学校课程思政建设指导纲要（教高〔2020〕3号）全文转载",
    grade: "A", gradeReason: "官方文件", sourceUrl: "http://example.com/smoke-dup-" + Date.now(),
    publishedAt: "2026-08-05",
  });
  ok(!sim.ok && sim.code === "similar" && sim.similar.length >= 1 && sim.similar.length <= 3
    && sim.similar.some((s) => s.id === "m-kcsz"), "相似素材提示返回 top-3 且含 m-kcsz");
  const forced = await Store.addMaterial({
    title: "高等学校课程思政建设指导纲要（教高〔2020〕3号）全文转载",
    grade: "A", gradeReason: "官方文件", sourceUrl: "http://example.com/smoke-dup2-" + Date.now(),
    publishedAt: "2026-08-05",
  }, true);
  ok(forced.ok && forced.material.status === "候选", "force=true 跳过相似闸仍落候选");
  // 清理 force 进去的测试素材（停用，避免污染后续断言）
  await Store.login("u-admin");
  await Store.batchUpdateMaterials([forced.material.id], { status: "停用" });

  // 8. 批量调密级 / 停用恢复 / 豁免淘汰
  ok(await Store.batchUpdateMaterials(["m-kcsz", "m-kxjsh"], { level: 2 }), "批量 PATCH 调密级");
  let two = Store.db.materials.filter((m) => ["m-kcsz", "m-kxjsh"].includes(m.id));
  ok(two.every((m) => m.level === 2), "批量调密级生效");
  ok(await Store.batchUpdateMaterials(["m-kxjsh"], { status: "停用" }), "批量停用");
  await Store.login("u-chen");
  await Store.syncMaterials();
  ok(!Store.materialById("m-kxjsh"), "停用后普通账号不可见");
  await Store.login("u-admin");
  await Store.batchUpdateMaterials(["m-kxjsh"], { status: "正常", level: 0 });
  await Store.batchUpdateMaterials(["m-kcsz"], { level: 0 });
  ok(await Store.batchUpdateMaterials(["m-kc4"], { exempt: true }), "批量豁免淘汰");
  await Store.syncMaterials();
  ok(!Store.db.materials.find((m) => m.id === "m-kc4").dormant, "豁免后待淘汰标清除");

  // 9. 被引计数服务端维护：cite → 防抖 PATCH 后计数 +1；uncite 回落
  await Store.login("u-chen");
  await Store.syncMaterials();
  await Store.syncCases();
  const c = Store.db.cases.find((x) => x.id === "c-draft-1");
  const before = Store.materialUsage("m-qwllib").count;
  Store.cite(c, "m-qwllib");
  await sleep(2500); // 400ms 案例防抖 + 800ms 素材刷新防抖 + 网络
  await Store.syncMaterials();
  const after = Store.materialUsage("m-qwllib").count;
  ok(after === before + 1, "cite 后 citedCount 服务端 +1", before + "→" + after);
  Store.uncite(c, "m-qwllib");
  await sleep(2500);
  await Store.syncMaterials();
  ok(Store.materialUsage("m-qwllib").count === before, "uncite 后 citedCount 回落");

  // 10. 统计看板数据（admin 全量视角）
  await Store.login("u-admin");
  await Store.syncMaterials();
  const stats = Store.materialStats();
  ok(stats.total >= 77 && stats.failed >= 1 && stats.grades.A > 0 && stats.grades.B >= 1,
    "统计看板（总量/来源失效/grade 分布）", JSON.stringify(stats));

  console.log("\n%d PASS, %d FAIL", pass, fail);
  process.exit(fail ? 1 : 0);
}

main().catch((e) => { console.error("冒烟执行异常:", e); process.exit(1); });
