#!/usr/bin/env node
// WP3 引用证据冒烟：句级锚点（U.citeAnchors/U.markCites 纯函数）、手工挂接自动捕获 evidence、
// 检索 chunk 证据元数据、来源失效判定、采纳 AI 内容落地真实引用、老案例 evidence 启动回填。
// 用法：node tools/smoke_evidence.js [baseUrl]（默认 http://127.0.0.1:18077，需服务已启动）
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
const rawFetch = global.fetch;
global.fetch = (url, opts) => rawFetch(String(url).startsWith("/") ? BASE + url : url, opts);

for (const f of ["app/seed.js", "app/data.js", "app/js/util.js", "app/js/store.js", "app/js/copilot.js"]) {
  eval(fs.readFileSync(path.join(ROOT, f), "utf-8"));
}
window.U.toast = () => {};
const Store = window.Store;
const U = window.U;
const Copilot = window.Copilot;

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

  // 1. 句级锚点纯函数：quote 定位 / 锚点漂移 / 来源失效角标
  const blocks = [
    { kind: "p", text: "钱伟长是我国著名科学家。他主持创办了上海大学。这一理念影响深远。〔1〕" },
    { kind: "p", text: "另一段没有引用的文字。" },
  ];
  const cites = [{ target: "kn-06-01", quote: "他主持创办了上海大学" }];
  const anchors = U.citeAnchors(blocks, cites);
  ok(anchors[0] && anchors[0][0].n === 1 && anchors[0][0].at > 0 && !anchors[0][0].drift,
    "句级锚点定位到 quote 所在块", JSON.stringify(anchors));
  let html = U.markCites(blocks[0].text, 0, anchors, () => false);
  ok(html.includes("上海大学<a class=\"cite-mark\"") && html.endsWith("深远。"),
    "〔1〕上标跟在 quote 句后（字面标记被剔除）", html);
  // 漂移：quote 被改写后找不到
  const drifted = U.citeAnchors([{ kind: "p", text: "句子已经改写过了。〔1〕" }], cites);
  ok(drifted[0] && drifted[0][0].drift === true && drifted[0][0].at === -1, "quote 找不到 → 锚点漂移（块尾）");
  html = U.markCites("句子已经改写过了。〔1〕", 0, drifted, () => true);
  ok(html.includes("cite-mark drift") && html.includes("锚点漂移") && html.includes("cite-bad"),
    "漂移标记 + 来源失效角标渲染");

  // 2. 老案例 evidence 启动回填（迁移）：c-02 的 kn/素材引用都有 evidence
  await Store.login("u-admin");
  await Store.syncCases();
  const c02 = Store.db.cases.find((c) => c.id === "c-02");
  const evs = (c02.citations || []).map((r) => r.evidence);
  ok(evs.length >= 4 && evs.every((e) => e && e.materialId && e.snippet && e.capturedAt),
    "老案例 evidence 启动回填（c-02 全部引用）", JSON.stringify(evs.map((e) => e && e.materialId)));
  const knEv = c02.citations.find((r) => r.target === "kn-06-02");
  ok(knEv && knEv.evidence.sec && /^\d/.test(knEv.evidence.sec),
    "kn 节引用 evidence.sec = fileSec", knEv && JSON.stringify(knEv.evidence));

  // 3. /api/search chunk 证据元数据（materialId/sec/snippet/标题/发布时间/grade）
  const sr = await fetch(BASE + "/api/search", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ q: "课程思政 纲要", kinds: ["material"], limit: 5 }),
  }).then((r) => r.json());
  const mh = (sr.materials || [])[0];
  ok(mh && mh.materialId && mh.snippet && mh.title && ("publishedAt" in mh) && ("grade" in mh),
    "检索素材 chunk 携带证据元数据", JSON.stringify(mh && { materialId: mh.materialId, publishedAt: mh.publishedAt, grade: mh.grade }));
  const kr = await fetch(BASE + "/api/search", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ q: "科学技术 创新", kinds: ["knowledge"], limit: 5 }),
  }).then((r) => r.json());
  ok((kr.knowledge || []).some((h) => h.id && h.sec && h.snippet), "检索知识 chunk 带 kn id + sec + snippet");

  // 4. 手工挂接自动捕获 evidence（普通教师视角）
  await Store.login("u-chen");
  await Store.syncMaterials();
  await Store.syncCases();
  const draft = Store.db.cases.find((c) => c.id === "c-draft-1");
  const quote = "钱伟长图书馆入选全国首批科学家精神教育基地";
  Store.cite(draft, "m-kxjsh", { quote });
  const ref1 = draft.citations.find((r) => r.target === "m-kxjsh");
  ok(ref1 && ref1.quote === quote && ref1.evidence && ref1.evidence.snippet && ref1.evidence.capturedAt,
    "手工挂接自动捕获 evidence（素材 excerpt）", ref1 && JSON.stringify(ref1.evidence));
  Store.cite(draft, "kn-04-01", { quote: "问题导向是马克思主义的鲜明特点" });
  const ref2 = draft.citations.find((r) => r.target === "kn-04-01");
  ok(ref2 && ref2.evidence && ref2.evidence.sec && ref2.evidence.snippet.includes("问题"),
    "kn 节挂接 evidence.sec = fileSec", ref2 && JSON.stringify(ref2.evidence && ref2.evidence.sec));
  // 服务端持久化校验（防抖 400ms + 网络）
  await sleep(1200);
  const fresh = await fetch(BASE + "/api/cases/c-draft-1", { headers: Store.authHeaders() }).then((r) => r.json());
  const fref = (fresh.case.citations || []).find((r) => r.target === "m-kxjsh");
  ok(fref && fref.evidence && fref.evidence.snippet && fref.quote === quote, "evidence 已持久化到服务端案例");

  // 5. 来源失效判定：停用素材 → citeFailed；恢复后回落
  await Store.login("u-admin");
  await Store.batchUpdateMaterials(["m-kxjsh"], { status: "停用" });
  await Store.login("u-chen");
  await Store.syncMaterials();
  ok(Store.citeFailed({ target: "m-kxjsh" }) === true, "素材停用 → 引用标来源失效");
  ok(Store.citeFailed({ target: "kn-04-01" }) === false, "kn 节引用不受素材状态影响");
  await Store.login("u-admin");
  await Store.batchUpdateMaterials(["m-kxjsh"], { status: "正常" });
  await Store.syncMaterials();
  ok(Store.citeFailed({ target: "m-kxjsh" }) === false, "素材恢复 → 失效标回落");

  // 6. 采纳 AI 插入：〔n〕落成真实引用（quote=所在句、evidence 来自 chunk）
  await Store.login("u-chen");
  await Store.syncCases();
  const draft2 = Store.db.cases.find((c) => c.id === "c-draft-1");
  const msg = {
    text: "落实立德树人根本任务，必须将价值塑造、知识传授和能力培养三者融为一体〔1〕。",
    chunks: [{ n: 1, kind: "material", materialId: "m-kcsz", sec: "", grade: "A",
               snippet: "落实立德树人根本任务，必须将价值塑造、知识传授和能力培养三者融为一体、不可割裂。" }],
  };
  const added = Copilot.materializeCitations(draft2, msg);
  const ref3 = draft2.citations.find((r) => r.target === "m-kcsz");
  ok(added.includes("m-kcsz") && ref3 && ref3.quote.includes("三者融为一体") &&
    ref3.evidence && ref3.evidence.snippet.includes("立德树人") && ref3.evidence.capturedAt,
    "采纳 AI 插入 → 真实 citation（quote=所在句 + evidence）", ref3 && JSON.stringify(ref3.evidence));
  // 清理本烟测试挂接的引用，恢复种子状态
  ["m-kxjsh", "kn-04-01", "m-kcsz"].forEach((t) => Store.uncite(draft2, t));
  await sleep(1200);

  console.log("\n%d PASS, %d FAIL", pass, fail);
  process.exit(fail ? 1 : 0);
}

main().catch((e) => { console.error("冒烟执行异常:", e); process.exit(1); });
