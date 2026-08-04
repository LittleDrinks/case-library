#!/usr/bin/env node
// WP4 审核与反馈沉淀冒烟：checking 状态机 + 词库机审批注 + checking 留痕、
// reasonType 强制（无则 400）、退回台账聚合、版本 diffSummary、
// AI 生成标识（markAiAssist 持久化 + 审核通过 reviewedBy）、AI_REVIEW_ENABLED 开关一致性。
// 用法：node tools/smoke_review.js [baseUrl]（默认 http://127.0.0.1:18077，需服务已启动）
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

let pass = 0, fail = 0;
function ok(cond, name, extra) {
  if (cond) { pass++; console.log("PASS  " + name); }
  else { fail++; console.log("FAIL  " + name + (extra ? "  -> " + extra : "")); }
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function getCase(cid) {
  const d = await fetch(BASE + "/api/cases/" + encodeURIComponent(cid), {
    headers: Store.authHeaders(),
  }).then((r) => r.json());
  return d && d.ok ? d.case : null;
}

async function waitStatus(cid, want, timeoutMs) {
  const t0 = Date.now();
  let c = null;
  while (Date.now() - t0 < timeoutMs) {
    c = await getCase(cid);
    if (c && c.status === want) return c;
    await sleep(1000);
  }
  return c;
}

async function main() {
  const constants = await fetch(BASE + "/api/constants").then((r) => r.json()).catch(() => null);
  ok(constants && constants.ok, "服务可达 " + BASE);
  if (!constants || !constants.ok) process.exit(1);

  // 1. 提交 → checking → 机审（词库命中）→ pending
  await Store.login("u-chen");
  Store.setUser("u-chen");
  await Store.syncCases();
  const created = await Store.addCase({
    title: "机审冒烟案例（含术语与职务误写）",
    typeId: "ct-general", audience: "ug",
    theoryPoints: ["自然辩证法"],
    blocks: [
      { kind: "h2", text: "案例背景" },
      { kind: "p", text: "本案例讨论自然辨证法在工程教学中的应用，强调按步就班推进课程改革。" },
      { kind: "p", text: "李强总书记指出，科技创新是高质量发展的核心动力，我们要做好布署。" },
      { kind: "p", text: "教师们结合辩证唯物主义自然观组织学生研讨，形成良好的课堂氛围。" +
          "本段仅用于凑足篇幅：".repeat(30) },
    ],
    citations: [{ target: "kn-01-01", quote: "自然辩证法" }],
  });
  ok(created && created.id, "创建冒烟案例", JSON.stringify(created && created.error));
  const cid = created.id;
  ok(created.meta && created.meta.origin === "human" && Array.isArray(created.meta.modelVersions),
    "新案例 meta 默认 origin=human", JSON.stringify(created.meta));

  const submitted = await Store.submitCase(created);
  ok(submitted && created.status === "checking", "提交后状态 = checking", created.status);
  const pending = await waitStatus(cid, "pending", 120000);
  ok(pending && pending.status === "pending", "机审完成后转 pending", pending && pending.status);
  const ruleAnnos = (pending.annotations || []).filter((a) => a.author === "机审·词库");
  const ruleText = ruleAnnos.map((a) => a.text).join("\n");
  ok(ruleAnnos.length >= 3 && ruleAnnos.every((a) => a.kind === "risk"),
    "词库机审命中 ≥3 条 risk 批注", JSON.stringify(ruleAnnos.map((a) => a.quote)));
  ok(ruleText.includes("自然辨证法") && ruleText.includes("李强总书记") && ruleText.includes("布署"),
    "教材术语/职务/易错词三类词库均命中", ruleText.slice(0, 200));
  const aiAnnos = (pending.annotations || []).filter((a) => a.author === "机审·审校");
  ok(constants.reviewEnabled ? true : aiAnnos.length === 0,
    "AI_REVIEW_ENABLED 关闭时无 LLM 审校批注（当前 reviewEnabled=" + constants.reviewEnabled + "）");

  // checking 留痕（admin 视角；setUser 同步前端身份，syncCases 才会拉 /api/reviews）
  await Store.login("u-admin");
  Store.setUser("u-admin");
  await Store.syncCases();
  const revs = Store.db.reviews.filter((r) => r.caseId === cid);
  const checkingRec = revs.find((r) => r.action === "checking");
  ok(checkingRec && /词库规则命中/.test(checkingRec.opinion || ""),
    "reviews 留痕 action=checking 含机审结果", checkingRec && checkingRec.opinion);

  // 2. 退回必须带 reasonType：无 → 400；forced_mapping → 成功并留痕
  const c4 = await getCase(cid);
  await Store.startReview(c4);
  const bad = await fetch(BASE + "/api/cases/" + encodeURIComponent(cid) + "/review", {
    method: "POST", headers: Object.assign({ "Content-Type": "application/json" }, Store.authHeaders()),
    body: JSON.stringify({ action: "reject", reason: "缺 reasonType 应被拒绝" }),
  });
  ok(bad.status === 400, "退回不带 reasonType → 400", String(bad.status));
  const good = await fetch(BASE + "/api/cases/" + encodeURIComponent(cid) + "/review", {
    method: "POST", headers: Object.assign({ "Content-Type": "application/json" }, Store.authHeaders()),
    body: JSON.stringify({ action: "reject", reason: "理论映射牵强", reasonType: "forced_mapping" }),
  });
  const goodJ = await good.json();
  ok(good.status === 200 && goodJ.ok && goodJ.case.status === "draft",
    "带 forced_mapping 退回成功并回 draft", String(good.status));
  await Store.syncCases();
  const rejRec = Store.db.reviews.find((r) => r.caseId === cid && r.action === "reject");
  ok(rejRec && rejRec.reasonType === "forced_mapping", "reviews 留痕含 reasonType=forced_mapping",
    rejRec && rejRec.reasonType);

  // 3. 退回台账：按类型聚合
  const ledger = await Store.fetchReviewLedger();
  ok(ledger && (ledger.byType.forced_mapping || 0) >= 1 &&
    ledger.items.some((x) => x.caseId === cid && x.reasonType === "forced_mapping"),
    "GET /api/admin/review-ledger 按类型聚合退回记录", ledger && JSON.stringify(ledger.byType));

  // 4. 版本 diffSummary：连续两个带快照版本后，后一个带增/删/改统计
  await Store.login("u-chen");
  Store.setUser("u-chen");
  await Store.syncCases();
  const mine = Store.db.cases.find((c) => c.id === cid);
  await Store.saveVersion(cid, "存档A");
  mine.blocks.push({ kind: "p", text: "新增一段：补充教学反思与改进措施。" });
  Store.touch(mine);
  await sleep(1200);
  await Store.saveVersion(cid, "存档B");
  const after = await getCase(cid);
  const vb = (after.versions || []).find((v) => v.label === "存档B");
  ok(vb && vb.diffSummary && vb.diffSummary.added >= 1 && vb.diffSummary.blocks.length >= 1,
    "连续两版后 versions 返回 diffSummary（增/删/改 + 变更块）",
    vb && JSON.stringify(vb.diffSummary));

  // 5. AI 生成标识：copilot 采纳打标持久化；审核通过记录 reviewedBy
  Store.markAiAssist(mine, "qwen-plus");
  Store.touch(mine);
  await sleep(1200);
  const marked = await getCase(cid);
  ok(marked.meta && marked.meta.origin === "ai_assisted" &&
    (marked.meta.modelVersions || []).includes("qwen-plus"),
    "markAiAssist 持久化 origin=ai_assisted + modelVersions", JSON.stringify(marked.meta));
  const resub = Store.db.cases.find((c) => c.id === cid);
  await Store.submitCase(resub);
  await waitStatus(cid, "pending", 120000);
  await Store.login("u-admin");
  Store.setUser("u-admin");
  const c6 = await getCase(cid);
  const approved = await Store.reviewCase(c6, "approve", "同意发布", "");
  ok(approved, "管理员审核通过");
  const pub = await getCase(cid);
  ok(pub && pub.status === "published" && pub.meta && pub.meta.reviewedBy === "周正",
    "审核通过记录 meta.reviewedBy", pub && JSON.stringify(pub.meta));

  // 清理：删除冒烟案例（联动清批注/版本/留痕）
  const del = await fetch(BASE + "/api/cases/" + encodeURIComponent(cid), {
    method: "DELETE", headers: Store.authHeaders(),
  }).then((r) => r.json());
  ok(del && del.ok, "清理：删除冒烟案例");

  console.log("\n%d PASS, %d FAIL", pass, fail);
  process.exit(fail ? 1 : 0);
}

main().catch((e) => { console.error("冒烟执行异常:", e); process.exit(1); });
