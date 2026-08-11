#!/usr/bin/env node
"use strict";

const BASE = process.argv[2] || "http://127.0.0.1:18082";
let pass = 0, fail = 0, cid = "", attachmentIds = [], authorToken = "", adminToken = "";

function ok(value, name, extra) {
  if (value) { pass += 1; console.log("PASS  " + name); return; }
  fail += 1;
  console.log("FAIL  " + name + (extra ? "  -> " + extra : ""));
}

async function request(path, opts, token) {
  const options = Object.assign({}, opts || {});
  options.headers = Object.assign({ "Content-Type": "application/json" }, options.headers || {});
  if (token) options.headers.Authorization = "Bearer " + token;
  return fetch(BASE + path, options);
}

async function json(path, opts, token) {
  const response = await request(path, opts, token);
  return { status: response.status, body: await response.json() };
}

async function login(uid) {
  const result = await json("/api/auth/login", { method: "POST", body: JSON.stringify({ userId: uid }) });
  return result.body.token;
}

async function addAttachment(level, title, text) {
  const payload = { level, title, text, fileName: title + ".txt", mime: "text/plain",
    data: Buffer.from(text).toString("base64") };
  const result = await json(`/api/cases/${cid}/attachments`,
    { method: "POST", body: JSON.stringify(payload) }, authorToken);
  const item = result.body.attachment;
  if (item) attachmentIds.push(item.id);
  return item;
}

function byTitle(items, title) {
  return (items || []).find((item) => item.title === title);
}

async function transition(action, token) {
  return json(`/api/cases/${cid}/${action === "submit" ? "submit" : "review"}`,
    { method: "POST", body: JSON.stringify(action === "submit" ? {} : { action }) }, token);
}

async function cleanup() {
  if (!cid) return;
  await transition("hide", adminToken).catch(() => null);
  for (const aid of attachmentIds) {
    await request(`/api/cases/${cid}/attachments/${aid}`, { method: "DELETE" }, authorToken).catch(() => null);
  }
  await request(`/api/cases/${cid}`, { method: "DELETE" }, adminToken).catch(() => null);
}

async function run() {
  const nonce = Date.now().toString(36);
  const bodyNonce = Math.random().toString(36).slice(2, 11);
  const titles = ["公开附件-" + nonce, "校内附件-" + nonce, "私密附件-" + nonce];
  const bodies = ["PUBLICBODY-" + bodyNonce, "CAMPUSBODY-" + bodyNonce,
    "PRIVATEBODY-" + bodyNonce];
  authorToken = await login("u-chen");
  adminToken = await login("u-admin");
  const campusToken = await login("u-zhao");

  const created = await json("/api/cases", { method: "POST", body: JSON.stringify({
    title: "案例文件夹冒烟-" + nonce, typeId: "ct-general", audience: "ug",
    blocks: [{ kind: "p", text: "正文" }],
  }) }, authorToken);
  cid = created.body.case && created.body.case.id;
  ok(created.status === 200 && cid, "创建案例文件夹", JSON.stringify(created.body));

  const attachments = [];
  for (let i = 0; i < 3; i += 1) attachments.push(await addAttachment(i, titles[i], bodies[i]));
  ok(attachments.every(Boolean), "创建三级附件");
  ok(attachments.every((a, i) => a.level === i && !("used" in a) && !("publish" in a)),
    "附件只保留访问级别", JSON.stringify(attachments));

  await json(`/api/cases/${cid}`, { method: "PATCH", body: JSON.stringify({
    blocks: [{ kind: "p", text: `正文 [附件 3](attachment:${attachments[2].id})` }],
  }) }, authorToken);
  ok((await transition("submit", authorToken)).status === 200, "提交冻结全部附件");
  ok((await transition("approve", adminToken)).status === 200, "审核发布并投影素材");

  const publicCase = (await json(`/api/cases/${cid}`)).body.case;
  ok(titles.every((title) => byTitle(publicCase.attachments, title)), "公开案例展示全部附件名称");
  ok(byTitle(publicCase.attachments, titles[0]).contentAvailable === true,
    "匿名可读公开附件内容");
  ok([1, 2].every((i) => byTitle(publicCase.attachments, titles[i]).contentAvailable === false),
    "匿名只见校内和私密附件名称");
  ok(!("storedPath" in byTitle(publicCase.attachments, titles[2])), "私密附件响应不泄露文件路径");

  const statuses = [];
  for (const aid of attachmentIds) statuses.push((await request(
    `/api/cases/${cid}/attachments/${aid}/file`)).status);
  ok(statuses.join() === "200,403,403", "匿名附件文件权限 200/403/403", statuses.join());
  const campusStatuses = [];
  for (const aid of attachmentIds) campusStatuses.push((await request(
    `/api/cases/${cid}/attachments/${aid}/file`, {}, campusToken)).status);
  ok(campusStatuses.join() === "200,200,403", "校内账号附件文件权限 200/200/403", campusStatuses.join());
  ok((await request(`/api/cases/${cid}/attachments/${attachmentIds[2]}/file`, {}, authorToken)).status === 200,
    "来源作者可读私密附件");

  const publicMaterials = (await json("/api/materials")).body.materials;
  ok(titles.every((title) => byTitle(publicMaterials, title)), "素材库公开全部投影名称");
  ok(byTitle(publicMaterials, titles[2]).contentAvailable === false,
    "私密素材列表仅返回公开元数据");
  const titleSearch = await json("/api/search", { method: "POST", body: JSON.stringify({
    q: titles[2], kinds: ["material"], limit: 20,
  }) });
  const titleHit = byTitle(titleSearch.body.materials, titles[2]);
  ok(titleHit && titleHit.contentAvailable === false && !titleHit.snippet,
    "匿名可按名称检索私密素材但无摘要", JSON.stringify(titleHit));
  const bodySearch = await json("/api/search", { method: "POST", body: JSON.stringify({
    q: bodies[2], kinds: ["material"], limit: 20,
  }) });
  ok(!byTitle(bodySearch.body.materials, titles[2]), "匿名不能用正文反查私密素材");
  const authorSearch = await json("/api/search", { method: "POST", body: JSON.stringify({
    q: bodies[2], kinds: ["material"], limit: 20,
  }) }, authorToken);
  ok(!!byTitle(authorSearch.body.materials, titles[2]), "来源作者可检索私密正文");
}

run().catch((error) => { fail += 1; console.error(error); }).finally(async () => {
  await cleanup();
  console.log(`\n${pass} passed, ${fail} failed`);
  process.exit(fail ? 1 : 0);
});
