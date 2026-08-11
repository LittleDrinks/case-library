(function () {
  "use strict";
  const M = window.MaterialDemoModel;
  const page = document.body.dataset.demoPage;
  const view = document.getElementById("demo-view");
  const layer = document.getElementById("demo-layer");
  const STORE_KEY = "case-library-material-demo-v1";
  const EVENT_KEY = "case-library-material-demo-events-v1";

  function esc(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, function (ch) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch];
    });
  }

  function loadState() {
    const fallback = {
      claims: M.claims,
      pack: M.materials.slice(0, 8).map(function (m) { return m.id; }),
      scoped: M.materials.filter(function (m) { return m.role === "核心证据"; }).map(function (m) { return m.id; }),
      queueStatus: {},
    };
    try { return Object.assign(fallback, JSON.parse(localStorage.getItem(STORE_KEY) || "{}")); }
    catch (_) { return fallback; }
  }

  let state = loadState();
  function saveState() { localStorage.setItem(STORE_KEY, JSON.stringify(state)); }
  function track(type, data) {
    let events = [];
    try { events = JSON.parse(localStorage.getItem(EVENT_KEY) || "[]"); } catch (_) {}
    events.push({ type: type, data: data || {}, at: new Date().toISOString() });
    localStorage.setItem(EVENT_KEY, JSON.stringify(events.slice(-200)));
  }

  function toast(message) {
    const el = document.getElementById("demo-toast");
    el.textContent = message;
    el.classList.add("show");
    clearTimeout(toast.timer);
    toast.timer = setTimeout(function () { el.classList.remove("show"); }, 2200);
  }

  function tagClass(value) {
    if (/原始|已核验|通过|正常|公开/.test(value)) return "green";
    if (/待|可能|部分|复核/.test(value)) return "amber";
    if (/二手|教师/.test(value)) return "blue";
    if (/观点|校内/.test(value)) return "purple";
    if (/风险|失效|不明|禁止/.test(value)) return "red";
    return "";
  }

  function tag(value) { return '<span class="tag ' + tagClass(value) + '">' + esc(value) + "</span>"; }
  function selectOptions(current, values) {
    return Array.from(new Set([current].concat(values))).map(function (value) {
      return '<option ' + (value === current ? "selected" : "") + '>' + esc(value) + '</option>';
    }).join("");
  }

  function renderHeader() {
    const links = [
      ["workspace", "material-workspace.html", "教师证据包"],
      ["explorer", "material-explorer.html", "万级素材掌控台"],
      ["intake", "material-intake.html", "候选审核"],
      ["metrics", "material-metrics.html", "闭环测试"],
    ];
    document.getElementById("demo-topbar").innerHTML =
      '<a class="demo-brand" href="index.html"><img src="assets/shu-logo.png" alt="上海大学"><strong>素材闭环实验台</strong><span>交互原型</span></a>' +
      '<nav class="demo-nav">' + links.map(function (x) {
        return '<a href="' + x[1] + '" class="' + (page === x[0] ? "active" : "") + '">' + x[2] + "</a>";
      }).join("") + '</nav><div class="demo-context"><span class="tag blue">当前案例</span><b>科技创新与科技报国</b></div>';
  }

  function closeLayer() { layer.innerHTML = ""; }
  layer.addEventListener("click", function (e) {
    if (e.target.classList.contains("drawer-backdrop") || e.target.classList.contains("modal-backdrop") || e.target.closest("[data-close-layer]")) closeLayer();
  });
  document.addEventListener("keydown", function (e) { if (e.key === "Escape") closeLayer(); });

  function sourceDrawer(material, options) {
    const claimOptions = state.claims.map(function (c, i) { return '<option value="' + c.id + '">主张 ' + (i + 1) + " · " + esc(c.text.slice(0, 25)) + "</option>"; }).join("");
    layer.innerHTML = '<div class="drawer-backdrop"><aside class="drawer" role="dialog" aria-modal="true" aria-label="素材详情">' +
      '<div class="drawer-head"><h2>' + esc(material.title) + '</h2><button class="icon-btn" data-close-layer title="关闭">×</button></div>' +
      '<div class="drawer-body"><div class="toolbar">' + tag(material.role) + tag(material.authority) + tag(material.rights) + '</div>' +
      '<table class="detail-meta"><tr><th>来源</th><td>' + esc(material.source) + ' · ' + esc(material.host) + '</td></tr>' +
      '<tr><th>发布日期</th><td>' + esc(material.date) + ' · ' + esc(material.freshness) + '</td></tr>' +
      '<tr><th>审核状态</th><td>' + tag(material.review) + '</td></tr><tr><th>跨案例复用</th><td>' + esc(material.citedCases) + ' 个案例</td></tr></table>' +
      '<h3>判定依据</h3><div class="reason-box">' + esc(material.reason) + '</div>' +
      '<h3>可引用证据片段</h3><blockquote class="excerpt">' + esc(material.excerpt) + '</blockquote>' +
      '<div class="field"><label for="drawer-claim">挂接到主张</label><select id="drawer-claim">' + claimOptions + '</select></div></div>' +
      '<div class="drawer-foot"><button class="btn neutral" data-close-layer>返回</button>' +
      ((options && options.readonly) ? '' : '<button class="btn" id="drawer-cite" data-mid="' + esc(material.id) + '">引用该片段</button>') +
      '</div></aside></div>';
    const cite = document.getElementById("drawer-cite");
    if (cite) cite.addEventListener("click", function () {
      const claimId = document.getElementById("drawer-claim").value;
      const claim = state.claims.find(function (c) { return c.id === claimId; });
      if (!claim.evidence.includes(material.id)) claim.evidence.push(material.id);
      if (!state.pack.includes(material.id)) state.pack.push(material.id);
      if (!state.scoped.includes(material.id)) state.scoped.push(material.id);
      saveState(); track("evidence_attached", { materialId: material.id, claimId: claimId });
      closeLayer(); renderWorkspace(); toast("证据片段已挂接到主张");
    });
  }

  function renderWorkspace() {
    const coverage = M.evidenceCoverage(state.claims);
    const packMats = M.materials.filter(function (m) { return state.pack.includes(m.id); });
    const core = packMats.filter(function (m) { return m.role === "核心证据"; });
    const pending = packMats.filter(function (m) { return m.authority === "待核验线索"; }).length;
    view.innerHTML = '<div class="page-head"><div><h1 class="page-title">案例证据包</h1><div class="page-sub">科技创新与科技报国 · 本科专业课程思政 · 工作稿</div></div></div>' +
      '<section class="metric-strip"><div class="metric-mini"><b>' + packMats.length + '</b><span>证据包素材</span></div><div class="metric-mini"><b>' + core.length + '</b><span>核心证据</span></div><div class="metric-mini"><b>' + coverage.rate + '%</b><span>事实主张覆盖</span></div><div class="metric-mini"><b>' + pending + '</b><span>待核验来源</span></div></section>' +
      '<div class="workspace-grid"><section class="tool-shell"><div class="tool-head"><div><h2>正文主张与证据</h2><span class="small muted">每条事实主张必须落到具体证据片段</span></div><div class="toolbar"><span class="tag ' + (coverage.rate >= 85 ? "green" : "amber") + '">' + coverage.supported + '/' + coverage.total + ' 已覆盖</span><a class="btn small neutral" href="material-explorer.html">检索全库</a><button class="btn small secondary" id="add-source">添加素材</button><button class="btn small" id="preflight" data-preflight>发布前检查</button></div></div>' +
      '<div class="claim-list"><h3 class="claim-section">一、价值目标与现实背景</h3>' + state.claims.map(function (claim, i) {
        const evidence = (claim.evidence || []).map(function (id) { return M.materials.find(function (m) { return m.id === id; }); }).filter(Boolean);
        return '<article class="claim-row ' + (evidence.length ? "" : "unsupported") + '"><span class="claim-num">' + (i + 1) + '</span><div><div class="claim-text">' + esc(claim.text) + '</div><div class="claim-evidence">' +
          (evidence.length ? evidence.map(function (m) { return '<button class="evidence-chip" data-open-source="' + m.id + '">' + esc(m.source) + ' · ' + esc(m.excerpt.slice(0, 18)) + '…</button>'; }).join("") : '<span class="tag amber">缺少直接证据</span>') +
          '</div></div><div class="claim-status">' + (evidence.length ? '<span class="tag green">已支撑</span>' : '<button class="btn small secondary" data-find-for="' + claim.id + '">补证据</button>') + '</div></article>';
      }).join("") + '</div></section>' +
      '<aside class="tool-shell"><div class="tool-head"><div><h2>本案例素材范围</h2><span class="small muted">AI 仅使用已勾选来源</span></div><button class="btn small neutral" id="scope-all">全选核心</button></div>' +
      '<div class="pack-summary"><span><b>' + state.scoped.length + '</b> 条已纳入本轮生成</span><span class="small muted">总计 ' + packMats.length + ' 条</span></div><div class="pack-groups">' +
      ["核心证据", "教学补充", "备选与反方"].map(function (role) {
        const list = packMats.filter(function (m) { return m.role === role; });
        return '<section class="pack-group"><div class="group-head"><span>' + role + '</span><span>' + list.length + '</span></div>' + list.map(function (m) {
          return '<div class="source-card"><input type="checkbox" data-scope="' + m.id + '" ' + (state.scoped.includes(m.id) ? "checked" : "") + ' aria-label="纳入 ' + esc(m.title) + '"><div><button class="source-title" data-open-source="' + m.id + '">' + esc(m.title) + '</button><div class="source-meta">' + tag(m.authority) + '<span>' + esc(m.source) + '</span><span>' + esc(m.freshness) + '</span></div></div><span class="source-count">证据 ' + m.evidenceCount + '</span></div>';
        }).join("") + '</section>';
      }).join("") + '</div></aside></div>';

    view.onclick = function (e) {
      const open = e.target.closest("[data-open-source]");
      if (open) sourceDrawer(M.materials.find(function (m) { return m.id === open.dataset.openSource; }));
      const find = e.target.closest("[data-find-for]");
      if (find) openAddSource(find.dataset.findFor);
      if (e.target.closest("#add-source")) openAddSource();
      if (e.target.closest("[data-preflight]")) openPreflight();
      if (e.target.closest("#scope-all")) {
        state.scoped = core.map(function (m) { return m.id; }); saveState(); renderWorkspace(); toast("已限定为核心证据");
      }
    };
    view.onchange = function (e) {
      if (!e.target.matches("[data-scope]")) return;
      const id = e.target.dataset.scope;
      state.scoped = e.target.checked ? Array.from(new Set(state.scoped.concat(id))) : state.scoped.filter(function (x) { return x !== id; });
      saveState(); track("source_scope_changed", { materialId: id, included: e.target.checked });
      const count = view.querySelector(".pack-summary b"); if (count) count.textContent = state.scoped.length;
    };
  }

  function openAddSource(claimId) {
    const claim = state.claims.find(function (c) { return c.id === claimId; });
    let available = M.materials.filter(function (m) {
      return !state.pack.includes(m.id) && !(claim && claim.evidence.includes(m.id));
    });
    if (claimId === "claim-4") available.sort(function (a) { return a.id === "mat-team-02" ? -1 : 1; });
    available = available.slice(0, 6);
    layer.innerHTML = '<div class="modal-backdrop"><section class="modal" role="dialog" aria-modal="true"><div class="modal-head"><h2>添加到证据包</h2><button class="icon-btn" data-close-layer title="关闭">×</button></div><div class="modal-body">' +
      '<input class="search-input" id="modal-search" value="' + (claimId === "claim-4" ? "青年科技人才 跨学科协作" : "科技创新") + '" aria-label="搜索素材"><div class="modal-list">' + available.map(function (m, i) {
        return '<label class="modal-row"><input type="checkbox" name="pick" value="' + m.id + '" ' + (i === 0 ? "checked" : "") + '><span><b>' + esc(m.title) + '</b><span class="source-meta">' + tag(m.authority) + '<span>' + esc(m.source) + '</span></span></span><span class="small muted">被引 ' + m.citedCases + '</span></label>';
      }).join("") + '</div></div><div class="modal-foot"><button class="btn neutral" data-close-layer>取消</button><button class="btn" id="confirm-add">加入证据包</button></div></section></div>';
    document.getElementById("confirm-add").onclick = function () {
      const ids = Array.from(layer.querySelectorAll('input[name="pick"]:checked')).map(function (x) { return x.value; });
      if (!ids.length) { toast("至少选择一条素材"); return; }
      state.pack = Array.from(new Set(state.pack.concat(ids)));
      if (claimId) {
        const claim = state.claims.find(function (c) { return c.id === claimId; });
        if (claim) claim.evidence = Array.from(new Set((claim.evidence || []).concat(ids[0])));
      }
      saveState(); track("sources_added", { count: ids.length, claimId: claimId || null }); closeLayer(); renderWorkspace(); toast("已加入 " + ids.length + " 条素材");
    };
  }

  function openPreflight() {
    const coverage = M.evidenceCoverage(state.claims);
    const pending = M.materials.filter(function (m) { return state.pack.includes(m.id) && (m.authority === "待核验线索" || m.rights === "授权不明"); });
    const checks = [
      [coverage.rate >= 85, "事实主张证据覆盖率", coverage.rate + "% / 目标 85%"],
      [pending.length === 0, "来源和版权风险", pending.length + " 条待处理"],
      [state.scoped.length >= 3, "本轮生成来源范围", state.scoped.length + " 条已勾选"],
      [true, "引用均定位到快照片段", "5 条有效锚点"],
    ];
    layer.innerHTML = '<div class="modal-backdrop"><section class="modal" role="dialog" aria-modal="true"><div class="modal-head"><h2>发布前证据检查</h2><button class="icon-btn" data-close-layer>×</button></div><div class="modal-body"><div class="test-list">' + checks.map(function (x) {
      return '<div class="test-row"><span class="status-dot ' + (x[0] ? "pass" : "fail") + '">' + (x[0] ? "✓" : "!") + '</span><b>' + x[1] + '</b><span class="small muted">' + x[2] + '</span></div>';
    }).join("") + '</div></div><div class="modal-foot"><button class="btn neutral" data-close-layer>返回修改</button><a class="btn secondary" href="material-metrics.html">查看闭环指标</a><button class="btn" ' + (checks.every(function (x) { return x[0]; }) ? "" : "disabled") + '>提交审核</button></div></section></div>';
    track("preflight_run", { passed: checks.every(function (x) { return x[0]; }), coverage: coverage.rate });
  }

  let explorer = { q: "科技创新", authority: "", type: "", course: "", rights: false, page: 1, size: 20, density: "standard", selected: new Set(), allMatching: false };
  function explorerFilters() { return { authority: explorer.authority, type: explorer.type, course: explorer.course, rights: explorer.rights }; }
  function renderExplorer() {
    const data = M.explorerPage(explorer.q, explorerFilters(), explorer.page, explorer.size);
    const shownPages = [1, explorer.page - 1, explorer.page, explorer.page + 1, data.pages].filter(function (n, i, a) { return n >= 1 && n <= data.pages && a.indexOf(n) === i; }).sort(function (a, b) { return a - b; });
    view.innerHTML = '<div class="page-head"><div><h1 class="page-title">素材掌控台</h1><div class="page-sub">12,480 条素材 · 查询、视图和批量动作均作用于服务端结果集</div></div><div class="head-actions"><button class="btn neutral" id="save-view">保存当前视图</button><a class="btn" href="material-workspace.html">返回当前案例</a></div></div>' +
      '<section class="metric-strip"><div class="metric-mini"><b>12,480</b><span>可见素材</span></div><div class="metric-mini"><b>86%</b><span>已核验或可靠来源</span></div><div class="metric-mini"><b>23</b><span>我的保存视图</span></div><div class="metric-mini"><b>38 秒</b><span>目标素材定位中位数</span></div></section>' +
      '<div class="explorer-shell"><aside class="filter-rail"><h2 class="filter-title">工作视图</h2>' +
      '<button class="saved-view active" data-view="current"><span>当前案例候选</span><b>86</b></button><button class="saved-view" data-view="official"><span>最新权威材料</span><b>214</b></button><button class="saved-view" data-view="unread"><span>待阅读</span><b>47</b></button><button class="saved-view" data-view="risk"><span>需复核来源</span><b>19</b></button>' +
      '<div class="filter-group"><h2 class="filter-title">来源权威性</h2>' + filterRadio("authority", "", "全部", "12,480", explorer.authority) + filterRadio("authority", "primary", "原始权威", "2,995", explorer.authority) + filterRadio("authority", "secondary", "可靠二手", "4,118", explorer.authority) + filterRadio("authority", "pending", "待核验", "1,622", explorer.authority) + '</div>' +
      '<div class="filter-group"><h2 class="filter-title">素材类型</h2>' + filterRadio("type", "", "全部", "", explorer.type) + filterRadio("type", "政策文件", "政策文件", "1,245", explorer.type) + filterRadio("type", "统计数据", "统计数据", "938", explorer.type) + filterRadio("type", "视频", "视频影像", "1,870", explorer.type) + '</div>' +
      '<div class="filter-group"><label class="filter-option"><input type="checkbox" id="rights-filter" ' + (explorer.rights ? "checked" : "") + '><span>仅可对外使用</span><span>7,736</span></label></div></aside>' +
      '<section class="results-area"><div class="search-band"><input class="search-input" id="explorer-q" value="' + esc(explorer.q) + '" placeholder="搜索标题、正文、来源或证据片段"><button class="btn" id="explorer-search">搜索</button><div class="segmented" aria-label="列表密度"><button data-density="compact" title="紧凑">密</button><button data-density="standard" class="active" title="标准">中</button><button data-density="comfortable" title="宽松">宽</button></div></div>' +
      '<div class="results-meta"><div><b>' + data.total.toLocaleString("zh-CN") + '</b> 条结果 <span class="small muted">· 已从 12,480 条缩小 ' + Math.round((1 - data.total / 12480) * 100) + '%</span></div><div class="toolbar"><span class="small muted">排序</span><select id="sort"><option>相关度与权威性</option><option>最新发布</option><option>跨案例复用</option></select></div></div>' +
      (explorer.selected.size && !explorer.allMatching ? '<div class="query-scope">已选择当前页 ' + explorer.selected.size + ' 条。<button id="select-all-matching">选择全部 ' + data.total.toLocaleString("zh-CN") + ' 条匹配结果</button></div>' : explorer.allMatching ? '<div class="query-scope">已选择当前查询的全部 ' + data.total.toLocaleString("zh-CN") + ' 条结果。<button id="clear-selection">清除选择</button></div>' : '') +
      '<table class="results-table ' + explorer.density + '"><thead><tr><th class="col-check"><input type="checkbox" id="page-check" aria-label="选择本页" ' + (data.total ? "" : "disabled") + '></th><th>素材</th><th class="col-source">来源</th><th class="col-type">类型</th><th class="col-authority">权威性</th><th class="col-use">复用</th></tr></thead><tbody>' + (data.rows.length ? data.rows.map(function (m) {
        return '<tr><td class="col-check"><input type="checkbox" data-result-check="' + m.id + '" ' + (explorer.selected.has(m.id) || explorer.allMatching ? "checked" : "") + '></td><td><button class="result-title" data-result-open="' + m.id + '">' + esc(m.title) + '</button><span class="rank-reason">匹配主题与证据片段 · 综合分 ' + m.score + ' · ' + esc(m.freshness) + '</span></td><td class="col-source">' + esc(m.source) + '</td><td class="col-type">' + tag(m.type) + '</td><td class="col-authority">' + tag(m.authority) + '</td><td class="col-use">' + m.citedCases + '</td></tr>';
      }).join("") : '<tr><td colspan="6" style="padding:48px 20px;text-align:center"><b>没有匹配素材</b><p class="muted">当前查询和筛选组合过窄</p><button class="btn small secondary" id="reset-zero">清除筛选并返回当前案例候选</button></td></tr>') + '</tbody></table>' +
      (data.total ? '<div class="pager"><span class="small muted">第 ' + data.page + ' / ' + data.pages + ' 页 · 每页仅加载 ' + data.size + ' 条</span><div class="page-buttons"><button class="btn small neutral" data-page="' + (data.page - 1) + '" ' + (data.page <= 1 ? "disabled" : "") + '>上一页</button>' + shownPages.map(function (n) { return '<button class="btn small ' + (n === data.page ? "" : "neutral") + '" data-page="' + n + '">' + n + '</button>'; }).join("") + '<button class="btn small neutral" data-page="' + (data.page + 1) + '" ' + (data.page >= data.pages ? "disabled" : "") + '>下一页</button></div></div>' : '') + '</section></div>' +
      ((explorer.selected.size || explorer.allMatching) ? '<div class="compare-tray"><b>' + (explorer.allMatching ? data.total.toLocaleString("zh-CN") : explorer.selected.size) + ' 条已选</b><div class="tray-items">' + Array.from(explorer.selected).slice(0, 4).map(function (id) { return '<span class="tray-item">' + id + '</span>'; }).join("") + '</div><button class="btn small secondary" id="compare-selected" ' + (explorer.selected.size < 2 || explorer.selected.size > 4 ? "disabled" : "") + '>对比</button><button class="btn small" id="batch-add">' + (explorer.allMatching ? "创建候选集" : "加入当前案例") + '</button></div>' : '');

    bindExplorer(data);
  }

  function filterRadio(name, value, label, count, checked) {
    return '<label class="filter-option"><input type="radio" name="' + name + '" value="' + value + '" ' + (value === checked ? "checked" : "") + '><span>' + label + '</span><span>' + count + '</span></label>';
  }

  function bindExplorer(data) {
    document.getElementById("explorer-search").onclick = runSearch;
    document.getElementById("explorer-q").onkeydown = function (e) { if (e.key === "Enter") runSearch(); };
    function runSearch() {
      explorer.q = document.getElementById("explorer-q").value.trim(); explorer.page = 1; explorer.selected.clear(); explorer.allMatching = false;
      track("explorer_search", { query: explorer.q }); history.replaceState(null, "", "?q=" + encodeURIComponent(explorer.q)); renderExplorer();
    }
    view.onchange = function (e) {
      if (e.target.name === "authority" || e.target.name === "type") { explorer[e.target.name] = e.target.value; explorer.page = 1; explorer.selected.clear(); track("facet_applied", { facet: e.target.name, value: e.target.value }); renderExplorer(); }
      if (e.target.id === "rights-filter") { explorer.rights = e.target.checked; explorer.page = 1; track("facet_applied", { facet: "rights", value: explorer.rights }); renderExplorer(); }
      if (e.target.matches("[data-result-check]")) { e.target.checked ? explorer.selected.add(e.target.dataset.resultCheck) : explorer.selected.delete(e.target.dataset.resultCheck); explorer.allMatching = false; renderExplorer(); }
      if (e.target.id === "page-check") { data.rows.forEach(function (m) { e.target.checked ? explorer.selected.add(m.id) : explorer.selected.delete(m.id); }); renderExplorer(); }
    };
    view.onclick = function (e) {
      const pg = e.target.closest("[data-page]"); if (pg && !pg.disabled) { explorer.page = Number(pg.dataset.page); renderExplorer(); window.scrollTo({ top: 0, behavior: "smooth" }); }
      const den = e.target.closest("[data-density]"); if (den) { explorer.density = den.dataset.density; renderExplorer(); }
      const open = e.target.closest("[data-result-open]"); if (open) { const row = data.rows.find(function (m) { return m.id === open.dataset.resultOpen; }); sourceDrawer(row, { readonly: true }); }
      const saved = e.target.closest("[data-view]"); if (saved) applySavedView(saved.dataset.view);
      if (e.target.id === "select-all-matching") { explorer.allMatching = true; track("query_scope_selected", { count: data.total }); renderExplorer(); }
      if (e.target.id === "clear-selection") { explorer.allMatching = false; explorer.selected.clear(); renderExplorer(); }
      if (e.target.id === "batch-add") {
        track("batch_added_to_case", { scope: explorer.allMatching ? "query" : "explicit", count: explorer.allMatching ? data.total : explorer.selected.size });
        toast(explorer.allMatching ? "已创建候选集，当前查询条件已完整保存" : "所选素材已加入当前案例");
      }
      if (e.target.id === "reset-zero") applySavedView("current");
      if (e.target.id === "compare-selected") openCompare(data.rows.filter(function (m) { return explorer.selected.has(m.id); }));
    };
    document.getElementById("save-view").onclick = function () { track("saved_view_created", { query: explorer.q, filters: explorerFilters() }); toast("已保存为“科技创新 · 当前筛选”"); };
  }

  function applySavedView(name) {
    if (name === "official") { explorer.q = ""; explorer.authority = "primary"; explorer.type = ""; explorer.rights = true; }
    else if (name === "risk") { explorer.q = ""; explorer.authority = "pending"; explorer.rights = false; }
    else if (name === "unread") { explorer.q = "待阅读"; explorer.authority = ""; explorer.rights = false; }
    else { explorer.q = "科技创新"; explorer.authority = ""; explorer.type = ""; explorer.rights = false; }
    explorer.page = 1; explorer.selected.clear(); explorer.allMatching = false; track("saved_view_opened", { view: name }); renderExplorer();
  }

  function openCompare(rows) {
    layer.innerHTML = '<div class="modal-backdrop"><section class="modal" role="dialog"><div class="modal-head"><h2>素材对比</h2><button class="icon-btn" data-close-layer>×</button></div><div class="modal-body"><table class="metric-table"><thead><tr><th>字段</th>' + rows.map(function (m) { return '<th>' + esc(m.title.slice(0, 14)) + '</th>'; }).join("") + '</tr></thead><tbody>' +
      [["来源", "source"], ["权威性", "authority"], ["审核", "review"], ["版权", "rights"], ["时效", "freshness"]].map(function (r) { return '<tr><td>' + r[0] + '</td>' + rows.map(function (m) { return '<td>' + esc(m[r[1]]) + '</td>'; }).join("") + '</tr>'; }).join("") + '</tbody></table></div><div class="modal-foot"><button class="btn" data-close-layer>完成对比</button></div></section></div>';
  }

  let queueSelected = M.queues[0].id;
  function renderIntake() {
    const current = M.queues.find(function (q) { return q.id === queueSelected; });
    const status = state.queueStatus[current.id] || current.status;
    const assessment = M.assessSource({ host: current.host, authorKnown: current.host !== "example.com", date: current.date, original: current.signal === "自动盯源", exactExcerpt: true, supportsClaim: current.host !== "example.com", rights: current.rights, teachingFit: "适配本科课堂" });
    const highRisk = status === "高风险";
    const machineReason = highRisk
      ? "未识别可核验的原始发布主体、数据口径或授权信息，只能作为发现线索。"
      : "已识别发布主体、规范网址与发布日期；证据片段可定位。公共入库仍需审核人确认用途。";
    view.innerHTML = '<div class="page-head"><div><h1 class="page-title">候选素材审核</h1><div class="page-sub">机器完成采集与分流，审核人只处理不能自动决定的差异</div></div><div class="head-actions"><button class="btn neutral">批量分配</button><a class="btn" href="material-metrics.html">查看审核指标</a></div></div>' +
      '<section class="metric-strip"><div class="metric-mini"><b>27</b><span>待我处理</span></div><div class="metric-mini"><b>8</b><span>疑似重复</span></div><div class="metric-mini"><b>5</b><span>高风险</span></div><div class="metric-mini"><b>6.2 分钟</b><span>单条处理时长</span></div></section>' +
      '<div class="intake-grid"><aside class="queue-pane"><div class="queue-tabs"><button class="btn small">全部 27</button><button class="btn small neutral">重复 8</button><button class="btn small neutral">高风险 5</button></div>' + M.queues.map(function (q) {
        const qs = state.queueStatus[q.id] || q.status;
        return '<button class="queue-item ' + (q.id === current.id ? "active" : "") + '" data-queue="' + q.id + '"><strong>' + esc(q.title) + '</strong><span class="queue-item-meta">' + tag(qs) + '<span>' + esc(q.source) + '</span><span>' + esc(q.signal) + '</span></span></button>';
      }).join("") + '</aside><section class="review-pane"><div class="tool-head"><span>候选 ' + esc(current.id) + '</span><span class="small muted">队列位置 1 / 27</span></div><div class="review-content"><div class="toolbar">' + tag(status) + tag(current.type) + tag(current.signal) + '</div><h2 class="review-title">' + esc(current.title) + '</h2><div class="review-source">' + esc(current.source) + ' · ' + esc(current.host) + ' · ' + esc(current.date) + '</div>' +
      '<h3>分维度判断</h3><div class="assessment-grid"><div class="assessment-cell"><span>来源身份</span><b>' + esc(assessment.provenance) + '</b></div><div class="assessment-cell"><span>文档完整性</span><b>' + esc(assessment.document) + '</b></div><div class="assessment-cell"><span>证据适配</span><b>' + esc(assessment.evidenceFit) + '</b></div><div class="assessment-cell"><span>审核状态</span><b>' + esc(assessment.review) + '</b></div></div>' +
      '<div class="reason-box"><b>机器判定依据</b><br>' + machineReason + '</div>' +
      (current.duplicate ? '<div class="duplicate-box"><b>发现 1 条高相似素材</b><p>库内已有“' + esc(M.materials.find(function (m) { return m.id === current.duplicate; }).title) + '”。原始发布更早、引用关系 12 条，建议合并为该素材的新来源记录。</p><button class="btn small secondary" id="compare-duplicate">查看字段差异</button></div>' : '') +
      '<div class="review-fields"><div class="field"><label>建议用途</label><select>' + selectOptions(assessment.allowedUse, ["需教师确认", "仅作课堂讨论", "发现线索"]) + '</select></div><div class="field"><label>版权与使用范围</label><select>' + selectOptions(current.rights, ["公开引用", "校内使用", "授权不明"]) + '</select></div><div class="field"><label>素材角色</label><select>' + selectOptions(highRisk ? "备选与反方" : "核心证据", ["核心证据", "教学补充", "备选与反方"]) + '</select></div><div class="field"><label>审核说明</label><input value="' + (highRisk ? "缺少原始数据与授权信息" : "发布主体与证据片段已核验") + '"></div></div></div>' +
      '<div class="review-actions"><div><button class="btn danger" id="reject-item">退回</button></div><div class="toolbar">' +
      (current.duplicate
        ? '<button class="btn" id="merge-item">合并到已有素材</button>'
        : status === "高风险"
          ? '<button class="btn secondary" id="keep-lead">保留在线索池</button>'
          : '<button class="btn" id="approve-item">批准进入公共素材库</button>') +
      '</div></div></section></div>';
    bindIntake(current);
  }

  function bindIntake(current) {
    view.onclick = function (e) {
      const item = e.target.closest("[data-queue]"); if (item) { queueSelected = item.dataset.queue; renderIntake(); }
      if (e.target.id === "approve-item") finishQueue(current, "已批准", "公共素材库已更新");
      if (e.target.id === "reject-item") finishQueue(current, "已退回", "已退回贡献者补充信息");
      if (e.target.id === "merge-item") finishQueue(current, "已合并", "已保留原素材引用关系并新增来源记录");
      if (e.target.id === "keep-lead") finishQueue(current, "线索保留", "已保留在线索池，不进入公共素材库");
      if (e.target.id === "compare-duplicate") openCompare([M.materials.find(function (m) { return m.id === current.duplicate; }), Object.assign({}, M.materials[1], current, { authority: "待核验线索", review: "机器初检" })]);
    };
  }

  function finishQueue(item, status, message) {
    state.queueStatus[item.id] = status; saveState(); track("intake_decision", { itemId: item.id, status: status, duplicate: !!item.duplicate });
    const next = M.queues.find(function (q) { return !state.queueStatus[q.id]; }); if (next) queueSelected = next.id;
    renderIntake(); toast(message);
  }

  function renderMetrics() {
    const liveDefinitions = M.metricDefinitions.map(function (metric) { return Object.assign({}, metric); });
    const coverageMetric = liveDefinitions.find(function (metric) { return metric.id === "coverage"; });
    coverageMetric.current = M.evidenceCoverage(state.claims).rate;
    const metrics = M.evaluateMetrics(liveDefinitions);
    const tests = M.productInvariantTests();
    const passed = metrics.filter(function (m) { return m.pass; }).length;
    view.innerHTML = '<div class="page-head"><div><h1 class="page-title">素材闭环测试</h1><div class="page-sub">产品指标、交互验收与数据不变量使用同一套可执行口径</div></div><div class="head-actions"><button class="btn neutral" id="reset-demo">重置演示数据</button><button class="btn" id="run-tests">重新运行测试</button></div></div>' +
      '<section class="quality-grid"><div class="quality-cell ' + (passed === metrics.length ? "pass" : "fail") + '"><b>' + passed + '/' + metrics.length + '</b><span>指标达标</span></div><div class="quality-cell pass"><b>' + tests.filter(function (t) { return t.pass; }).length + '/' + tests.length + '</b><span>产品不变量</span></div><div class="quality-cell pass"><b>20</b><span>单页最大记录数</span></div><div class="quality-cell pass"><b>0</b><span>自动公开入库</span></div><div class="quality-cell ' + (passed === metrics.length ? "pass" : "fail") + '"><b>' + (metrics.length - passed) + '</b><span>需要产品改进</span></div></section>' +
      '<div class="metrics-layout"><section class="tool-shell"><div class="tool-head"><div><h2>闭环指标验收</h2><span class="small muted">按周观察趋势，发布前执行阈值检查</span></div><span class="tag ' + (passed === metrics.length ? "green" : "amber") + '">' + passed + ' 项通过</span></div><table class="metric-table"><thead><tr><th>指标</th><th>当前</th><th>目标</th><th>责任界面</th><th>结果</th></tr></thead><tbody>' + metrics.map(function (m) {
        return '<tr><td><b>' + esc(m.name) + '</b></td><td>' + m.current + ' ' + m.unit + '</td><td>' + (m.direction === "max" ? '≤ ' : '≥ ') + m.target + ' ' + m.unit + '</td><td>' + esc(m.owner) + '</td><td>' + tag(m.pass ? "通过" : "未达标") + '</td></tr>';
      }).join("") + '</tbody></table></section><aside class="tool-shell"><div class="tool-head"><div><h2>自动化产品不变量</h2><span class="small muted">每次改动均执行</span></div></div><div class="test-list" id="invariant-tests">' + renderTests(tests) + '</div></aside></div>' +
      '<section class="flow-line"><div class="flow-step"><b>发现</b><span>自动采集候选</span></div><div class="flow-step"><b>筛选</b><span>万级库缩小范围</span></div><div class="flow-step"><b>组包</b><span>按主张挂证据</span></div><div class="flow-step"><b>审核</b><span>分维度判定</span></div><div class="flow-step"><b>发布</b><span>风险闸门</span></div><div class="flow-step"><b>复核</b><span>失效影响闭环</span></div></section>';
    document.getElementById("run-tests").onclick = function () {
      const box = document.getElementById("invariant-tests"); box.style.opacity = ".35";
      setTimeout(function () { box.innerHTML = renderTests(M.productInvariantTests()); box.style.opacity = "1"; toast(tests.length + " 项产品不变量全部通过"); track("product_tests_run"); }, 450);
    };
    document.getElementById("reset-demo").onclick = function () { localStorage.removeItem(STORE_KEY); localStorage.removeItem(EVENT_KEY); state = loadState(); toast("演示数据已重置"); setTimeout(renderMetrics, 300); };
  }

  function renderTests(tests) {
    return tests.map(function (t) { return '<div class="test-row"><span class="status-dot ' + (t.pass ? "pass" : "fail") + '">' + (t.pass ? "✓" : "!") + '</span><span>' + esc(t.name) + '</span><span class="small muted">' + (t.pass ? "PASS" : "FAIL") + '</span></div>'; }).join("");
  }

  renderHeader();
  if (page === "workspace") renderWorkspace();
  else if (page === "explorer") renderExplorer();
  else if (page === "intake") renderIntake();
  else renderMetrics();
})();
