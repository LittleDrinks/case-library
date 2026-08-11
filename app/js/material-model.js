(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  root.MaterialDemoModel = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  const TRUSTED_HOSTS = ["gov.cn", "moe.gov.cn", "stats.gov.cn", "news.cn", "people.com.cn"];

  const materials = [
    {
      id: "mat-policy-01", role: "核心证据", title: "高等学校课程思政建设指导纲要",
      source: "教育部", host: "moe.gov.cn", date: "2020-06-01", type: "政策文件",
      authority: "原始权威来源", review: "机构已核验", rights: "公开引用",
      freshness: "现行", citedCases: 38, evidenceCount: 3,
      reason: "教育部原始发布，文号、发布日期和正文完整。",
      excerpt: "深入挖掘各类课程所蕴含的思想政治教育资源，实现全员全程全方位育人。",
    },
    {
      id: "mat-stat-01", role: "核心证据", title: "2025 年全国科技经费投入统计公报",
      source: "国家统计局", host: "stats.gov.cn", date: "2026-03-18", type: "统计数据",
      authority: "原始权威来源", review: "机构已核验", rights: "公开引用",
      freshness: "最新", citedCases: 12, evidenceCount: 4,
      reason: "国家统计局原始公报，指标口径和统计周期完整。",
      excerpt: "2025 年全国研究与试验发展经费投入保持稳定增长，基础研究投入占比继续提高。",
    },
    {
      id: "mat-case-01", role: "核心证据", title: "钱伟长：国家需要就是我的专业",
      source: "上海大学档案馆", host: "shu.edu.cn", date: "2024-09-12", type: "校史档案",
      authority: "原始权威来源", review: "学科已核验", rights: "校内使用",
      freshness: "稳定", citedCases: 21, evidenceCount: 5,
      reason: "校档案馆整理的一手史料，关键时间线已交叉核验。",
      excerpt: "面对国家需要，钱伟长多次调整研究方向，将个人选择与国家发展紧密相连。",
    },
    {
      id: "mat-theory-01", role: "核心证据", title: "科技创新与社会责任研究综述",
      source: "中国科学技术与社会研究会", host: "csts.org.cn", date: "2025-11-06", type: "学术论文",
      authority: "可靠二手来源", review: "教师已核验", rights: "摘要引用",
      freshness: "较新", citedCases: 9, evidenceCount: 2,
      reason: "有作者、参考文献和同行评议记录，但属于综合性二手研究。",
      excerpt: "技术创新的公共价值需要在科研伦理、社会需求与专业自主之间形成动态平衡。",
    },
    {
      id: "mat-video-01", role: "教学补充", title: "大国重器：实验室里的青年科研团队",
      source: "央视网", host: "cctv.com", date: "2026-05-04", type: "视频",
      authority: "可靠二手来源", review: "教师已核验", rights: "课堂播放",
      freshness: "最新", citedCases: 17, evidenceCount: 1,
      reason: "主流媒体采编，有明确采访对象；适合情境导入，不单独支撑统计结论。",
      excerpt: "青年科研人员围绕重大工程中的关键技术展开跨学科协作。",
    },
    {
      id: "mat-image-01", role: "教学补充", title: "上海大学校史建筑与实验室影像集",
      source: "上海大学融媒体中心", host: "shu.edu.cn", date: "2025-10-20", type: "图片",
      authority: "原始权威来源", review: "机构已核验", rights: "校内使用",
      freshness: "稳定", citedCases: 14, evidenceCount: 0,
      reason: "校内自有影像，拍摄信息完整；对外使用需再次确认肖像授权。",
      excerpt: "影像包含校史建筑、实验装置和师生科研活动场景。",
    },
    {
      id: "mat-view-01", role: "备选与反方", title: "效率优先是否必然促进科技创新",
      source: "高校学术公众号", host: "example.edu.cn", date: "2026-01-08", type: "评论",
      authority: "观点素材", review: "待学科核验", rights: "链接分享",
      freshness: "较新", citedCases: 2, evidenceCount: 1,
      reason: "作者身份可确认，但内容属于观点表达，只能作为课堂讨论材料。",
      excerpt: "过度强调短期量化产出，可能挤压基础研究与高风险探索的空间。",
    },
    {
      id: "mat-pending-01", role: "备选与反方", title: "某实验室成果转化率数据图",
      source: "行业自媒体", host: "example.com", date: "2023-04-02", type: "图片",
      authority: "待核验线索", review: "机器初检", rights: "授权不明",
      freshness: "可能过时", citedCases: 0, evidenceCount: 0,
      reason: "缺少原始数据链接、作者和统计口径，不得支撑公开案例事实。",
      excerpt: "图片声称部分高校成果转化率在三年内显著提升，但未给出样本和口径。",
    },
    {
      id: "mat-team-02", role: "核心证据", title: "青年科技人才跨学科协作状况调查",
      source: "中国科协创新战略研究院", host: "cast.org.cn", date: "2026-06-18", type: "调研报告",
      authority: "原始权威来源", review: "机构已核验", rights: "公开引用",
      freshness: "最新", citedCases: 6, evidenceCount: 3,
      reason: "研究机构原始调查报告，样本范围、问卷和统计口径可追溯。",
      excerpt: "受访青年科技人才中，跨机构或跨学科团队合作已成为解决复杂科研问题的重要组织方式。",
    },
    {
      id: "mat-class-02", role: "教学补充", title: "科研伦理课堂角色讨论卡",
      source: "上海大学教师发展中心", host: "shu.edu.cn", date: "2026-04-10", type: "案例集",
      authority: "原始权威来源", review: "教师已核验", rights: "校内使用",
      freshness: "最新", citedCases: 8, evidenceCount: 0,
      reason: "校内教学团队原创材料，适合课堂活动，不作为事实证据。",
      excerpt: "讨论卡设置科研负责人、青年研究者、资助机构和公众四种角色。",
    },
  ];

  const claims = [
    { id: "claim-1", text: "课程思政需要把价值塑造融入专业知识教学。", evidence: ["mat-policy-01"] },
    { id: "claim-2", text: "科研人员的专业选择会受到国家战略需求影响。", evidence: ["mat-case-01", "mat-theory-01"] },
    { id: "claim-3", text: "我国基础研究投入占比持续提高。", evidence: ["mat-stat-01"] },
    { id: "claim-4", text: "青年科研团队普遍采用跨学科协作方式。", evidence: [] },
    { id: "claim-5", text: "量化评价可能抑制高风险基础研究。", evidence: ["mat-view-01"] },
  ];

  const queues = [
    { id: "q-01", title: "科技日报：高校有组织科研观察", source: "科技日报", host: "stdaily.com", type: "报道", date: "2026-08-07", signal: "自动盯源", status: "待核验", duplicate: null, rights: "公开链接" },
    { id: "q-02", title: "2025 年全国科技经费投入统计公报（转载）", source: "地方政务网", host: "local.gov.cn", type: "统计数据", date: "2026-03-19", signal: "教师提交", status: "疑似重复", duplicate: "mat-stat-01", rights: "公开引用" },
    { id: "q-03", title: "高校实验室成果转化率数据图", source: "行业观察号", host: "example.com", type: "图片", date: "2026-08-06", signal: "AI 推荐", status: "高风险", duplicate: null, rights: "授权不明" },
    { id: "q-04", title: "科研伦理课堂讨论案例集", source: "校教师发展中心", host: "shu.edu.cn", type: "案例集", date: "2026-08-05", signal: "教师上传", status: "待核验", duplicate: null, rights: "校内使用" },
    { id: "q-05", title: "青年科技人才发展状况调查", source: "中国科协", host: "cast.org.cn", type: "调研报告", date: "2026-07-28", signal: "自动盯源", status: "待核验", duplicate: null, rights: "公开引用" },
  ];

  const metricDefinitions = [
    { id: "timeToEvidence", name: "首组可用证据时间", target: 5, unit: "分钟", direction: "max", current: 3.8, owner: "教师工作台" },
    { id: "coverage", name: "事实主张证据覆盖率", target: 85, unit: "%", direction: "min", current: 80, owner: "发布检查" },
    { id: "firstPass", name: "证据包一次审核通过率", target: 75, unit: "%", direction: "min", current: 72, owner: "审核队列" },
    { id: "dedupe", name: "重复素材合并率", target: 90, unit: "%", direction: "min", current: 91, owner: "采集入口" },
    { id: "invalidation", name: "失效来源复核时长", target: 24, unit: "小时", direction: "max", current: 18, owner: "影响处置" },
    { id: "reuse", name: "优质证据包平均复用", target: 3, unit: "次", direction: "min", current: 2.7, owner: "资源检索" },
    { id: "citationClicks", name: "完成一次引用操作数", target: 5, unit: "次", direction: "max", current: 4, owner: "证据包" },
    { id: "locateAtScale", name: "万级库目标素材定位时间", target: 45, unit: "秒", direction: "max", current: 38, owner: "素材掌控台" },
    { id: "zeroRecovery", name: "零结果查询恢复率", target: 80, unit: "%", direction: "min", current: 86, owner: "素材掌控台" },
    { id: "savedViewReturn", name: "保存视图任务恢复率", target: 90, unit: "%", direction: "min", current: 94, owner: "素材掌控台" },
  ];

  function hostTrusted(host) {
    return TRUSTED_HOSTS.some(function (h) { return host === h || host.endsWith("." + h); });
  }

  function assessSource(source) {
    const primary = hostTrusted(source.host || "");
    const provenance = primary && source.original ? "原始权威来源" : source.authorKnown ? "可靠二手来源" : "待核验线索";
    const document = source.authorKnown && source.date && source.original ? "完整" : source.date ? "部分完整" : "缺失";
    const evidenceFit = source.exactExcerpt && source.supportsClaim ? "直接支持" : source.exactExcerpt ? "仅作背景" : "尚未判断";
    const review = source.humanApproved ? "机构已核验" : "机器初检";
    const allowedUse = review === "机构已核验" && evidenceFit === "直接支持" ? "可支撑事实" : provenance === "待核验线索" ? "发现线索" : "需教师确认";
    return { provenance, document, evidenceFit, review, rights: source.rights || "授权不明", teachingFit: source.teachingFit || "未评价", allowedUse };
  }

  function routeIngestion(source) {
    if (source.humanApproved && source.reviewPassed) return "catalog";
    if (source.addedToCase) return "personal";
    return "candidate";
  }

  function evidenceCoverage(items) {
    const factual = items.filter(function (c) { return c.kind !== "opinion"; });
    const supported = factual.filter(function (c) { return Array.isArray(c.evidence) && c.evidence.length > 0; });
    return { total: factual.length, supported: supported.length, rate: factual.length ? Math.round(supported.length / factual.length * 100) : 100 };
  }

  function metricPass(metric) {
    return metric.direction === "max" ? metric.current <= metric.target : metric.current >= metric.target;
  }

  function evaluateMetrics(metrics) {
    return metrics.map(function (metric) { return Object.assign({}, metric, { pass: metricPass(metric) }); });
  }

  function queryEstimate(query, filters) {
    let total = 12480;
    const q = (query || "").trim();
    if (/无结果|不存在素材/.test(q)) return 0;
    if (q) total = Math.max(6, Math.round(total * Math.max(.018, .23 - Math.min(q.length, 14) * .009)));
    if (filters && filters.authority) total = Math.round(total * ({ primary: .24, secondary: .33, pending: .13 }[filters.authority] || 1));
    if (filters && filters.type) total = Math.round(total * .18);
    if (filters && filters.course) total = Math.round(total * .27);
    if (filters && filters.rights) total = Math.round(total * .62);
    return Math.max(total, 1);
  }

  function explorerPage(query, filters, page, size) {
    const total = queryEstimate(query, filters);
    const start = (page - 1) * size;
    const rows = [];
    const typePool = ["政策文件", "统计数据", "学术论文", "校史档案", "视频", "案例集"];
    const sourcePool = ["教育部", "国家统计局", "新华社", "上海大学", "中国科协", "核心期刊"];
    for (let i = 0; i < Math.min(size, Math.max(total - start, 0)); i++) {
      const n = start + i + 1;
      const base = materials[(n - 1) % materials.length];
      rows.push(Object.assign({}, base, {
        id: "search-" + n,
        title: (query ? query + " · " : "") + (n <= materials.length ? base.title : typePool[n % typePool.length] + "专题材料 " + String(n).padStart(5, "0")),
        source: n <= materials.length ? base.source : sourcePool[n % sourcePool.length],
        type: n <= materials.length ? base.type : typePool[n % typePool.length],
        score: Math.max(62, 98 - (n % 31)),
        citedCases: (n * 7) % 43,
      }));
      if (filters && filters.authority) rows[rows.length - 1].authority = { primary: "原始权威来源", secondary: "可靠二手来源", pending: "待核验线索" }[filters.authority];
      if (filters && filters.type) rows[rows.length - 1].type = filters.type;
      if (filters && filters.rights) rows[rows.length - 1].rights = "公开引用";
    }
    return { total, page, size, pages: Math.ceil(total / size), rows };
  }

  function productInvariantTests() {
    const officialButUnreviewed = assessSource({ host: "moe.gov.cn", date: "2026-01-01", original: true, authorKnown: true, exactExcerpt: true, supportsClaim: true, rights: "公开引用" });
    const rightsA = assessSource({ host: "moe.gov.cn", date: "2026-01-01", original: true, authorKnown: true, rights: "禁止下载" });
    const rightsB = assessSource({ host: "moe.gov.cn", date: "2026-01-01", original: true, authorKnown: true, rights: "公开引用" });
    const coverage = evidenceCoverage([{ evidence: ["a"] }, { evidence: [] }, { evidence: ["b"] }, { kind: "opinion", evidence: [] }]);
    const trustedRepost = assessSource({ host: "local.gov.cn", authorKnown: true, original: false, date: "2026-01-01", exactExcerpt: true, supportsClaim: true });
    return [
      { name: "自动发现只进入候选区", pass: routeIngestion({ automated: true }) === "candidate" },
      { name: "教师临时素材进入案例私人区", pass: routeIngestion({ addedToCase: true }) === "personal" },
      { name: "公共入库必须经过人工审核", pass: routeIngestion({ humanApproved: true, reviewPassed: true }) === "catalog" },
      { name: "权威域名不等于已审核证据", pass: officialButUnreviewed.review === "机器初检" && officialButUnreviewed.allowedUse !== "可支撑事实" },
      { name: "版权状态不改变来源权威性", pass: rightsA.provenance === rightsB.provenance && rightsA.rights !== rightsB.rights },
      { name: "覆盖率只统计有证据片段的事实主张", pass: coverage.total === 3 && coverage.supported === 2 && coverage.rate === 67 },
      { name: "万级检索仅生成当前页数据", pass: explorerPage("科技创新", {}, 200, 20).rows.length <= 20 },
      { name: "跨页选择以查询范围表达", pass: queryEstimate("科技创新", { authority: "primary" }) > 20 },
      { name: "可信域名转载不冒充原始来源", pass: trustedRepost.provenance === "可靠二手来源" },
    ];
  }

  return {
    materials, claims, queues, metricDefinitions,
    assessSource, routeIngestion, evidenceCoverage, evaluateMetrics,
    queryEstimate, explorerPage, productInvariantTests,
  };
});
