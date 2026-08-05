#!/usr/bin/env node
// WP4b 显式生成偏好冒烟：/api/my/prefs CRUD（PUT 保存 → GET 读回 → 部分更新 → 清空）、
// 账号隔离、未知字段丢弃，以及注入逻辑的数据层部分
// （Store.fetchMyPrefs 缓存 + Copilot.buildMessages 偏好段：有偏好含禁用词行、清空后不含）。
// 用法：node tools/smoke_prefs.js [baseUrl]（默认 http://127.0.0.1:18077，需服务已启动）
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
const Copilot = window.Copilot;

let pass = 0, fail = 0;
function ok(cond, name, extra) {
  if (cond) { pass++; console.log("PASS  " + name); }
  else { fail++; console.log("FAIL  " + name + (extra ? "  -> " + extra : "")); }
}

const authed = (extra) => Object.assign({ "Content-Type": "application/json" }, Store.authHeaders(), extra || {});

async function putPrefs(prefs) {
  const r = await fetch(BASE + "/api/my/prefs", {
    method: "PUT", headers: authed(), body: JSON.stringify(prefs),
  });
  return { status: r.status, body: await r.json() };
}
async function getPrefs() {
  const r = await fetch(BASE + "/api/my/prefs", { headers: authed() });
  return { status: r.status, body: await r.json() };
}

// buildMessages 用的最小案例对象（不落库）
const FAKE_CASE = {
  id: "c-prefs-smoke", title: "偏好冒烟", typeId: "ct-general", audience: "ug",
  course: "", summary: "", theoryPoints: [],
  blocks: [{ kind: "p", text: "测试段落，用于上下文组装。" }], citations: [],
};
const prefLineOf = async () => {
  const msgs = await Copilot.buildMessages(FAKE_CASE, 0, "写一段", "chat");
  return msgs[1].content;
};

async function main() {
  const constants = await fetch(BASE + "/api/constants").then((r) => r.json()).catch(() => null);
  ok(constants && constants.ok, "服务可达 " + BASE);
  if (!constants || !constants.ok) process.exit(1);

  // 未登录 → 401
  const noauth = await fetch(BASE + "/api/my/prefs");
  ok(noauth.status === 401, "未登录 GET /api/my/prefs → 401", String(noauth.status));

  await Store.login("u-chen");
  Store.setUser("u-chen");

  // 1. PUT 保存 → 回显四项；未知字段被丢弃
  const put1 = await putPrefs({
    length: "800字以内", style: "朴实课堂型", bannedWords: "赋能,抓手",
    themes: "科学家精神，科技自立自强", hack: "应被丢弃",
  });
  ok(put1.status === 200 && put1.body.ok &&
    put1.body.prefs.length === "800字以内" && put1.body.prefs.style === "朴实课堂型" &&
    put1.body.prefs.bannedWords === "赋能,抓手" && put1.body.prefs.themes.indexOf("科学家精神") >= 0,
    "PUT /api/my/prefs 保存并回显", JSON.stringify(put1.body));
  ok(!("hack" in (put1.body.prefs || {})), "未知字段不落入偏好", Object.keys(put1.body.prefs || {}).join(","));

  // 2. GET 读回（含 updatedAt）
  const get1 = await getPrefs();
  ok(get1.status === 200 && get1.body.ok && get1.body.prefs.bannedWords === "赋能,抓手" &&
    !!get1.body.prefs.updatedAt, "GET 读回已保存偏好（含 updatedAt）", JSON.stringify(get1.body.prefs));

  // 3. 部分更新（整体覆盖语义：未提交的字段清空）
  const put2 = await putPrefs({ length: "400字以内", style: "", bannedWords: "赋能", themes: "" });
  ok(put2.body.ok && put2.body.prefs.length === "400字以内" &&
    put2.body.prefs.bannedWords === "赋能" && put2.body.prefs.style === "",
    "PUT 部分更新 = 整体覆盖", JSON.stringify(put2.body.prefs));

  // 4. 注入逻辑（数据层）：有偏好时 buildMessages 偏好段含禁用词行
  await Store.saveMyPrefs({ length: "800字以内", style: "朴实课堂型", bannedWords: "赋能,抓手", themes: "科学家精神" });
  const cached = await Store.fetchMyPrefs();
  ok(cached && cached.bannedWords === "赋能,抓手", "Store.fetchMyPrefs 返回服务端偏好", JSON.stringify(cached));
  const line1 = await prefLineOf();
  ok(line1.indexOf("教师偏好：") >= 0 && line1.indexOf("禁用词绝对不得出现：赋能,抓手") >= 0 &&
    line1.indexOf("篇幅：800字以内") >= 0 && line1.indexOf("科学家精神") >= 0,
    "buildMessages 偏好段含篇幅/风格/禁用词/常用主题",
    line1.split("\n").filter((l) => l.indexOf("教师偏好") >= 0).join(" | "));

  // 5. 清空 → GET 四项全空；buildMessages 偏好段不再含禁用词
  await Store.saveMyPrefs({});
  const get2 = await getPrefs();
  const p2 = get2.body.prefs || {};
  ok(get2.body.ok && !p2.length && !p2.style && !p2.bannedWords && !p2.themes && !p2.updatedAt,
    "清空后 GET 偏好为空", JSON.stringify(p2));
  const line2 = await prefLineOf();
  ok(line2.indexOf("禁用词") < 0 && line2.indexOf("篇幅：") < 0,
    "清空后 buildMessages 偏好段不含禁用词/篇幅",
    line2.split("\n").filter((l) => l.indexOf("教师偏好") >= 0).join(" | "));

  // 6. 账号隔离：其他用户读不到 u-chen 的偏好（此处先给 u-chen 再写一条验证）
  await Store.saveMyPrefs({ bannedWords: "隔离测试词" });
  await Store.login("u-wang");
  Store.setUser("u-wang");
  const get3 = await getPrefs();
  const p3 = get3.body.prefs || {};
  ok(get3.body.ok && !p3.bannedWords, "账号隔离：u-wang 读不到 u-chen 的偏好", JSON.stringify(p3));

  // 清理：u-chen 偏好清空
  await Store.login("u-chen");
  Store.setUser("u-chen");
  const clean = await putPrefs({});
  ok(clean.body.ok, "清理：清空冒烟偏好");

  console.log("\n%d PASS, %d FAIL", pass, fail);
  process.exit(fail ? 1 : 0);
}

main().catch((e) => { console.error("冒烟执行异常:", e); process.exit(1); });
