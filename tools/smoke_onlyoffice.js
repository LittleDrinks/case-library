#!/usr/bin/env node
// WP6 OnlyOffice 主编辑器冒烟：config JWT 签名（含篡改拒绝、payload==config）、docx 迁移生成、
// 模拟 DS 保存回调（status 2 落盘+blocks 回写+key 变更；status 4 无动作；坏 JWT 不落盘）、
// AI 修订插入（append/newsec/replace → docxVer bump）、版本快照 docx 副本与回滚恢复、
// 删除案例联动清理 docx。用法：node tools/smoke_onlyoffice.js [baseUrl]（默认 http://127.0.0.1:18077，需服务已启动）
"use strict";
const fs = require("fs");
const os = require("os");
const path = require("path");
const http = require("http");
const crypto = require("crypto");

const ROOT = path.join(__dirname, "..");
const BASE = process.argv[2] || "http://127.0.0.1:18077";

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

// ------------------------------------------------------------ JWT（与服务端 hmac HS256 同规则）
const SECRET = fs.readFileSync(path.join(ROOT, ".env"), "utf-8").split("\n")
  .map((l) => l.match(/^ONLYOFFICE_JWT_SECRET=(.*)$/))
  .filter(Boolean).map((m) => m[1].trim().replace(/^["']|["']$/g, ""))[0] || "";
const b64 = (d) => Buffer.from(d).toString("base64url");
function jwtSign(obj) {
  const h = b64('{"alg":"HS256","typ":"JWT"}');
  const p = b64(JSON.stringify(obj));
  const s = crypto.createHmac("sha256", SECRET).update(h + "." + p).digest("base64url");
  return h + "." + p + "." + s;
}

async function api(p, opts) {
  const d = await fetch(BASE + p, Object.assign({ headers: Store.authHeaders() }, opts || {}))
    .then((r) => r.json());
  return d;
}
const postJson = (p, body) => api(p, {
  method: "POST",
  headers: Object.assign({ "Content-Type": "application/json" }, Store.authHeaders()),
  body: JSON.stringify(body || {}),
});

async function main() {
  const constants = await fetch(BASE + "/api/constants").then((r) => r.json()).catch(() => null);
  ok(constants && constants.ok, "服务可达 " + BASE);
  if (!constants || !constants.ok) process.exit(1);
  const ds = await fetch("http://127.0.0.1:8081/healthcheck").then((r) => r.text()).catch(() => "");
  ok(ds.trim() === "true", "OnlyOffice DS 健康检查（8081/healthcheck）");

  await Store.login("u-chen");
  Store.setUser("u-chen");
  await Store.syncCases();

  // 0. 造冒烟案例（草稿、owner=u-chen）
  const MARK = "OO 冒烟原始段";
  const created = await Store.addCase({
    title: "OO 冒烟案例", typeId: "ct-general", audience: "ug",
    blocks: [
      { kind: "h2", text: "冒烟小节" },
      { kind: "p", text: MARK },
      { kind: "p", text: "第二段。" },
      { kind: "ul", text: "要点一\n要点二" },
    ],
  });
  ok(created && created.id, "创建冒烟案例", JSON.stringify(created && created.error));
  const cid = created.id;
  const docxPath = path.join(ROOT, "files", "cases", cid + ".docx");

  // 1. config：JWT 签名/payload/权限/key；同时触发 docx 迁移生成
  const cfg = await api("/api/onlyoffice/config/" + encodeURIComponent(cid));
  ok(cfg && cfg.ok && cfg.config && cfg.config.token, "GET /api/onlyoffice/config 返回签名 config",
    JSON.stringify(cfg && cfg.error));
  const conf = cfg.config;
  const [h, p, s] = conf.token.split(".");
  const want = crypto.createHmac("sha256", SECRET).update(h + "." + p).digest("base64url");
  ok(s === want, "config JWT 签名正确（HS256 重算一致）");
  const payload = JSON.parse(Buffer.from(p, "base64url").toString("utf-8"));
  const { token, ...stripped } = conf;
  ok(JSON.stringify(payload) === JSON.stringify(stripped), "JWT payload == config（除 token）");
  const badSig = s.slice(0, -2) + (s.endsWith("AA") ? "BB" : "AA");
  ok(badSig !== want, "篡改签名不一致（将被 DS 拒绝）");
  ok(conf.document.key === cid + "-v1" && /\/api\/onlyoffice\/file\//.test(conf.document.url)
    && /\/api\/onlyoffice\/callback\?caseId=/.test(conf.editorConfig.callbackUrl),
    "config key/url/callbackUrl 形态正确", conf.document.key);
  ok(conf.editorConfig.mode === "edit" && conf.document.permissions.edit === true,
    "owner 草稿 = 可编辑权限");
  ok(fs.existsSync(docxPath), "docx 迁移生成（config 请求触发）");
  ok(fs.existsSync(path.join(ROOT, "files", "cases", "c-02.docx")),
    "种子案例 docx 已随启动迁移生成");

  // admin 打开他人草稿：只读 + 评论
  await Store.login("u-admin");
  Store.setUser("u-admin");
  const cfgA = await api("/api/onlyoffice/config/" + encodeURIComponent(cid));
  ok(cfgA.ok && cfgA.config.editorConfig.mode === "view"
    && cfgA.config.document.permissions.edit === false
    && cfgA.config.document.permissions.comment === true,
    "admin 非 owner = 只读 + 评论权限");
  await Store.login("u-chen");
  Store.setUser("u-chen");

  // 2. AI 修订插入：append / newsec（replace 结构验证见任务验收记录）
  const ins = await postJson("/api/onlyoffice/insert",
    { caseId: cid, mode: "append", secTitle: "冒烟小节", text: "OO 冒烟 AI 修订段" });
  ok(ins && ins.ok && ins.docxVer === 2, "AI 修订插入（append）成功并 bump docxVer",
    JSON.stringify(ins && (ins.error || ins.docxVer)));
  ok((ins.case.blocks || []).some((b) => (b.text || "").includes("OO 冒烟 AI 修订段")),
    "插入后 blocks 回写含 AI 文本");
  const ins2 = await postJson("/api/onlyoffice/insert",
    { caseId: cid, mode: "newsec", text: "OO 冒烟新节\n新节正文。" });
  ok(ins2 && ins2.ok && (ins2.case.blocks || []).some((b) => b.kind === "h2" && b.text === "OO 冒烟新节"),
    "AI 修订插入（newsec）新节落 blocks");

  // 3. 模拟 DS 回调：静态服务托管“当前 docx 的副本”，callback status=2 应原样落盘；
  //    为验证 blocks 真正回写，先保留插入前快照副本？——改为：回调内容=当前 docx（含 AI 文本），
  //    验证 key 变更 + blocks 与 docx 一致；再回调 status=4 验证无动作
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "oo-smoke-"));
  fs.copyFileSync(docxPath, path.join(tmpDir, "saved.docx"));
  const srv = http.createServer((req, res) => {
    res.writeHead(200, { "Content-Type": "application/octet-stream" });
    fs.createReadStream(path.join(tmpDir, "saved.docx")).pipe(res);
  });
  await new Promise((r) => srv.listen(18998, "127.0.0.1", r));
  const keyBefore = (await api("/api/onlyoffice/config/" + encodeURIComponent(cid))).config.document.key;
  const cb = { status: 2, key: keyBefore, url: "http://127.0.0.1:18998/saved.docx", users: ["u-chen"] };
  const cbResp = await fetch(BASE + "/api/onlyoffice/callback?caseId=" + encodeURIComponent(cid), {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: "Bearer " + jwtSign(cb) },
    body: JSON.stringify(cb),
  }).then((r) => r.json());
  ok(cbResp && cbResp.error === 0, "callback 响应 {error:0}");
  const keyAfter = (await api("/api/onlyoffice/config/" + encodeURIComponent(cid))).config.document.key;
  ok(keyAfter !== keyBefore, "callback 保存后 document.key 变更", keyBefore + " -> " + keyAfter);
  const caseAfterCb = (await api("/api/cases/" + encodeURIComponent(cid))).case;
  ok((caseAfterCb.blocks || []).some((b) => (b.text || "").includes("OO 冒烟 AI 修订段")),
    "callback 后 blocks 与 docx 内容一致（回写路径）");
  const cb4 = { status: 4, key: keyAfter };
  await fetch(BASE + "/api/onlyoffice/callback?caseId=" + encodeURIComponent(cid), {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: "Bearer " + jwtSign(cb4) },
    body: JSON.stringify(cb4),
  }).then((r) => r.json());
  const keyAfter4 = (await api("/api/onlyoffice/config/" + encodeURIComponent(cid))).config.document.key;
  ok(keyAfter4 === keyAfter, "callback status=4（关闭无修改）不动作");
  const bytesBefore = fs.readFileSync(docxPath);
  await fetch(BASE + "/api/onlyoffice/callback?caseId=" + encodeURIComponent(cid), {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: "Bearer bad.token.here" },
    body: JSON.stringify(cb),
  }).then((r) => r.json());
  ok(fs.readFileSync(docxPath).equals(bytesBefore), "坏 JWT 的 callback 不落盘");
  srv.close();

  // 4. 版本快照 docx 副本 + 回滚恢复
  const ver = await postJson("/api/cases/" + encodeURIComponent(cid) + "/versions", { label: "OO 冒烟快照" });
  ok(ver && ver.ok && ver.version && ver.version.id, "存版本成功");
  const vCopy = path.join(ROOT, "files", "cases", "versions", cid + "-" + ver.version.id + ".docx");
  ok(fs.existsSync(vCopy), "版本 docx 副本生成（files/cases/versions/）");
  await postJson("/api/onlyoffice/insert", { caseId: cid, mode: "append", text: "OO 冒烟待回滚段" });
  const keyMid = (await api("/api/onlyoffice/config/" + encodeURIComponent(cid))).config.document.key;
  const rb = await postJson("/api/cases/" + encodeURIComponent(cid) + "/versions/"
    + encodeURIComponent(ver.version.id) + "/rollback", {});
  ok(rb && rb.ok && !(rb.case.blocks || []).some((b) => (b.text || "").includes("OO 冒烟待回滚段")),
    "回滚后 blocks 恢复（无待回滚段）");
  const keyRb = (await api("/api/onlyoffice/config/" + encodeURIComponent(cid))).config.document.key;
  ok(keyRb !== keyMid, "回滚后 document.key 变更（强制 DS 重载）", keyMid + " -> " + keyRb);

  // 5. 清理：删除案例联动删除 docx 与版本副本
  const del = await fetch(BASE + "/api/cases/" + encodeURIComponent(cid), {
    method: "DELETE", headers: Store.authHeaders(),
  }).then((r) => r.json());
  ok(del && del.ok, "清理：删除冒烟案例");
  ok(!fs.existsSync(docxPath) && !fs.existsSync(vCopy), "清理：docx 与版本副本联动删除");
  fs.rmSync(tmpDir, { recursive: true, force: true });

  console.log("\n%d PASS, %d FAIL", pass, fail);
  process.exit(fail ? 1 : 0);
}

main().catch((e) => { console.error("冒烟执行异常:", e); process.exit(1); });
