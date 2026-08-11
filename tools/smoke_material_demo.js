#!/usr/bin/env node
"use strict";

const M = require("../app/js/material-model.js");

let passed = 0;
let failed = 0;

function check(condition, name, detail) {
  if (condition) {
    passed += 1;
    console.log("PASS  " + name);
  } else {
    failed += 1;
    console.log("FAIL  " + name + (detail ? "  -> " + detail : ""));
  }
}

for (const test of M.productInvariantTests()) {
  check(test.pass, test.name);
}

const official = M.assessSource({
  host: "moe.gov.cn", authorKnown: true, original: true, date: "2026-08-01",
  exactExcerpt: true, supportsClaim: true, rights: "授权不明", teachingFit: "适配本科课堂",
});
check(official.provenance === "原始权威来源", "白名单只影响来源身份");
check(official.review === "机器初检", "机器识别不能替代人工审核");
check(official.allowedUse === "需教师确认", "未审核权威来源不能直接支撑公开事实");
check(official.rights === "授权不明" && official.teachingFit === "适配本科课堂", "版权和教学适配保持独立");
const repost = M.assessSource({
  host: "local.gov.cn", authorKnown: true, original: false, date: "2026-08-01",
  exactExcerpt: true, supportsClaim: true, rights: "公开引用",
});
check(repost.provenance === "可靠二手来源", "可信域名转载不冒充原始权威来源");

const before = M.evidenceCoverage([
  { evidence: ["source-a"] }, { evidence: [] }, { evidence: [] },
]);
const after = M.evidenceCoverage([
  { evidence: ["source-a"] }, { evidence: ["source-b"] }, { evidence: [] },
]);
check(before.rate === 33 && after.rate === 67, "挂接证据片段后覆盖率可计算", before.rate + " -> " + after.rate);

const broad = M.queryEstimate("科技创新", {});
const narrowed = M.queryEstimate("科技创新", { authority: "primary", type: "政策文件", rights: true });
check(narrowed < broad && narrowed > 0, "组合筛选能稳定缩小万级结果集", broad + " -> " + narrowed);

const farPage = M.explorerPage("科技创新", {}, 100, 20);
check(farPage.rows.length <= 20, "任意页只返回固定窗口", String(farPage.rows.length));
check(farPage.total > 1000 && farPage.pages > 50, "万级查询保留总量和总页数", JSON.stringify({ total: farPage.total, pages: farPage.pages }));
const officialPage = M.explorerPage("科技创新", { authority: "primary" }, 1, 20);
check(officialPage.rows.every((row) => row.authority === "原始权威来源"), "筛选计数与结果标签保持一致");
const zeroPage = M.explorerPage("不存在素材", {}, 1, 20);
check(zeroPage.total === 0 && zeroPage.rows.length === 0, "零结果状态可稳定复现并恢复");

const metrics = M.evaluateMetrics(M.metricDefinitions);
check(metrics.length === 10, "十项需求闭环指标已固化");
check(metrics.filter((m) => m.pass).length === 7, "指标页能识别当前三项产品缺口");
check(metrics.some((m) => m.id === "locateAtScale" && m.pass), "万级数据定位时间纳入验收");
check(metrics.some((m) => m.id === "zeroRecovery" && m.pass), "零结果恢复率纳入验收");
check(metrics.some((m) => m.id === "savedViewReturn" && m.pass), "保存视图任务恢复率纳入验收");

console.log("\n%d PASS, %d FAIL", passed, failed);
process.exit(failed ? 1 : 0);
