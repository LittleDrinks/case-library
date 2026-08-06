#!/usr/bin/env node
// WP7 Neo4j 图谱冒烟：灌库计数（overview stats）、ego 两跳子图、reverse 知识点/标签反查、
// 全局问答（AI 在线 → 带节点引用的回答）、增量同步（案例建/删、素材上传/删除联动）、
// qa 降级（独立实例 AI_API_KEY 置空 → degraded 子图统计）、admin 全量重建。
// 用法：node tools/smoke_graph.js [baseUrl]（默认 http://127.0.0.1:18077，
// 需服务已启动且 Neo4j 在线；会另起 18079 降级实例跑完即杀）
"use strict";
const { spawn } = require("child_process");
const path = require("path");

const ROOT = path.join(__dirname, "..");
const BASE = process.argv[2] || "http://127.0.0.1:18077";
const DEGRADED_PORT = 18079;
const DEGRADED_BASE = "http://127.0.0.1:" + DEGRADED_PORT;

let pass = 0, fail = 0;
function ok(cond, name, extra) {
  if (cond) { pass++; console.log("PASS  " + name); }
  else { fail++; console.log("FAIL  " + name + (extra ? "  -> " + String(extra).slice(0, 300) : "")); }
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const api = (p, opts, base) =>
  fetch((base || BASE) + p, opts).then((r) => r.json()).catch(() => null);
const login = async (uid, base) => {
  const d = await api("/api/auth/login", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ userId: uid }),
  }, base);
  return d && d.ok ? d.token : null;
};
const auth = (tok) => ({ Authorization: "Bearer " + tok });

async function main() {
  const constants = await api("/api/constants");
  ok(constants && constants.ok, "服务可达 " + BASE);
  if (!constants || !constants.ok) process.exit(1);
  ok(constants.graph === true, "constants 报告图谱已配置（graph=true）");

  // 1. 灌库计数（overview stats）
  const ov = await api("/api/graph/overview");
  ok(ov && ov.ok && ov.nodes.length > 0, "GET /api/graph/overview 返回全库轻量图",
    ov && (ov.error || ov.nodes && ov.nodes.length));
  const st = (ov && ov.stats) || {};
  ok(st.Knowledge === 52 && st.Chapter === 7, "灌库计数：Knowledge=52、Chapter=7",
    JSON.stringify(st));
  ok(st.Material === 77 && st.Case >= 4, "灌库计数：Material=77、Case≥4", JSON.stringify(st));
  ok((st["rel:CITES"] || 0) > 0 && (st["rel:BELONGS"] || 0) === 52,
    "灌库计数：CITES 边>0、BELONGS=52", JSON.stringify(st));

  // 2. ego 两跳子图
  const ego = await api("/api/graph/ego?type=case&id=c-02");
  ok(ego && ego.ok && ego.center === "c-02" && ego.nodes.length > 1 && ego.links.length > 0,
    "ego(case c-02) 返回两跳子图", ego && (ego.error || ego.nodes && ego.nodes.length));
  // c-05 与 c-11 同引 kn-06-01：以 c-05 为中心的两跳必含另一案例
  const ego2 = await api("/api/graph/ego?type=case&id=c-05");
  const types = new Set((ego2.nodes || []).map((n) => n.type));
  const otherCases = (ego2.nodes || []).filter((n) => n.type === "case" && n.id !== "c-05");
  ok(ego2 && types.has("section") && otherCases.some((n) => n.id === "c-11"),
    "ego 含知识节（一跳）与共同引用的其他案例（两跳，c-05→kn-06-01→c-11）",
    Array.from(types).join(",") + " otherCases=" + otherCases.map((n) => n.id));
  const badType = await fetch(BASE + "/api/graph/ego?type=nope&id=x");
  ok(badType.status === 404, "ego 非法 type → 404", String(badType.status));
  const noNode = await fetch(BASE + "/api/graph/ego?type=case&id=c-not-exist");
  ok(noNode.status === 404, "ego 未知节点 → 404", String(noNode.status));

  // 3. reverse 反查
  const rev = await api("/api/graph/reverse?kn=kn-06-01");
  ok(rev && rev.ok && rev.node && rev.node.id === "kn-06-01",
    "reverse(kn-06-01) 返回知识点节点", rev && rev.error);
  ok(rev.cases.length > 0 && rev.materials.length > 0,
    "reverse 含直接引用案例与两跳素材（知识点→案例→素材）",
    "cases=" + (rev.cases || []).length + " materials=" + (rev.materials || []).length);
  const revTag = await api("/api/graph/reverse?tag=" + encodeURIComponent("科学家精神"));
  ok(revTag && revTag.ok && revTag.cases.some((c) => c.id === "c-02"),
    "reverse(tag=科学家精神) 反查到案例 c-02", revTag && (revTag.error || JSON.stringify(revTag.cases)));
  const revBad = await fetch(BASE + "/api/graph/reverse");
  ok(revBad.status === 400, "reverse 缺参数 → 400", String(revBad.status));

  // 4. 全局问答（AI 在线：带节点引用的回答；AI 不在线也能收到降级统计）
  const qa = await api("/api/graph/qa", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ q: "库里的案例主要涉及哪些思政主题" }),
  });
  ok(qa && qa.ok, "POST /api/graph/qa 应答", qa && qa.error);
  if (constants.aiConfigured) {
    ok(qa.answer && qa.answer.length > 50 && !qa.degraded,
      "qa 真实 AI 回答（非降级）", qa.answer ? "len=" + qa.answer.length : qa.note);
    ok((qa.refs || []).length > 0 && qa.refs.every((r) => r.ref && r.ref.id),
      "qa 回答带节点引用（可点开详情）", JSON.stringify((qa.refs || []).slice(0, 3)));
  } else {
    ok(qa.degraded && qa.stats, "AI 未配置时 qa 降级返回子图统计", JSON.stringify(qa.stats));
  }

  // 5. 增量同步：案例建/删
  const ctok = await login("u-chen");
  const atok = await login("u-admin");
  ok(!!ctok && !!atok, "登录 u-chen / u-admin");
  const created = await api("/api/cases", {
    method: "POST", headers: Object.assign({ "Content-Type": "application/json" }, auth(ctok)),
    body: JSON.stringify({
      id: "c-graph-smoke", title: "图谱增量同步冒烟案例", typeId: "ct-general",
      theoryPoints: ["图谱冒烟"],
      citations: [{ target: "kn-06-01" }, { target: "m-kcsz" }],
    }),
  });
  ok(created && created.ok, "创建冒烟案例（挂 kn-06-01 + m-kcsz 引用）", created && created.error);
  await sleep(600);
  const egoAfter = await api("/api/graph/ego?type=knowledge&id=kn-06-01", { headers: auth(ctok) });
  const smokeEdges = (egoAfter.links || []).filter(
    (l) => l.source === "c-graph-smoke" || l.target === "c-graph-smoke");
  ok(egoAfter && egoAfter.ok && smokeEdges.length >= 2,
    "新案例引用边 ego 立即可见（CITES×2）", JSON.stringify(smokeEdges));
  const del = await api("/api/cases/c-graph-smoke", { method: "DELETE", headers: auth(ctok) });
  ok(del && del.ok, "删除冒烟案例", del && del.error);
  await sleep(600);
  const egoGone = await api("/api/graph/ego?type=knowledge&id=kn-06-01", { headers: auth(atok) });
  ok(egoGone && !(egoGone.nodes || []).some((n) => n.id === "c-graph-smoke"),
    "删除案例后图谱节点同步消失");

  // 6. 增量同步：素材上传/删除联动（admin 上传直通正常 → 图谱成点；删文件 → 图谱消失）
  const up = await api("/api/files", {
    method: "POST", headers: Object.assign({ "Content-Type": "application/json" }, auth(atok)),
    body: JSON.stringify({
      title: "图谱删除冒烟素材", filename: "graph-smoke.md", level: 0,
      summary: "图谱删除同步测试",
      dataBase64: Buffer.from("图谱删除同步冒烟素材内容：科技伦理与人工智能治理。", "utf-8").toString("base64"),
    }),
  });
  const mid = up && up.material && up.material.id;
  const fid = up && up.material && up.material.fileId;
  ok(!!mid && !!fid, "上传冒烟素材文件", up && up.error);
  await sleep(600);
  const mEgo = await api("/api/graph/ego?type=material&id=" + encodeURIComponent(mid));
  ok(mEgo && mEgo.ok, "上传素材图谱成点（ego 可见）", mEgo && mEgo.error);
  const fd = await api("/api/files/" + encodeURIComponent(fid), { method: "DELETE", headers: auth(atok) });
  ok(fd && fd.ok, "删除素材文件", fd && fd.error);
  await sleep(600);
  const mGone = await fetch(BASE + "/api/graph/ego?type=material&id=" + encodeURIComponent(mid));
  ok(mGone.status === 404, "删除素材后图谱节点同步消失（ego 404）", String(mGone.status));

  // 7. qa 降级：独立实例 AI_API_KEY 置空 → degraded 子图统计
  const child = spawn(path.join(ROOT, ".venv", "bin", "python"), ["server.py", String(DEGRADED_PORT)], {
    cwd: ROOT, env: Object.assign({}, process.env, { AI_API_KEY: "", AI_BASE_URL: "" }),
    stdio: "ignore",
  });
  let up2 = false;
  for (let i = 0; i < 60 && !up2; i++) {
    await sleep(1000);
    const c = await api("/api/constants", {}, DEGRADED_BASE);
    up2 = !!(c && c.ok);
  }
  ok(up2, "降级实例（AI 置空）启动 " + DEGRADED_BASE);
  if (up2) {
    const dqa = await api("/api/graph/qa", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ q: "库里的案例主要涉及哪些思政主题" }),
    }, DEGRADED_BASE);
    ok(dqa && dqa.ok && dqa.degraded === true && dqa.answer === null && dqa.stats
      && Object.keys(dqa.stats).length > 0,
      "AI 不可用时 qa 降级返回子图统计（degraded=true, answer=null）",
      dqa && JSON.stringify({ degraded: dqa.degraded, note: dqa.note }));
  }
  child.kill("SIGTERM");

  // 8. admin 全量重建
  const rb = await api("/api/admin/graph/rebuild", { method: "POST", headers: auth(atok) });
  ok(rb && rb.ok && rb.started, "POST /api/admin/graph/rebuild（admin）", rb && rb.error);
  let rebuilt = null;
  for (let i = 0; i < 30; i++) {
    await sleep(1000);
    const o = await api("/api/graph/overview");
    if (o && o.ok && o.stats && o.stats.Knowledge === 52 && o.stats.Material === 77) {
      rebuilt = o.stats;
      break;
    }
  }
  ok(!!rebuilt, "重建后计数恢复（Knowledge=52、Material=77）", JSON.stringify(rebuilt));

  console.log("\n%d PASS, %d FAIL", pass, fail);
  process.exit(fail ? 1 : 0);
}

main().catch((e) => { console.error("冒烟执行异常:", e); process.exit(1); });
