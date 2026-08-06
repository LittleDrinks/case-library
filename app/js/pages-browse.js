// 页面：资源检索（列表/图谱/图谱问答三视图）、案例详情、素材详情、知识详情
// 依据 docs/adr/0004（检索与图谱）、0005（引用体系与详情页）、0007（检索页去凌乱：百度式混合结果流）
window.Pages = window.Pages || {};
(function () {
  const P = window.Pages;
  const H = P.H;

  // ------------------------------------------------------------ 资源检索
  const PAGE_SIZE = 10;
  const SORTS = {
    all: [["smart", "综合排序"], ["newest", "最新优先"]],
    case: [["smart", "综合排序"], ["newest", "最新优先"], ["likes", "点赞优先"]],
    material: [["smart", "综合排序"], ["newest", "最新优先"], ["cited", "被引优先"]],
    knowledge: [["smart", "综合排序"], ["bookorder", "教材顺序"]],
  };
  // 更新时间筛选（单选，ADR 0007）
  const TIME_DAYS = { week: 7, month: 30, year: 365 };
  const TIME_OPTS = [["week", "一周内"], ["month", "一月内"], ["year", "一年内"]];

  P.search = (params) => {
    const state = {
      q: params.q || "", kindTab: "all", page: 1, sort: "smart",
      view: params.view === "graph" || params.view === "qa" ? params.view : "list",
      fTypes: new Set(), fAud: new Set(), fGrade: new Set(), fKind: new Set(), fTags: new Set(),
      fTime: "", ddOpen: null,
      ran: !!params.q, aiLoading: false, aiHtml: "", aiCount: 0, aiSeq: 0, aiSkipped: false,
      aiStreaming: false, aiText: "", aiSources: [], aiStream: null,
      aiFold: localStorage.getItem("sizheng-ai-fold") === "1",
      terms: null, expanded: [], base: null, loading: false,
      qa: { q: "", seq: 0, loading: false, answer: "", refs: [], stats: null, note: "", error: "", degraded: false },
    };
    const graphState = { expanded: new Set(), data: null }; // data = overview 缓存（展开案例后并入 ego）

    // 时间口径：案例/素材取自身时间，知识取所属教材来源的更新日（ADR 0007）
    const knDate = () => {
      const src = Store.db.knowledgeSources.find((s) => s.id === "ks-zr") || Store.db.knowledgeSources[0];
      return (src && src.updatedAt) || "";
    };
    const dateOf = (kind, item) => kind === "knowledge"
      ? knDate()
      : (item.updatedAt || item.publishedAt || item.collectedAt || "");

    // 当前查询的基础结果（未加筛选）；空查询 = 全量目录（浏览 = 不带关键词的检索，ADR 0007）
    // 目录态下知识按「资源实体」聚合为教材 1 条（碎片进教材主页浏览，ADR 0011）；检索态仍按节命中
    // 检索态命中来自服务端 /api/search（BM25 统一口径），refresh 异步拉取后缓存进 state.base
    const base = () => state.base || { cases: [], knowledge: [], materials: [], terms: state.terms || [] };
    const refresh = async () => {
      if (!state.ran) {
        const bookEntry = Store.db.bookFile ? [{
          item: {
            id: "#book", bookEntry: true, chapter: "教材",
            title: Store.db.book.title,
            text: Store.db.bookFile.summary || "",
            updatedAt: knDate(),
          },
        }] : [];
        state.base = {
          cases: Store.visibleCases().map((item) => ({ item })),
          knowledge: bookEntry,
          materials: Store.visibleMaterials().map((item) => ({ item })),
          terms: [],
        };
        return;
      }
      state.loading = true;
      state.base = await Store.search(state.q, { limit: 500 }, state.terms || undefined);
      state.loading = false;
    };

    // 筛选过滤；skipGroup 用于「结果集口径」的选项计数（本组不参与自己的计数）
    const pass = (item, kind, skipGroup) => {
      if (kind === "case") {
        if (skipGroup !== "type" && state.fTypes.size && !state.fTypes.has(item.typeId)) return false;
        if (skipGroup !== "aud" && state.fAud.size && !state.fAud.has(item.audience)) return false;
      } else if (kind === "material") {
        if (skipGroup !== "grade" && state.fGrade.size && !state.fGrade.has(item.grade || "未定级")) return false;
        if (skipGroup !== "mkind" && state.fKind.size && !state.fKind.has(item.kind)) return false;
      }
      // 知识条目无标签，标签筛选不作用于它（保留历史行为）
      if (kind !== "knowledge" && skipGroup !== "tags" && state.fTags.size && !Store.hasTag(kind, item, state.fTags)) return false;
      if (skipGroup !== "time" && state.fTime) {
        const d = Date.parse(String(dateOf(kind, item)));
        if (!d || d < Date.now() - TIME_DAYS[state.fTime] * 864e5) return false;
      }
      return true;
    };

    const results = () => {
      const r = base();
      return {
        cases: r.cases.filter((x) => pass(x.item, "case", null)),
        knowledge: r.knowledge.filter((x) => pass(x.item, "knowledge", null)),
        materials: r.materials.filter((x) => pass(x.item, "material", null)),
        terms: r.terms,
      };
    };

    // 选项计数 = 当前查询 + 其他筛选下的结果集计数（ADR 0004）
    const facetData = () => {
      const r = base();
      const cnt = (arr, kind, skip, key) =>
        arr.filter((x) => pass(x.item, kind, skip)).reduce((m, x) => {
          const k = key(x.item); m[k] = (m[k] || 0) + 1; return m;
        }, {});
      const typeN = cnt(r.cases, "case", "type", (c) => c.typeId);
      const audN = cnt(r.cases, "case", "aud", (c) => c.audience);
      const gradeN = cnt(r.materials, "material", "grade", (m) => m.grade || "未定级");
      const kindN = cnt(r.materials, "material", "mkind", (m) => m.kind);
      const tagN = {};
      r.cases.filter((x) => pass(x.item, "case", "tags")).forEach((x) =>
        Store.tagsOf("case", x.item).forEach((t) => { tagN[t] = (tagN[t] || 0) + 1; }));
      r.materials.filter((x) => pass(x.item, "material", "tags")).forEach((x) =>
        Store.tagsOf("material", x.item).forEach((t) => { tagN[t] = (tagN[t] || 0) + 1; }));
      const only = (items, set) => items.filter((x) => x.n > 0 || set.has(x.id));
      return {
        types: only(Store.db.caseTypes.map((t) => ({ id: t.id, name: t.name, n: typeN[t.id] || 0 })), state.fTypes),
        aud: only(["grad", "ug", "embed"].map((a) => ({ id: a, name: Store.audienceName(a), n: audN[a] || 0 })), state.fAud),
        grade: only(["S", "A", "B", "C", "未定级"].map((id) => ({ id, name: id === "未定级" ? id : id + " 级", n: gradeN[id] || 0 })), state.fGrade),
        kind: only(Object.keys(kindN).sort().map((id) => ({ id, name: id, n: kindN[id] })), state.fKind),
        tags: Object.entries(tagN).sort((a, b) => b[1] - a[1]).slice(0, 14).map(([t, n]) => ({ id: t, name: t, n })),
      };
    };

    const sortSelect = () => {
      let opts = SORTS[state.kindTab] || SORTS.all;
      // 目录态无相关度，隐藏综合排序（ADR 0007）
      if (!state.ran) opts = opts.filter(([v]) => v !== "smart");
      if (!opts.some(([v]) => v === state.sort)) state.sort = opts[0][0];
      if (opts.length <= 1) return "";
      return `<select id="sf-sort" style="max-width:130px">
        ${opts.map(([v, n]) => `<option value="${v}" ${state.sort === v ? "selected" : ""}>${n}</option>`).join("")}
      </select>`;
    };

    // 筛选维度按页签出项（ADR 0007）；素材分面 = 信源等级/类型/标签/时间（ADR 0004 方向）
    const filterDefs = () => {
      const f = facetData();
      return [
        { key: "type", title: "案例类型", items: f.types, set: state.fTypes, tabs: ["case"] },
        { key: "aud", title: "学段", items: f.aud, set: state.fAud, tabs: ["case"] },
        { key: "grade", title: "信源等级", items: f.grade, set: state.fGrade, tabs: ["material"] },
        { key: "mkind", title: "类型", items: f.kind, set: state.fKind, tabs: ["material"] },
        { key: "tags", title: "标签", items: f.tags, set: state.fTags, tabs: ["all", "case", "material"] },
        { key: "time", title: "时间", single: true, tabs: ["all", "case", "material", "knowledge"],
          items: TIME_OPTS.map(([id, name]) => ({ id, name })) },
      ];
    };

    // 百度式高级筛选：下拉内多选/单选，选中条件以 chip 行回显（ADR 0007）
    const filterBar = () => {
      const dds = filterDefs().filter((d) => d.tabs.includes(state.kindTab) && (d.single || d.items.length));
      const sort = sortSelect();
      // 范围（我的/机构/公共）预留 UI 位，逻辑待 scope 字段启用
      const scope = state.kindTab === "material"
        ? `<button class="btn sm plain" disabled title="范围筛选（我的/机构/公共）待开通">范围 ▾</button>` : "";
      if (!dds.length && !sort && !scope) return "";
      const html = dds.map((d) => {
        const active = d.single ? !!state.fTime : d.set.size > 0;
        const label = d.single
          ? (state.fTime ? TIME_OPTS.find(([v]) => v === state.fTime)[1] : "时间不限")
          : (active ? `${d.title}·${d.set.size}` : d.title);
        return `<span class="fdd" data-dd-root>
          <button class="btn sm ${active ? "" : "plain"}" data-dd-btn="${d.key}">${U.esc(label)} ▾</button>
          ${state.ddOpen === d.key ? `<span class="fdd-panel">
            ${d.single ? `<label><input type="radio" name="flt-time" data-f-time="" ${!state.fTime ? "checked" : ""}><span>时间不限</span></label>` : ""}
            ${d.items.map((it) => d.single
              ? `<label><input type="radio" name="flt-time" data-f-time="${it.id}" ${state.fTime === it.id ? "checked" : ""}><span>${U.esc(it.name)}</span></label>`
              : `<label><input type="checkbox" data-facet="${d.key}" value="${U.esc(String(it.id))}" ${d.set.has(it.id) ? "checked" : ""}><span>${U.esc(it.name)}</span>${it.n !== undefined ? `<span class="facet-n">${it.n}</span>` : ""}</label>`).join("")}
          </span>` : ""}
        </span>`;
      }).join("");
      return `<div class="filter-bar">${html}${scope}${sort}</div>`;
    };

    const chipsRow = () => {
      const chips = [];
      filterDefs().forEach((d) => {
        if (d.single) {
          if (state.fTime) chips.push({ key: d.key, val: "", label: "时间：" + TIME_OPTS.find(([v]) => v === state.fTime)[1] });
          return;
        }
        d.set.forEach((v) => {
          const it = (d.items.find((x) => x.id === v) || {}).name || v;
          chips.push({ key: d.key, val: v, label: d.title + "：" + it });
        });
      });
      if (!chips.length) return "";
      return `<div class="row wrap" style="gap:6px;margin-bottom:10px">
        ${chips.map((c) => `<span class="chip">${U.esc(String(c.label))}<a data-chip-key="${c.key}" data-chip-val="${U.esc(String(c.val))}">×</a></span>`).join("")}
        <button class="btn sm plain" id="flt-clear">清空筛选</button>
      </div>`;
    };

    // 结果条目统一极简格式：小字类型标 + 标题 + 90 字摘要（ADR 0007）
    // 素材条目加元信息行：信源等级/可信度/来源/发布日期/状态/被引次数/时效标（ADR 0005）
    const materialMeta = (x) => {
      const m = x.item;
      const bits = [
        H.gradeTag(m.grade), H.credTag(m.credibility),
        `<span>${U.esc(m.source || "")}</span>`,
        m.publishedAt ? `<span>${U.esc(U.plainDate(m.publishedAt))}</span>` : "",
        m.status && m.status !== "正常" ? `<span class="tag red">${U.esc(m.status)}</span>` : "",
        `<span>被引 ${m.citedCount || 0}</span>`,
        Store.isPolicyDated(m) ? `<span class="tag amber" title="政策类文件发布超过 3 年">注意时效</span>` : "",
      ];
      return `<div class="row wrap small muted" style="gap:6px;margin-top:2px">${bits.filter(Boolean).join("")}</div>`;
    };
    const KIND_META = {
      case: { name: "案例", cls: "primary", href: (x) => "#/case/" + x.item.id, title: (x) => x.item.title, text: (x) => x.item.summary || "" },
      knowledge: { name: "知识", cls: "blue", href: (x) => x.item.bookEntry ? "#/book" : "#/knowledge/" + x.item.id, title: (x) => x.item.chapter + " · " + x.item.title, text: (x) => x.item.text || "" },
      // 服务端切片命中带 sec 结构路径时直达切片（ADR 0010 深链）
      material: { name: "素材", cls: "green", href: (x) => "#/material/" + x.item.id + (x.sec ? "?sec=" + encodeURIComponent(x.sec) : ""), title: (x) => x.item.title, text: (x) => x.item.summary || "", meta: materialMeta },
    };
    const kindRow = (hl, kind) => (x) => {
      const m = KIND_META[kind];
      return `
      <a class="result-item" href="${m.href(x)}">
        <div class="row"><span class="tag ${m.cls}">${m.name}</span><h4>${hl(m.title(x))}</h4></div>
        <div class="small muted" style="margin:2px 0">${hl(m.text(x).slice(0, 90))}</div>
        ${m.meta ? m.meta(x) : ""}
      </a>`;
    };

    const pager = (total) => {
      const pages = Math.ceil(total / PAGE_SIZE);
      if (pages <= 1) return "";
      const cur = state.page;
      const nums = [];
      for (let i = 1; i <= pages; i++) {
        if (pages > 7 && i > 2 && i < pages - 1 && Math.abs(i - cur) > 1) {
          if (nums[nums.length - 1] !== "…") nums.push("…");
          continue;
        }
        nums.push(i);
      }
      return `<div class="pager">
        <button data-page="${cur - 1}" ${cur <= 1 ? "disabled" : ""}>上一页</button>
        ${nums.map((n) => n === "…" ? `<span class="pager-dots">…</span>` : `<button data-page="${n}" class="${n === cur ? "on" : ""}">${n}</button>`).join("")}
        <button data-page="${cur + 1}" ${cur >= pages ? "disabled" : ""}>下一页</button>
        <span class="pager-jump">跳至<input id="pg-jump" type="number" min="1" max="${pages}" value="${cur}">/ ${pages} 页
          <button data-page-jump>跳转</button></span>
      </div>`;
    };

    // AI 回答：仅「本地结果不足」或「问题式查询」自动生成（省 token，ADR 0004）
    const shouldAnswer = () => {
      const r = results();
      const total = r.cases.length + r.knowledge.length + r.materials.length;
      const questionLike = /哪些|怎么|为什么|如何|吗|？|\?/.test(state.q) || state.q.length >= 15;
      return total < 3 || questionLike;
    };

    // 来源 chips：链接到对应详情页（sources 为 [{n, type, id, title}]，type 取 case/knowledge/material）
    const AI_SRC_HREF = { case: "#/case/", knowledge: "#/knowledge/", material: "#/material/" };
    const aiSrcChips = () => !state.aiSources.length ? "" : `
      <div class="row wrap" style="gap:6px;margin-top:8px">
        ${state.aiSources.map((s) => `<a class="tag" href="${AI_SRC_HREF[s.type]}${U.esc(s.id)}" title="${U.esc(s.title)}">〔${s.n}〕${U.esc(s.title)}</a>`).join("")}
      </div>`;

    const aiBlockHTML = () => {
      if (!state.ran) return "";
      if (Store.flags.aiConfigured === false) return ""; // AI 未配置：隐藏入口，只留 BM25 列表
      if (state.aiSkipped) return `
        <div class="ai-answer row spread">
          <span class="small muted">本次检索命中明确，未生成 AI 解读（省流模式）</span>
          <button class="btn sm plain" id="ai-force">生成 AI 解读</button>
        </div>`;
      if (state.aiLoading) return `
        <div class="ai-answer">
          <div class="ai-answer-head"><span class="tag primary">AI 回答</span></div>
          <div class="small muted">正在结合平台资源生成回答<span class="loading-dots">…</span></div>
        </div>`;
      // 流式生成中：气泡增量渲染（onToken 节流直写 #ai-stream-body；redraw 时带当前快照）
      if (state.aiStreaming) return `
        <div class="ai-answer">
          <div class="ai-answer-head"><span class="tag primary">AI 回答</span>
          <span class="small muted">正在生成<span class="loading-dots">…</span></span></div>
          <div class="ai-answer-body" id="ai-stream-body">${U.linkifyCitations(U.md(state.aiText || ""), state.aiSources, { escaped: true })}</div>
        </div>`;
      if (!state.aiHtml) return "";
      if (state.aiFold) return `
        <div class="ai-answer">
          <div class="row spread"><span class="tag primary">AI 回答</span>
          <button class="btn sm plain" id="ai-fold">展开</button></div>
        </div>`;
      return `
        <div class="ai-answer">
          <div class="ai-answer-head"><span class="tag primary">AI 回答</span>
          <span class="small muted">${state.aiCount ? `总结 ${state.aiCount} 篇平台资源生成` : "平台资源未覆盖，结合通用知识回答"} · 仅供参考</span>
          <button class="btn sm plain" id="ai-fold">折叠</button></div>
          <div class="ai-answer-body">${state.aiHtml}</div>
          ${aiSrcChips()}
        </div>`;
    };

    const mainHTML = () => {
      const r = results();
      const hl = (txt) => U.highlight(txt, r.terms || []);
      const counts = { case: r.cases.length, knowledge: r.knowledge.length, material: r.materials.length };
      const tabs = [["all", `全部 ${counts.case + counts.knowledge + counts.material}`], ["case", `案例 ${counts.case}`], ["knowledge", `知识 ${counts.knowledge}`], ["material", `素材 ${counts.material}`]];
      // 统一装配 [kind, entry]；目录态默认最新，检索态全部页签按相关度（ADR 0007）
      const sortValid = (SORTS[state.kindTab] || SORTS.all).some(([v]) => v === state.sort);
      let sortKey = sortValid ? state.sort : "smart";
      if (!state.ran && sortKey === "smart") sortKey = "newest";
      // 素材综合排序 = 等级权重 × 相关度 × 新鲜度 × 被引（其余页签按服务端相关度）
      const GRADE_W = { S: 1.3, A: 1.2, B: 1.0, C: 0.8, "": 0.9 };
      const matSmart = (e) => {
        const m = e.item;
        const fresh = Store.isPolicyDated(m) ? 0.85 : 1;
        return (e.score || 0.1) * (GRADE_W[m.grade || ""] || 0.9) * fresh *
          (1 + Math.min(m.citedCount || 0, 10) * 0.05);
      };
      const cmp = {
        smart: state.kindTab === "material"
          ? (a, b) => matSmart(b[1]) - matSmart(a[1])
          : (a, b) => (b[1].score || 0) - (a[1].score || 0),
        newest: (a, b) => String(dateOf(b[0], b[1].item)).localeCompare(String(dateOf(a[0], a[1].item))),
        likes: (a, b) => (b[1].item.likes || 0) - (a[1].item.likes || 0),
        cited: (a, b) => Store.materialUsage(b[1].item.id).count - Store.materialUsage(a[1].item.id).count,
        bookorder: (a, b) => Store.db.knowledge.indexOf(a[1].item) - Store.db.knowledge.indexOf(b[1].item),
      }[sortKey];
      const pairs = {
        case: r.cases.map((x) => ["case", x]),
        knowledge: r.knowledge.map((x) => ["knowledge", x]),
        material: r.materials.map((x) => ["material", x]),
      };
      let ordered, emptyText;
      if (state.kindTab === "all") {
        ordered = pairs.case.concat(pairs.knowledge, pairs.material).sort(cmp);
        emptyText = state.ran ? "平台内没有命中结果，可换个关键词，或让 AI 联网补充公开来源" : "平台内暂无资源";
      } else {
        // 检索态服务端按相关度（score）返回，其余排序口径在本地 cmp（ADR 0007）
        ordered = pairs[state.kindTab].slice().sort(cmp);
        emptyText = "当前筛选下没有结果";
      }
      const list = ordered.slice((state.page - 1) * PAGE_SIZE, state.page * PAGE_SIZE);
      const body = state.loading
        ? `<div class="card card-pad small muted">检索中<span class="loading-dots">…</span></div>`
        : `<div class="card">${list.map(([k, x]) => kindRow(hl, k)(x)).join("") || H.empty(emptyText)}</div>${pager(ordered.length)}`;
      return `
      ${state.expanded.length ? `<div class="small muted" style="margin-bottom:10px">已扩展检索：${state.expanded.map(U.esc).join("、")}</div>` : ""}
      ${aiBlockHTML()}
      <div class="row spread wrap" style="margin-bottom:10px">
        <div class="result-tabs">${tabs.map(([k, n]) => `<button data-ktab="${k}" class="${state.kindTab === k ? "on" : ""}">${n}</button>`).join("")}</div>
        ${filterBar()}
      </div>
      ${chipsRow()}
      ${body}`;
    };

    // ---------------- 图谱视图（ADR 0004：骨架+案例，素材按需展开；数据 = 服务端 Neo4j 图谱） ----------------
    const graphHTML = () => `
      <div id="graph-wrap">
        <canvas id="graph-canvas"></canvas>
        <div id="graph-legend">
          ${Object.keys(Graph.NAMES).map((k) => `
            <div class="row"><span class="legend-dot" style="background:${Graph.COLORS[k]}"></span>${Graph.NAMES[k]}</div>`).join("")}
        </div>
        <div id="graph-tip"></div>
        <div id="graph-card" class="graph-card" hidden></div>
      </div>`;

    async function renderGraph(el) {
      const canvas = U.$("#graph-canvas", el);
      if (!canvas) return;
      const card = U.$("#graph-card", el);
      const hl = new Set();
      if (state.ran) {
        const r = results();
        r.cases.forEach((x) => hl.add(x.item.id));
        r.knowledge.forEach((x) => hl.add(x.item.id));
        r.materials.forEach((x) => hl.add(x.item.id));
      }
      if (!graphState.data) {
        const d = await Graph.fetchOverview();
        if (!U.$("#graph-canvas", el)) return; // 已切走视图
        if (!d || !d.ok) {
          U.$("#s-results", el).innerHTML = `<div class="card"><div class="card-pad small muted">
            图谱服务不可用（Neo4j 未连接），检索列表等其他功能不受影响。</div></div>`;
          return;
        }
        graphState.data = { nodes: d.nodes, links: d.links };
        for (const cid of graphState.expanded) { // 重挂载时恢复已展开的案例
          const sub = await Graph.fetchEgo("case", cid);
          if (sub && sub.ok) graphState.data = Graph.mergeData(graphState.data, sub);
        }
      }
      const hideCard = () => { card.hidden = true; };
      const openNode = (n) => {
        if (n.ref.kind === "case") location.hash = "#/case/" + n.ref.id;
        else if (n.ref.kind === "knowledge") location.hash = "#/knowledge/" + n.ref.id;
        else if (n.ref.kind === "material") location.hash = "#/material/" + n.ref.id;
        else if (n.ref.kind === "tag") location.hash = "#/search?q=" + encodeURIComponent(n.ref.id);
        else if (n.ref.kind === "chapter") {
          const ch = Store.db.chapters.find((x) => x.id === n.ref.id);
          const first = ch && ch.sections[0] && Store.knowledgeById(ch.sections[0]);
          if (first) location.hash = "#/knowledge/" + first.id;
        }
      };
      Graph.render(canvas, {
        data: graphState.data,
        tip: U.$("#graph-tip", el),
        highlight: hl,
        onOpen: openNode,
        onCard(n, pos) {
          const t = n.ref.kind === "tag" ? { src: "" } : H.citeName(n.ref.id);
          const snippet = n.ref.kind === "case"
            ? (Store.caseById(n.ref.id) || {}).summary || ""
            : n.ref.kind === "knowledge" ? (Store.knowledgeById(n.ref.id) || {}).text || ""
            : n.ref.kind === "material" ? ((Store.materialById(n.ref.id) || {}).summary || "") : "";
          const canExpand = n.ref.kind === "case" && !graphState.expanded.has(n.ref.id);
          card.innerHTML = `
            <div class="row spread"><b>${U.esc(n.label)}</b><button class="modal-close" id="gc-close">×</button></div>
            <div class="small muted" style="margin:4px 0">${Graph.NAMES[n.type]}${t.src ? " · " + U.esc(t.src) : ""}</div>
            ${snippet ? `<div class="small" style="margin-bottom:8px">${U.esc(snippet.slice(0, 80))}…</div>` : ""}
            <div class="row">
              <button class="btn sm" id="gc-open">打开</button>
              ${canExpand ? `<button class="btn sm plain" id="gc-expand">展开素材引用</button>` : ""}
            </div>`;
          card.hidden = false;
          card.style.left = Math.min(pos.x + 16, canvas.clientWidth - 240) + "px";
          card.style.top = Math.max(8, pos.y - 20) + "px";
          U.$("#gc-close", card).addEventListener("click", hideCard);
          U.$("#gc-open", card).addEventListener("click", () => openNode(n));
          const ex = U.$("#gc-expand", card);
          if (ex) ex.addEventListener("click", async () => {
            graphState.expanded.add(n.ref.id);
            hideCard();
            const sub = await Graph.fetchEgo("case", n.ref.id);
            if (sub && sub.ok) graphState.data = Graph.mergeData(graphState.data, sub);
            renderGraph(el);
          });
        },
      });
    }

    // ---------------- 图谱问答（WP7：子图召回 + AI 综合，引用节点可点开） ----------------
    const REF_KIND_NAMES = { case: "案例", knowledge: "知识", material: "素材", chapter: "知识 · 章", tag: "标签" };
    const openRef = (kind, id) => {
      if (kind === "case") location.hash = "#/case/" + id;
      else if (kind === "knowledge") location.hash = "#/knowledge/" + id;
      else if (kind === "material") location.hash = "#/material/" + id;
      else if (kind === "chapter") {
        const ch = Store.db.chapters.find((x) => x.id === id);
        const first = ch && ch.sections[0] && Store.knowledgeById(ch.sections[0]);
        if (first) location.hash = "#/knowledge/" + first.id;
      } else location.hash = "#/search?q=" + encodeURIComponent(id);
    };
    const refCardHTML = (r) => `
      <div class="kn-item" data-ref-kind="${U.esc(r.ref.kind)}" data-ref-id="${U.esc(r.ref.id)}" style="cursor:pointer">
        <div class="row" style="gap:6px"><span class="tag">${REF_KIND_NAMES[r.ref.kind] || r.ref.kind}</span>
        <b class="small">${U.esc(r.label)}</b></div>
      </div>`;
    const qaHTML = () => {
      const qa = state.qa;
      let body = `<div class="small muted">就整个案例库提问：共同主题、思政元素分布、政策关联等。
        回答基于知识图谱子图召回 + AI 综合，引用节点可点开查看详情。</div>`;
      if (qa.loading) {
        body += `<div class="small muted" style="margin-top:12px">图谱召回与 AI 综合中<span class="loading-dots">…</span></div>`;
      } else if (qa.error) {
        body += `<div class="small" style="color:var(--red);margin-top:12px">${U.esc(qa.error)}</div>`;
      } else if (qa.answer || qa.degraded) {
        if (qa.answer) body += `<div class="snapshot-box" style="margin-top:12px">${U.md(qa.answer)}</div>`;
        if (qa.degraded) body += `<div class="small muted" style="margin-top:8px">${U.esc(qa.note || "AI 不可用，以下为召回子图统计")}</div>`;
        if (qa.stats && Object.keys(qa.stats).length) {
          body += `<div class="row wrap" style="margin-top:8px;gap:6px">
            ${Object.entries(qa.stats).map(([k, v]) => `<span class="tag">${U.esc(k)} ${v}</span>`).join("")}</div>`;
        }
        if (qa.refs.length) {
          body += `<div class="small muted" style="margin:10px 0 4px">引用节点（${qa.refs.length}）</div>`
            + qa.refs.map(refCardHTML).join("");
        }
      }
      return `<div class="card"><div class="card-pad">
        <div class="search-bar" style="margin-bottom:10px">
          <input id="qa-q" placeholder="例如：库里的案例主要涉及哪些思政主题？" value="${U.esc(qa.q)}">
          <button class="btn" id="qa-go">提问</button>
        </div>${body}</div></div>`;
    };

    return {
      html: `
      <div class="search-bar">
        <input id="sq" placeholder="用自然语言或关键词检索案例、知识、素材；留空回车即浏览全部" value="${U.esc(state.q)}">
        <button class="btn" id="s-go">检索</button>
        <div class="view-toggle">
          <button data-view="list" class="${state.view === "list" ? "on" : ""}">列表</button>
          <button data-view="graph" class="${state.view === "graph" ? "on" : ""}">图谱</button>
          <button data-view="qa" class="${state.view === "qa" ? "on" : ""}">图谱问答</button>
        </div>
      </div>
      <div id="s-results">${state.view === "list" ? mainHTML() : state.view === "graph" ? graphHTML() : qaHTML()}</div>`,
      mount(el) {
        const redraw = () => {
          if (state.view === "graph") { renderGraph(el); return; }
          if (state.view === "qa") { U.$("#s-results", el).innerHTML = qaHTML(); return; }
          U.$("#s-results", el).innerHTML = mainHTML();
        };
        const runQa = async () => {
          const inp = U.$("#qa-q", el);
          const q = (inp ? inp.value : state.qa.q).trim();
          if (!q) return;
          const seq = state.qa.seq + 1;
          state.qa = { q, seq, loading: true, answer: "", refs: [], stats: null, note: "", error: "", degraded: false };
          redraw();
          const d = await Graph.qa(q);
          if (state.qa.seq !== seq) return;
          if (!d || !d.ok) {
            state.qa = Object.assign(state.qa, { loading: false, error: (d && d.error) || "图谱问答服务不可用，请稍后重试" });
          } else {
            state.qa = { q, seq, loading: false, answer: d.answer || "", refs: d.refs || [],
                         stats: d.stats || null, note: d.note || "", error: "", degraded: !!d.degraded };
          }
          redraw();
        };
        // AI 回答消息组装：与 Copilot.answerQuery 同口径（资源池编号 〔n〕），改为走流式
        const buildAnswerPrompt = (q, results) => {
          const pool = [];
          results.cases.slice(0, 5).forEach((r) => pool.push({ kind: "案例", id: r.item.id, title: r.item.title, snippet: (r.item.summary || "").slice(0, 90) }));
          results.knowledge.slice(0, 5).forEach((r) => pool.push({ kind: "知识", id: r.item.id, title: r.item.chapter + " " + r.item.title, snippet: r.item.text.replace(/\s+/g, " ").slice(0, 90) }));
          results.materials.slice(0, 5).forEach((r) => pool.push({ kind: "素材", id: r.item.id, title: r.item.title, snippet: (r.item.excerpt || r.item.summary || "").replace(/\s+/g, " ").slice(0, 90) }));
          const numbered = pool.map((p, i) => `〔${i + 1}〕${p.kind}｜${p.title}｜${p.snippet}`).join("\n");
          const messages = [
            { role: "system", content: [
              "你是高校思政教学案例智能平台的检索助手，作用类似搜索引擎顶部的 AI 摘要。",
              "基于给出的平台资源回答用户问题：1. 先一两句直接回答（是什么、背景、要点）；2. 再分点展开：平台里有哪些可用资源、各自能支撑什么；3. 引用具体资源时在句末标注〔编号〕；4. 只能使用资源中的事实，平台资源未覆盖的部分明说，并可用常识简要补充（标注「通用知识」）；5. 中文、简练。",
            ].join("\n") },
            { role: "user", content: `用户问题：${q}\n\n平台资源（编号｜类型｜标题｜摘录）：\n${numbered || "（平台内未检索到相关资源）"}` },
          ];
          return { messages, pool };
        };
        // 流式气泡增量渲染（~80ms 节流，直写节点避免整页 redraw）
        let streamTimer = null;
        const flushStream = () => {
          streamTimer = null;
          const node = U.$("#ai-stream-body");
          if (node) node.innerHTML = U.linkifyCitations(U.md(state.aiText || ""), state.aiSources, { escaped: true });
        };
        const scheduleStream = () => { if (!streamTimer) streamTimer = setTimeout(flushStream, 80); };
        const runAi = async (force) => {
          const seq = ++state.aiSeq;
          if (state.aiStream) { state.aiStream.abort(); state.aiStream = null; } // 新检索取消上一轮流
          state.aiSkipped = false;
          state.aiLoading = true; state.aiStreaming = false;
          state.aiHtml = ""; state.aiText = ""; state.aiSources = []; state.expanded = [];
          redraw();
          const ex = await Copilot.expandQuery(state.q);
          if (seq !== state.aiSeq) return;
          if (ex.ok) {
            const local = U.terms(state.q);
            state.expanded = ex.core.concat(ex.expand).filter((t) => !local.includes(t)).slice(0, 8);
            state.terms = Array.from(new Set(local.concat(ex.core, ex.expand)));
          }
          // 查询理解扩展后的词重新拉一次命中（结果列表与 AI 资源池同口径）
          await refresh();
          if (seq !== state.aiSeq) return;
          redraw();
          if (!force && !shouldAnswer()) {
            state.aiLoading = false;
            state.aiSkipped = true;
            redraw();
            return;
          }
          const { messages, pool } = buildAnswerPrompt(state.q, base());
          if (seq !== state.aiSeq) return;
          state.aiCount = pool.length;
          state.aiSources = pool.map((p, i) => ({
            n: i + 1,
            type: { "案例": "case", "知识": "knowledge", "素材": "material" }[p.kind],
            id: p.id, title: p.title,
          }));
          state.aiLoading = false;
          state.aiStreaming = true;
          redraw();
          // 流式生成（失败时 chatStream 内部自动回退非流式）；text 仅用于会话历史记录
          state.aiStream = Copilot.chatStream({
            messages, text: state.q, conversationKey: "search",
            sources: state.aiSources, temperature: 0.3, max_tokens: 900,
            onToken(acc) { if (seq !== state.aiSeq) return; state.aiText = acc; scheduleStream(); },
            onDone: (full) => {
              if (seq !== state.aiSeq) return;
              state.aiStreaming = false; state.aiStream = null;
              state.aiHtml = U.linkifyCitations(U.md(full), state.aiSources, { escaped: true });
              redraw();
            },
            onError: (err) => {
              if (seq !== state.aiSeq) return;
              state.aiStreaming = false; state.aiStream = null;
              state.aiHtml = `<span class="small" style="color:var(--red)">AI 回答生成失败：${U.esc((err && err.message) || String(err || ""))}</span>`;
              redraw();
            },
          });
        };
        const run = async () => {
          state.q = U.$("#sq", el).value.trim();
          state.terms = null; state.expanded = []; state.page = 1;
          if (!state.q) { state.ran = false; await refresh(); redraw(); return; }
          state.ran = true;
          state.sort = "smart"; // 新检索默认回到相关度排序
          redraw();
          await refresh();
          redraw();
          if (state.view === "list" && Store.flags.aiConfigured !== false) runAi();
        };
        U.$("#s-go", el).addEventListener("click", run);
        U.$("#sq", el).addEventListener("keydown", (e) => { if (e.key === "Enter") run(); });
        // 分页跳转输入
        const jumpPage = () => {
          const inp = U.$("#pg-jump", el);
          if (!inp) return;
          const v = Math.round(Number(inp.value));
          if (!v) return;
          state.page = Math.min(Math.max(1, v), Number(inp.max) || 1);
          redraw();
          U.$("#s-results").scrollIntoView({ behavior: "smooth" });
        };
        el.addEventListener("keydown", (e) => {
          if (e.target.id === "pg-jump" && e.key === "Enter") { e.preventDefault(); jumpPage(); }
          if (e.target.id === "qa-q" && e.key === "Enter") { e.preventDefault(); runQa(); }
        });
        el.addEventListener("change", (e) => {
          if (e.target.id === "sf-sort") { state.sort = e.target.value; state.page = 1; redraw(); }
          // 时间筛选为单选，选中即收起面板
          const ft = e.target.closest("[data-f-time]");
          if (ft) { state.fTime = ft.dataset.fTime; state.ddOpen = null; state.page = 1; redraw(); return; }
          const f = e.target.closest("[data-facet]");
          if (f) {
            const set = { type: state.fTypes, aud: state.fAud, grade: state.fGrade, mkind: state.fKind, tags: state.fTags }[f.dataset.facet];
            f.checked ? set.add(f.value) : set.delete(f.value);
            state.page = 1;
            redraw();
          }
        });
        el.addEventListener("click", (e) => {
          const vw = e.target.closest("[data-view]");
          if (vw) {
            const v = vw.dataset.view;
            if (v !== state.view) {
              // 通过 URL 切换，路由重建后视图状态不丢
              Graph.stop();
              location.hash = "#/search?view=" + v + (state.q ? "&q=" + encodeURIComponent(state.q) : "");
            }
            return;
          }
          if (e.target.id === "ai-force") { state.aiSkipped = false; runAi(true); return; }
          if (e.target.id === "qa-go") { runQa(); return; }
          const rf = e.target.closest("[data-ref-kind]");
          if (rf) { openRef(rf.dataset.refKind, rf.dataset.refId); return; }
          if (e.target.id === "ai-fold") {
            state.aiFold = !state.aiFold;
            localStorage.setItem("sizheng-ai-fold", state.aiFold ? "1" : "0");
            redraw(); return;
          }
          // 筛选下拉开合
          const db = e.target.closest("[data-dd-btn]");
          if (db) { state.ddOpen = state.ddOpen === db.dataset.ddBtn ? null : db.dataset.ddBtn; redraw(); return; }
          // chip 单个移除 / 全部清空
          const cd = e.target.closest("[data-chip-key]");
          if (cd) {
            const k = cd.dataset.chipKey;
            if (k === "time") state.fTime = "";
            else {
              const set = { type: state.fTypes, aud: state.fAud, grade: state.fGrade, mkind: state.fKind, tags: state.fTags }[k];
              set.delete(cd.dataset.chipVal);
            }
            state.page = 1; redraw(); return;
          }
          if (e.target.id === "flt-clear") {
            state.fTypes.clear(); state.fAud.clear(); state.fGrade.clear(); state.fKind.clear(); state.fTags.clear();
            state.fTime = ""; state.page = 1; redraw(); return;
          }
          const kt = e.target.closest("[data-ktab]");
          if (kt) { state.kindTab = kt.dataset.ktab; state.page = 1; state.ddOpen = null; redraw(); return; }
          if (e.target.closest("[data-page-jump]")) { jumpPage(); return; }
          const pg = e.target.closest("[data-page]");
          if (pg && !pg.disabled) { state.page = Number(pg.dataset.page); redraw(); U.$("#s-results").scrollIntoView({ behavior: "smooth" }); return; }
        });
        // 点击面板之外时收起筛选下拉
        const onDocClick = (e) => {
          if (!state.ddOpen) return;
          if (e.target.closest && e.target.closest("[data-dd-root]")) return;
          state.ddOpen = null;
          redraw();
        };
        document.addEventListener("click", onDocClick);
        this._unmount = () => {
          document.removeEventListener("click", onDocClick);
          if (state.aiStream) { state.aiStream.abort(); state.aiStream = null; }
          if (streamTimer) { clearTimeout(streamTimer); streamTimer = null; }
        };
        if (state.view === "graph") { refresh().then(() => renderGraph(el)); }
        else if (state.view === "qa") { /* 问答视图无需预取检索结果 */ }
        else if (state.ran && state.q) {
          refresh().then(() => {
            redraw();
            if (state.view === "list" && Store.flags.aiConfigured !== false) runAi();
          });
        } else refresh();
      },
      unmount() { Graph.stop(); if (this._unmount) this._unmount(); },
    };
  };


  // ------------------------------------------------------------ 案例详情
  P.caseDetail = (id) => {
    const c = Store.caseById(id);
    if (!c) return P.notFound();
    const me = Store.me();
    const mine = c.ownerId === me.id || me.admin;
    const isPub = c.status === "published";
    const v = isPub && c.publishedSnapshot ? c.publishedSnapshot : c;

    if (!isPub && !mine) return P.notFound();

    const cites = (v.citations || []).map((r, i) => ({ r, i, t: H.citeName(r.target) }))
      .filter((x) => x.t.visible !== false);
    const related = Store.relatedCases(c, 4);
    const liked = (c.likedBy || []).includes(me.id);
    const blocks = Store.blocksOf(v);
    const tocItems = blocks.map((b, i) => ({ b, i })).filter((x) => x.b.kind === "h2" && x.b.text.trim());

    // 正文〔n〕上标 → 可点击（句级锚点：有 quote 的引用跟在 quote 句后，漂移退化块尾），与引用清单互跳（ADR 0005/WP3）
    const citeAnchors = U.citeAnchors(blocks, v.citations || []);
    const citeBad = (n) => Store.citeFailed((v.citations || [])[n - 1]);
    const markCites = (text, bi) => U.markCites(text, bi, citeAnchors, citeBad);

    const kitBlock = (title, items) => items && items.length ? `
      <div class="result-group"><div class="section-title"><span>${title}</span></div>
      <div class="card card-pad">${items.map((d, i) => `<div style="padding:4px 0">${i + 1}. ${U.esc(d)}</div>`).join("")}</div></div>` : "";

    const PREP_KINDS = [["kit-design", "教学设计"], ["kit-discussion", "讨论题"], ["kit-ppt", "PPT 提纲"]];
    // kit 展示：作者/管理员看工作副本（备课生成物写回后立即可见），其余访客看发布快照
    const kitView = mine ? (c.kit || v.kit) : v.kit;

    // 引用区：列表/图谱双视图，图谱为两跳力导向图（ADR 0008）；列表卡可展开看证据片段（WP3）
    let citeView = "list";
    const evdOpen = new Set();
    const citeHref = (t) => t.kind === "knowledge" ? "#/knowledge/" + t.id : "#/material/" + t.id;
    const citeListHTML = () => cites.length
      ? cites.map((x) => {
          const ev = x.r.evidence || {};
          const open = evdOpen.has(x.i + 1);
          const secHref = citeHref(x.t) + (ev.sec && x.t.kind !== "knowledge" ? "?sec=" + encodeURIComponent(ev.sec) : "");
          return `<div class="case-item" id="cite-card-${x.i + 1}">
            <div class="row spread">
              <h4><a href="${citeHref(x.t)}">〔${x.i + 1}〕${U.esc(x.t.name)}</a></h4>
              <span class="row" style="gap:6px">
                ${Store.citeFailed(x.r) ? `<span class="tag red sm">来源失效</span>` : ""}
                ${ev.snippet ? `<button class="btn sm plain" data-evd-toggle="${x.i + 1}">${open ? "收起证据" : "证据"}</button>` : ""}
              </span>
            </div>
            <div class="small muted">${U.esc(x.t.src || "")}${x.r.note ? " · " + U.esc(x.r.note) : ""}</div>
            ${open ? `<div class="evd-snip">${U.esc(ev.snippet)}</div>
              <div class="small muted" style="margin-top:4px">${ev.sec ? "切片 " + U.esc(ev.sec) + " · " : ""}${ev.capturedAt ? "采集 " + U.esc(ev.capturedAt) + " · " : ""}<a href="${secHref}">打开原文切片 →</a></div>` : ""}
          </div>`;
        }).join("")
      : `<div class="card-pad muted small">暂无引用。引用教材章节或素材后，这里会显示清单与关系图。</div>`;

    return {
      html: `
      <div class="case-layout">
        ${tocItems.length >= 2 ? `<aside class="case-toc" id="case-toc">
          <div class="small muted" style="margin-bottom:6px">目录</div>
          ${tocItems.map((x) => `<a href="javascript:void 0" data-toc="${x.i}">${U.esc(x.b.text)}</a>`).join("")}
        </aside>` : ""}
        <div style="min-width:0">
          ${!isPub ? `<div class="card card-pad" style="margin-bottom:12px">
            <div class="row spread">${H.statusTag(c.status)}<a class="btn sm" href="#/workbench/${c.id}">打开工作台</a></div>
          </div>` : ""}
          <div class="card card-pad article">
            <h2 style="font-size:20px">${U.esc(v.title)}</h2>
            <div class="row wrap small muted" style="margin-bottom:10px">
              ${H.typeTag(v.typeId)} ${H.audTag(v.audience)}
              ${v.author ? `<span>${U.esc(v.author)}</span>` : ""}
              ${v.org ? `<span>${U.esc(v.org)}</span>` : ""}
              ${isPub ? `<span>发布于 ${U.esc(U.plainDate(c.publishedAt))}</span>` : ""}
            </div>
            ${v.summary ? `<p style="background:var(--gray-soft);border-radius:6px;padding:10px 12px">${U.esc(v.summary)}</p>` : ""}
            ${(v.theoryPoints || []).length ? `<div class="row wrap" style="margin-bottom:10px">${v.theoryPoints.map((t) => `<span class="tag blue">${U.esc(t)}</span>`).join("")}</div>` : ""}
            ${blocks.map((b, i) => b.kind === "h2"
              ? `<h3 id="sec-${i}">${markCites(b.text, i)}</h3>`
              : `<p id="sec-${i}">${markCites(b.text, i)}</p>`).join("")}
            ${cites.length ? `<div class="doc-refs"><div class="doc-refs-title">参考文献</div>
              ${cites.map((x) => `<div class="doc-ref-item" id="ref-${x.i + 1}">
                <span>〔${x.i + 1}〕</span>
                <a href="${x.t.kind === "knowledge" ? "#/knowledge/" + x.t.id : "#/material/" + x.t.id}">${U.esc(x.t.name)}</a>
                <span class="small muted"> — ${U.esc(x.t.src || "")}</span>
              </div>`).join("")}</div>` : ""}
          </div>
          ${kitView && kitView.design ? `<div class="result-group"><div class="section-title"><span>教学设计</span></div>
            <div class="card card-pad snapshot-box" style="max-height:none">${U.esc(kitView.design)}</div></div>` : ""}
          ${kitView ? kitBlock("课堂讨论题", kitView.discussion) : ""}
          ${kitView ? kitBlock("PPT 提纲", kitView.ppt) : ""}
          ${isPub ? `
          <div class="card card-pad" style="margin-top:14px" id="prep-box">
            <div class="section-title"><span>结合案例备课</span></div>
            <div class="small muted" style="margin-bottom:8px">由 Copilot 基于本案例生成，生成物保存在「我的案例 → 我的备课材料」。</div>
            <div class="row wrap">
              ${PREP_KINDS.map(([k, n]) => `<button class="btn sm plain" data-prep="${k}">生成${n}</button>`).join("")}
            </div>
            <div id="prep-result"></div>
          </div>` : ""}
        </div>
        <div>
          <div class="card card-pad" style="margin-bottom:14px">
            <div class="section-title"><span>案例信息</span></div>
            <table class="meta-table">
              ${v.applyCourses && v.applyCourses.length ? `<tr><th>应用课程</th><td>${v.applyCourses.map(U.esc).join("、")}</td></tr>` : `<tr><th>课程</th><td>${U.esc(v.course || "—")}</td></tr>`}
              <tr><th>学段</th><td>${U.esc(v.stageText || Store.audienceName(v.audience))}</td></tr>
              <tr><th>案例类型</th><td>${U.esc(Store.typeName(v.typeId))}</td></tr>
            </table>
            <hr class="hr">
            <div class="row wrap">
              <button class="btn sm ${liked ? "" : "plain"}" id="cd-like">${liked ? "已赞" : "点赞"}（${c.likes || 0}）</button>
              <button class="btn sm ${Store.isFav(c) ? "" : "plain"}" id="cd-fav">${Store.isFav(c) ? "已收藏" : "收藏"}</button>
              <button class="btn sm plain" id="cd-share">复制链接</button>
              <button class="btn sm plain" id="cd-export">导出 Word</button>
              ${mine ? `<a class="btn sm plain" href="#/workbench/${c.id}">工作台</a>` : ""}
              ${Store.me().admin && (c.status === "published" || c.status === "hidden")
                ? `<a class="btn sm plain" href="#/admin/publish?q=${encodeURIComponent(c.title)}" title="在发布管理中检索定位该案例">后台定位 →</a>` : ""}
              ${Store.me().admin && (c.status === "pending" || c.status === "reviewing")
                ? `<a class="btn sm plain" href="#/admin/audit?q=${encodeURIComponent(c.title)}" title="在案例审核中检索定位该案例">后台定位 →</a>` : ""}
            </div>
          </div>
          <div class="card" style="margin-bottom:14px">
            <div class="card-pad section-title row spread" style="border-bottom:1px solid var(--line)">
              <span>引用（${cites.length}）</span>
              ${cites.length ? `<div class="view-toggle sm">
                <button data-cite-view="list" class="${citeView === "list" ? "on" : ""}">列表</button>
                <button data-cite-view="graph" class="${citeView === "graph" ? "on" : ""}">图谱</button>
              </div>` : ""}
            </div>
            <div id="cite-body">${citeListHTML()}</div>
          </div>
          ${related.length ? `<div class="card">
            <div class="card-pad section-title" style="border-bottom:1px solid var(--line)"><span>相关案例</span></div>
            ${related.map((x) => H.caseItem(x, "#/case/" + x.id)).join("")}
          </div>` : ""}
        </div>
      </div>`,
      mount(el) {
        U.$("#cd-like").addEventListener("click", async () => { if (await Store.likeCase(c)) P.rerender(); });
        U.$("#cd-fav").addEventListener("click", async () => { if (await Store.toggleFav(c)) P.rerender(); });
        U.$("#cd-share").addEventListener("click", () => {
          const url = location.origin + location.pathname + "#/case/" + c.id;
          (navigator.clipboard ? navigator.clipboard.writeText(url) : Promise.reject())
            .then(() => U.toast("链接已复制"))
            .catch(() => U.toast(url, 4000));
        });
        U.$("#cd-export").addEventListener("click", () => exportDetail(c, v));
        // 引用区图谱视图：两跳力导向图（服务端 Neo4j ego 子图，WP7），单击节点直达详情（ADR 0008）
        const renderCiteBody = async () => {
          const body = U.$("#cite-body", el);
          if (!body) return;
          Graph.stop();
          if (citeView === "list" || !cites.length) { body.innerHTML = citeListHTML(); return; }
          body.innerHTML = `<div class="ego-force"><canvas id="ego-canvas"></canvas><div class="graph-tip" id="ego-tip"></div></div>`;
          const d = await Graph.fetchEgo("case", c.id);
          const canvas = U.$("#ego-canvas", body);
          if (!canvas) return; // 已切回列表视图
          if (!d || !d.ok) {
            body.innerHTML = `<div class="small muted card-pad">图谱服务不可用（Neo4j 未连接），请用列表视图查看引用。</div>`;
            return;
          }
          Graph.render(canvas, {
            data: d, noCache: true,
            tip: U.$("#ego-tip", body),
            onCard: (n) => {
              if (n.ref.kind === "self") return;
              if (n.ref.kind === "tag") { location.hash = "#/search?q=" + encodeURIComponent(n.ref.id); return; }
              location.hash = n.ref.kind === "case" ? "#/case/" + n.ref.id : citeHref(n.ref);
            },
          });
        };
        // 目录：点击定位 + 滚动高亮
        const tocLinks = U.$$("[data-toc]", el);
        tocLinks.forEach((a) => a.addEventListener("click", () => {
          const target = U.$("#sec-" + a.dataset.toc, el);
          if (target) target.scrollIntoView({ behavior: "smooth", block: "start" });
        }));
        const spy = () => {
          let cur = null;
          tocItems.forEach((x) => {
            const n = U.$("#sec-" + x.i, el);
            if (n && n.getBoundingClientRect().top < 140) cur = x.i;
          });
          tocLinks.forEach((a) => a.classList.toggle("on", Number(a.dataset.toc) === cur));
        };
        window.addEventListener("scroll", spy);
        spy();
        // 正文〔n〕 → 引用清单互跳
        el.addEventListener("click", (e) => {
          const cv = e.target.closest("[data-cite-view]");
          if (cv) {
            citeView = cv.dataset.citeView;
            U.$$("[data-cite-view]", el).forEach((b) => b.classList.toggle("on", b.dataset.citeView === citeView));
            renderCiteBody();
            return;
          }
          const j = e.target.closest("[data-cite-jump]");
          if (j) {
            e.preventDefault();
            const card = U.$("#cite-card-" + j.dataset.citeJump) || U.$("#ref-" + j.dataset.citeJump);
            if (card) {
              card.scrollIntoView({ behavior: "smooth", block: "center" });
              card.classList.add("flash");
              setTimeout(() => card.classList.remove("flash"), 1600);
            }
            return;
          }
          const et = e.target.closest("[data-evd-toggle]");
          if (et) {
            const n = Number(et.dataset.evdToggle);
            evdOpen.has(n) ? evdOpen.delete(n) : evdOpen.add(n);
            renderCiteBody();
            return;
          }
          const pb = e.target.closest("[data-prep]");
          if (pb) runPrep(pb.dataset.prep);
        });
        // 备课生成（ADR 0005：入口在案例详情页，归生成者个人）
        let prepBusy = false;
        async function runPrep(intent) {
          if (prepBusy) return;
          prepBusy = true;
          const box = U.$("#prep-result", el);
          const kindName = (PREP_KINDS.find(([k]) => k === intent) || [])[1] || "材料";
          box.innerHTML = `<div class="small muted" style="margin-top:10px">Copilot 正在生成${kindName}<span class="loading-dots">…</span></div>`;
          const messages = await Copilot.buildMessages(c, 0, "", intent);
          const res = await Copilot.ask(messages, { max_tokens: 2200 });
          prepBusy = false;
          if (!res.ok) {
            box.innerHTML = `<div class="small" style="color:var(--red);margin-top:10px">生成失败：${U.esc(res.error || "")}</div>`;
            return;
          }
          const isAuthor = c.ownerId === me.id; // 仅作者可把生成物写回案例配套材料
          box.innerHTML = `
            <div class="snapshot-box" style="margin-top:10px;max-height:320px;overflow:auto">${U.md(res.content)}</div>
            <div class="row" style="margin-top:8px">
              <button class="btn sm" id="prep-save">保存到我的备课材料</button>
              ${isAuthor ? `<button class="btn sm secondary" id="prep-kit-save" title="写入本案例的配套材料（kit），详情页套件区即时更新">存为案例配套材料</button>` : ""}
              <span class="small muted">${U.esc(res.model || "")} · ${((res.elapsed_ms || 0) / 1000).toFixed(1)}s</span>
            </div>`;
          U.$("#prep-save", box).addEventListener("click", () => {
            Store.addPrep({ caseId: c.id, caseTitle: c.title, kind: intent, kindName, content: res.content });
            U.toast("已保存到「我的案例 → 我的备课材料」");
            if (P.refreshBadge) P.refreshBadge();
          });
          const kitBtn = U.$("#prep-kit-save", box);
          if (kitBtn) kitBtn.addEventListener("click", () => {
            const saved = Store.saveKitItem(c.id, intent.replace(/^kit-/, ""), res.content);
            if (saved) {
              U.toast(`已存为案例配套材料（${saved.kindName}）`);
              P.rerender(); // 套件区立即出现新内容
            } else U.toast("写回失败：只有案例作者才能保存配套材料", 3000);
          });
        }
        this._unmount = () => { window.removeEventListener("scroll", spy); Graph.stop(); };
      },
      unmount() { if (this._unmount) this._unmount(); },
    };
  };

  // 案例详情页的轻量导出（正文 + 参考文献）
  async function exportDetail(c, v) {
    const parts = [{
      heading: "案例正文",
      markdown: Store.blocksOf(v).map((b) => b.kind === "h2" ? "## " + b.text : b.text).join("\n\n"),
    }];
    if (v.kit && v.kit.design) parts.push({ heading: "教学设计", markdown: v.kit.design });
    if (v.kit && (v.kit.discussion || []).length)
      parts.push({ heading: "课堂讨论题", markdown: v.kit.discussion.map((d, i) => `${i + 1}. ${d}`).join("\n") });
    if (v.kit && (v.kit.ppt || []).length)
      parts.push({ heading: "PPT 提纲", markdown: v.kit.ppt.map((d, i) => `${i + 1}. ${d}`).join("\n") });
    const refs = (v.citations || []).map((r) => {
      const t = H.citeName(r.target);
      return { title: t.name, source: t.src || "" };
    });
    const statusNote = c.status === "published" ? "已发布公开版" : "草稿（仅供内部教学参考）";
    const resp = await fetch("/api/export-docx", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        title: v.title,
        meta: {
          author: v.author || Store.userById(c.ownerId).name,
          audience: Store.audienceName(v.audience),
          caseType: Store.typeName(v.typeId), course: v.course || "-",
          mode: "公开版导出", statusNote,
          footerNote: `上海大学思政教学案例智能平台 · 生成时间：${U.now()} · 状态：${statusNote}`,
        },
        parts, refs,
      }),
    });
    if (!resp.ok) { U.toast("导出失败"); return; }
    const blob = await resp.blob();
    U.download(v.title + ".docx", blob);
    U.toast("已导出");
  }

  // ------------------------------------------------------------ 真实文件切片预览（ADR 0010/0011）
  // 目录树 + 分页 + ?sec 深链；素材详情页与教材主页共用（每页一个实例，id 不冲突）
  P.fileSliceCard = (opts) => {
    const finfo = Store.fileInfo(opts.fileId);
    const fmtSize = (n) => (n >= 1048576 ? (n / 1048576).toFixed(1) + " MB" : Math.max(1, Math.round(n / 1024)) + " KB");
    return {
      html: `
      <div class="row spread">
        <span class="small muted" style="word-break:break-all">${U.esc(finfo ? finfo.name : opts.fallbackName)}${finfo ? " · " + fmtSize(finfo.size) : ""}</span>
        <button class="btn sm" id="md-download" style="flex-shrink:0;white-space:nowrap">下载文件</button>
      </div>
      <div class="row" id="md-pager" style="display:none;gap:8px;margin-top:8px">
        <button class="btn sm plain" id="md-prev">上一节</button>
        <span class="small muted" id="md-pos" style="align-self:center"></span>
        <button class="btn sm plain" id="md-next">下一节</button>
        <a id="md-sec-link" class="btn sm plain" style="display:none;margin-left:auto" href="#">知识节 →</a>
      </div>
      <div style="display:flex;gap:12px;margin-top:10px">
        <div id="md-toc" style="display:none;min-width:150px;max-width:min(240px,42%);max-height:420px;overflow:auto;border-right:1px dashed var(--line);padding-right:10px"></div>
        <div class="snapshot-box article" id="md-fileview" style="white-space:normal;flex:1;margin-top:0;min-width:0">文件加载中…</div>
      </div>`,
      mount() {
        const fv = U.$("#md-fileview");
        const fi0 = Store.fileInfo(opts.fileId);
        const nm0 = ((fi0 || {}).name || "").toLowerCase();
        // 非 md/txt 原始文件不可直接预览：上传的 docx 等若服务端已抽取纯文本（textPath），
        // 拉全文截断预览（前 4000 字 + 下载查看全文）；无抽取文本的（如 pdf）提示不支持
        const useTextPreview = !/\.(md|markdown|txt)$/.test(nm0) && !!(fi0 && fi0.textPath);
        if (useTextPreview) {
          Store.apiFetch("/api/files/" + encodeURIComponent(opts.fileId) + "/text").then(async (resp) => {
            let d = {}; try { d = await resp.json(); } catch (e) { /* 非 JSON */ }
            if (d && d.ok && String(d.text || "").trim()) {
              const t = String(d.text);
              const cut = t.length > 4000;
              fv.innerHTML = U.md(t.slice(0, 4000)) +
                (cut ? `<div class="small muted" style="margin-top:8px">……仅展示前 4000 字，完整内容请点上方「下载文件」查看全文。</div>` : "");
            } else {
              fv.textContent = "该格式暂不支持在线预览，请下载查看。";
            }
          }).catch(() => { fv.textContent = "该格式暂不支持在线预览，请下载查看。"; });
        }
        if (!useTextPreview) Store.apiFetch("/api/files/" + encodeURIComponent(opts.fileId)).then(async (resp) => {
          if (!resp.ok) {
            let d = {}; try { d = await resp.json(); } catch (e) { /* 非 JSON */ }
            fv.textContent = d.error || "文件加载失败";
            return;
          }
          const text = await resp.text();
          const nm = ((Store.fileInfo(opts.fileId) || {}).name || "").toLowerCase();
          if (!/\.(md|markdown|txt)$/.test(nm)) {
            fv.textContent = "该格式不支持在线预览，请下载查看。";
            return;
          }
          const chunks = U.chunkMd(text);
          if (chunks.length <= 1) { fv.innerHTML = U.md(text); return; }
          const showToc = opts.showToc !== false;
          const toc = U.$("#md-toc"), pager = U.$("#md-pager");
          pager.style.display = "flex";
          if (showToc) {
            toc.style.display = "block";
            toc.innerHTML = chunks.map((c, i) =>
              `<a href="javascript:void 0" data-sec="${i}" class="toc-item" style="padding-left:${6 + c.level * 12}px">${c.path !== "0" ? `<span class="muted">${U.esc(c.path)}</span> ` : ""}${U.esc(c.h || "文首")}</a>`
            ).join("");
          }
          let idx = 0;
          const show = (i, updateUrl) => {
            idx = Math.max(0, Math.min(chunks.length - 1, i));
            const c = chunks[idx];
            fv.innerHTML = (c.h ? `<div style="font-weight:600;margin-bottom:6px">${U.esc(c.h)}</div>` : "") + U.md(c.text);
            U.$("#md-pos").textContent = (c.path !== "0" ? c.path + " · " : "") + "第 " + (idx + 1) + " / " + chunks.length + " 节";
            U.$("#md-prev").disabled = idx <= 0;
            U.$("#md-next").disabled = idx >= chunks.length - 1;
            if (showToc) U.$$(".toc-item", toc).forEach((a, j) => a.classList.toggle("active", j === idx));
            const lk = opts.secLink && opts.secLink(c.path);
            const la = U.$("#md-sec-link");
            if (lk) { la.style.display = ""; la.href = lk.href; la.textContent = lk.text; }
            else la.style.display = "none";
            if (updateUrl !== false) {
              history.replaceState(null, "", opts.linkBase + "?sec=" + encodeURIComponent(c.path));
            }
          };
          U.$("#md-prev").addEventListener("click", () => show(idx - 1));
          U.$("#md-next").addEventListener("click", () => show(idx + 1));
          if (showToc) U.$$("[data-sec]", toc).forEach((a) => a.addEventListener("click", () => show(Number(a.dataset.sec))));
          const want = String(opts.sec || "").trim();
          const start = want ? chunks.findIndex((c) => c.path === want) : 0;
          show(start >= 0 ? start : 0, start < 0);
        }).catch(() => { fv.textContent = "文件加载失败（服务不可用）"; });
        const dl = U.$("#md-download");
        if (dl) dl.addEventListener("click", async () => {
          dl.disabled = true;
          try {
            const resp = await Store.apiFetch("/api/files/" + encodeURIComponent(opts.fileId));
            if (!resp.ok) {
              let d = {}; try { d = await resp.json(); } catch (e) { /* 非 JSON */ }
              U.toast(d.error || "下载失败", 3000);
              return;
            }
            const blob = await resp.blob();
            U.download((Store.fileInfo(opts.fileId) || {}).name || (opts.fallbackName + ".md"), blob);
          } finally { dl.disabled = false; }
        });
      },
    };
  };

  // ------------------------------------------------------------ 引入到案例（素材/知识详情共用）
  // 引用体系（ADR 0005）：c.citations 数组顺序 = 正文〔n〕编号；登记后在正文末尾追加引用标记，
  // 新引用排在最后，与正文出现顺序一致，无需重排（工作台后续编辑会由 renumberCitations 自动维护）。
  function intakeToCaseModal(targetId, targetName) {
    const mine = Store.db.cases.filter((c) => c.ownerId === Store.me().id && c.status === "draft");
    const close = U.modal(`
      <div class="modal-head"><b>引入到案例</b><button class="modal-close" data-close>×</button></div>
      <div class="modal-body">
        <p class="small muted" style="margin-bottom:10px">把「${U.esc(targetName)}」登记为案例引用，并在正文末尾追加引用标记〔n〕，随后跳转到工作台继续写作。</p>
        ${mine.length ? mine.map((c) => {
          const cited = Store.isCited(c, targetId);
          return `<div class="row spread" style="padding:6px 0;border-bottom:1px dashed var(--line)">
            <span>${U.esc(c.title)}${cited ? ` <span class="tag green">已引用</span>` : ""}</span>
            <button class="btn sm ${cited ? "plain" : ""}" data-intake="${c.id}">${cited ? "打开工作台" : "引入"}</button>
          </div>`;
        }).join("") : `<p class="small muted">你还没有写作中的案例。<a href="#/new" data-close>去新建案例 →</a></p>`}
      </div>`, { sticky: true });
    U.$$("[data-intake]").forEach((b) => b.addEventListener("click", () => {
      const c = Store.caseById(b.dataset.intake);
      if (!c) return;
      if (Store.isCited(c, targetId)) {
        U.toast("该案例已引用过此资源，未重复登记");
      } else {
        Store.cite(c, targetId);
        const n = (c.citations || []).findIndex((r) => r.target === targetId) + 1;
        const bs = Store.blocksOf(c);
        if (bs.length) bs[bs.length - 1].text = String(bs[bs.length - 1].text || "") + `〔${n}〕`;
        else bs.push({ kind: "p", text: `〔${n}〕` });
        Store.setBlocks(c, bs);
        Store.touch(c);
        U.toast(`已登记引用〔${n}〕，标记追加在正文末尾`);
      }
      close();
      location.hash = "#/workbench/" + c.id;
    }));
  }

  // ------------------------------------------------------------ 素材详情
  P.materialDetail = (id, params) => {
    const m = Store.materialById(id);
    if (!m) return P.notFound("素材不存在，或超出你的授权范围");
    const me = Store.me();
    const citing = Store.casesCiting(id);
    const usage = Store.materialUsage(id);
    const dormant = Store.isDormant(m);
    const dated = Store.isPolicyDated(m);
    const fcard = m.fileId ? P.fileSliceCard({
      fileId: m.fileId, fallbackName: m.title,
      sec: params && params.sec, linkBase: "#/material/" + m.id,
    }) : null;
    const credInfo = {
      high: ["权威来源", "green", "白名单机构或官方发布，可直接引用"],
      normal: ["一般来源", "", "已登记来源，引用时建议注明出处"],
      low: ["待核实", "amber", "非白名单来源，引用前需人工核验事实与授权"],
    }[m.credibility] || ["一般来源", "", ""];
    return {
      html: `
      <div class="detail-grid">
        <div>
          <div class="card card-pad">
            <h2 style="font-size:19px">${U.esc(m.title)}</h2>
            <div class="row wrap" style="margin-bottom:10px">
              ${H.levelTag(m.level)}
              ${H.gradeTag(m.grade)}
              <span class="tag ${credInfo[1]}" title="${U.esc(credInfo[2])}">${credInfo[0]}</span>
              <span class="tag">${U.esc(m.kind)}</span>
              ${m.status !== "正常" ? `<span class="tag red">${U.esc(m.status)}</span>` : ""}
              ${dormant ? `<span class="tag amber" title="入库超过 30 天且从未被引用">待淘汰</span>` : ""}
            </div>
            <div class="cred-note small muted">${U.esc(credInfo[2])}</div>
            ${dated ? `<div class="date-hint">该文件发布于 ${U.esc(String(m.publishedAt).slice(0, 4))} 年，距今超过 3 年，引用时请注意时效性与最新表述。</div>` : ""}
            <table class="meta-table">
              <tr><th>来源</th><td>${U.esc(m.source)}</td></tr>
              ${m.sourceUrl ? `<tr><th>原始链接</th><td><a href="${U.esc(m.sourceUrl)}" target="_blank" rel="noopener">${U.esc(m.sourceUrl)}</a></td></tr>` : ""}
              <tr><th>信源等级</th><td>${m.grade ? U.esc(m.grade) + " 级" : "未定级"}${m.gradeReason ? `<span class="small muted"> — ${U.esc(m.gradeReason)}</span>` : ""}</td></tr>
              <tr><th>发布时间</th><td>${U.esc(m.publishedAt)}</td></tr>
              <tr><th>采集时间</th><td>${U.esc(m.collectedAt)}</td></tr>
              <tr><th>适用范围</th><td>${U.esc(m.scope)}</td></tr>
              <tr><th>使用度</th><td>被 ${usage.count} 个案例引用${usage.lastAt ? " · 最近 " + U.esc(usage.lastAt) : ""}</td></tr>
            </table>
            <hr class="hr">
            <p>${U.esc(m.summary)}</p>
            <div class="row wrap" style="margin-top:8px">
              <button class="btn sm" id="md-intake" title="把该素材登记为我的案例引用，并转到工作台继续写作">引入到案例</button>
              <button class="btn sm ${Store.isFavMat(m) ? "" : "plain"}" id="md-fav">${Store.isFavMat(m) ? "已收藏" : "收藏"}</button>
              <button class="btn sm plain" id="md-copyid" title="复制后粘贴到工作台 Copilot，即可把该素材加入案例引用">复制引用 ID</button>
              ${m.sourceUrl ? `<button class="btn sm plain" id="md-refetch" title="按原始链接重新采集，更新内容副本">重新采集</button>` : ""}
            </div>
          </div>
          ${fcard ? `<div class="card" style="margin-top:14px">
            <div class="card-pad section-title" style="border-bottom:1px solid var(--line)"><span>真实文件</span></div>
            <div class="card-pad">${fcard.html}</div>
          </div>` : `<div class="result-group" style="margin-top:14px">
            <div class="section-title"><span>内容副本（采集于 ${U.esc(U.plainDate(m.collectedAt))}）</span></div>
            <div class="snapshot-box">${U.esc(m.excerpt || "该素材未保存内容副本。")}</div>
          </div>`}
        </div>
        <div>
          ${citing.length ? `<div class="card" style="margin-bottom:14px">
            <div class="card-pad section-title" style="border-bottom:1px solid var(--line)"><span>引用该素材的案例</span></div>
            ${citing.map((c) => H.caseItem(c, c.status === "published" ? "#/case/" + c.id : "#/workbench/" + c.id)).join("")}
          </div>` : `<div class="card card-pad muted small" style="margin-bottom:14px">暂无案例引用</div>`}
          ${me.admin ? `<div class="card card-pad">
            <div class="section-title"><span>管理</span></div>
            <label class="field"><span>密级</span>
              <select class="text" id="md-level">
                <option value="0" ${m.level === 0 ? "selected" : ""}>公开</option>
                <option value="1" ${m.level === 1 ? "selected" : ""}>校内</option>
                <option value="2" ${m.level === 2 ? "selected" : ""}>受限</option>
              </select></label>
            <label class="field"><span>信源等级</span>
              <select class="text" id="md-grade">
                ${["", "S", "A", "B", "C"].map((g) => `<option value="${g}" ${m.grade === g ? "selected" : ""}>${g || "未定级"}</option>`).join("")}
              </select></label>
            <label class="field"><span>定级依据</span>
              <input class="text" id="md-gradereason" value="${U.esc(m.gradeReason || "")}" placeholder="定级依据（如：教育部官网首发）"></label>
            <label class="field"><span>可信度</span>
              <select class="text" id="md-cred">
                <option value="high" ${m.credibility === "high" ? "selected" : ""}>权威来源</option>
                <option value="normal" ${m.credibility === "normal" ? "selected" : ""}>一般来源</option>
                <option value="low" ${m.credibility === "low" ? "selected" : ""}>待核实</option>
              </select></label>
            <label class="field"><span>状态</span>
              <select class="text" id="md-status">
                ${["候选", "正常", "来源失效", "停用"].map((s) => `<option ${m.status === s ? "selected" : ""}>${s}</option>`).join("")}
              </select></label>
            <label class="field"><span>标签</span>
              <div class="row wrap" id="mtag-box">
                ${(m.tags || []).map((t) => `<span class="tag blue">${U.esc(t)}<a href="javascript:void 0" class="tag-x" data-mtag-del="${U.esc(t)}">×</a></span>`).join("")}
                <input class="tag-input" id="mtag-add" placeholder="+ 标签">
              </div></label>
            <div class="row">
              <button class="btn sm" id="md-save">保存</button>
              <a class="btn sm plain" href="#/admin/materials?q=${encodeURIComponent(m.title)}" title="在管理后台素材管理中检索定位该素材">后台定位 →</a>
            </div>
          </div>` : ""}
        </div>
      </div>`,
      mount() {
        U.$("#md-intake").addEventListener("click", () => intakeToCaseModal(m.id, m.title));
        U.$("#md-fav").addEventListener("click", async () => { if (await Store.toggleFavMat(m)) P.rerender(); });
        U.$("#md-copyid").addEventListener("click", () => {
          (navigator.clipboard ? navigator.clipboard.writeText(m.id) : Promise.reject())
            .then(() => U.toast(`已复制 ${m.id}，粘贴到工作台 Copilot 即可引用`))
            .catch(() => U.toast(m.id, 4000));
        });
        const rf = U.$("#md-refetch");
        if (rf) rf.addEventListener("click", async () => {
          rf.disabled = true;
          rf.textContent = "采集中…";
          const res = await Copilot.fetchUrl(m.sourceUrl);
          rf.disabled = false;
          rf.textContent = "重新采集";
          if (!res.ok) { U.toast(res.error || "采集失败", 3000); return; }
          const ok = await Store.updateMaterial(m.id, {
            title: res.title || m.title,
            excerpt: (res.text || "").slice(0, 2000),
            collectedAt: U.plainDate(U.now()),
          });
          if (ok) { U.toast("内容副本已更新"); P.rerender(); }
        });
        const btn = U.$("#md-save");
        if (btn) btn.addEventListener("click", async () => {
          const ok = await Store.updateMaterial(m.id, {
            level: Number(U.$("#md-level").value),
            grade: U.$("#md-grade").value,
            gradeReason: U.$("#md-gradereason").value.trim(),
            credibility: U.$("#md-cred").value,
            status: U.$("#md-status").value,
          });
          if (ok) { U.toast("已保存"); P.rerender(); }
        });
        U.$$("[data-mtag-del]").forEach((b) => b.addEventListener("click", async () => {
          await Store.setMaterialTags(m.id, (m.tags || []).filter((x) => x !== b.dataset.mtagDel));
          P.rerender();
        }));
        const addInp = U.$("#mtag-add");
        if (addInp) addInp.addEventListener("keydown", async (e) => {
          if (e.key === "Enter" && addInp.value.trim()) {
            await Store.setMaterialTags(m.id, (m.tags || []).concat([addInp.value.trim()]));
            P.rerender();
          }
        });
        // 真实文件：切片预览 + 下载（共享组件，ADR 0010）
        if (fcard) fcard.mount();
      },
    };
  };

  // ------------------------------------------------------------ 知识详情
  P.knowledgeDetail = (id) => {
    const k = Store.knowledgeById(id);
    if (!k) return P.notFound();
    const ch = Store.db.chapters.find((x) => x.id === k.chapterId);
    const siblings = (ch ? ch.sections : []).map((sid) => Store.knowledgeById(sid)).filter(Boolean);
    const idx = siblings.findIndex((s) => s.id === id);
    const prev = siblings[idx - 1], next = siblings[idx + 1];
    const citing = Store.casesCiting(id);
    const src = Store.db.knowledgeSources.find((s) => s.id === "ks-zr");
    return {
      html: `
      <div class="detail-grid">
        <div class="card card-pad article">
          <div class="small muted" style="margin-bottom:8px">
            ${U.esc(Store.db.book.title)} · ${U.esc(k.chapter)}
          </div>
          <h2 style="font-size:19px">${U.esc(k.title)}</h2>
          ${k.text.split(/\n{2,}/).map((p) => `<p>${U.esc(p)}</p>`).join("")}
          <hr class="hr">
          <div class="row spread">
            ${prev ? `<a class="btn sm plain" href="#/knowledge/${prev.id}">上一节</a>` : "<span></span>"}
            ${next ? `<a class="btn sm plain" href="#/knowledge/${next.id}">下一节</a>` : "<span></span>"}
          </div>
        </div>
        <div>
          <div class="card card-pad" style="margin-bottom:14px">
            <div class="section-title"><span>来源</span></div>
            <table class="meta-table">
              <tr><th>教材</th><td><a href="#/book">${U.esc(Store.db.book.title)}</a></td></tr>
              <tr><th>版本</th><td>${U.esc(src ? src.version : Store.db.book.edition)}</td></tr>
              <tr><th>更新</th><td>${U.esc(src ? src.updatedAt : "")}</td></tr>
              <tr><th>章节</th><td>${U.esc(k.chapter)}</td></tr>
              ${k.fileSec ? `<tr><th>原始文件</th><td><a href="#/book?sec=${U.esc(k.fileSec)}">打开教材此节（切片 ${U.esc(k.fileSec)}）→</a></td></tr>` : ""}
            </table>
            ${ch ? `<hr class="hr"><div class="section-title small"><span>${U.esc(ch.title)}</span></div>
            <div class="row wrap">${siblings.map((s) => `<a class="tag ${s.id === id ? "primary" : ""}" href="#/knowledge/${s.id}">${U.esc(s.title)}</a>`).join("")}</div>` : ""}
            ${Store.me().admin ? `<hr class="hr"><a class="btn sm plain" href="#/admin/knowledge" title="在管理后台知识管理中查看">后台定位 →</a>` : ""}
          </div>
          <div class="card card-pad" style="margin-bottom:14px">
            <button class="btn sm" id="kn-intake" style="width:100%" title="把本节登记为我的案例引用，并转到工作台继续写作">引入到案例</button>
          </div>
          <div class="card">
            <div class="card-pad section-title" style="border-bottom:1px solid var(--line)"><span>被引用于（${citing.length} 个案例）</span></div>
            ${citing.map((c) => H.caseItem(c, c.status === "published" ? "#/case/" + c.id : "#/workbench/" + c.id)).join("") || `<div class="card-pad muted small">还没有案例引用本节</div>`}
          </div>
        </div>
      </div>`,
      mount() {
        U.$("#kn-intake").addEventListener("click", () => intakeToCaseModal(k.id, k.chapter + " " + k.title));
      },
    };
  };

  // ------------------------------------------------------------ 教材主页（知识层级入口，ADR 0011）
  // 章节目录（按章分页，节标签驱动切片）+ 原始文件切片预览；#/book?sec=<路径> 深链
  P.bookPage = (params) => {
    const bf = Store.db.bookFile;
    const src = Store.db.knowledgeSources.find((s) => s.id === "ks-zr");
    const sec = (params && params.sec) || "";
    const knOfSec = (path) => Store.db.knowledge.find((x) => x.fileSec === path);
    const activeKn = knOfSec(sec);
    const activeCh = activeKn ? activeKn.chapterId : Store.db.chapters[0].id;
    const fcard = bf ? P.fileSliceCard({
      fileId: bf.fileId, fallbackName: bf.title, sec: sec, linkBase: "#/book",
      showToc: false,
      secLink: (path) => {
        const k = knOfSec(path);
        return k ? { href: "#/knowledge/" + k.id, text: "知识节 →" } : null;
      },
    }) : null;
    const secsHtml = (chId) => {
      const ch = Store.db.chapters.find((x) => x.id === chId);
      return (ch ? ch.sections : []).map((sid) => {
        const s = Store.knowledgeById(sid);
        if (!s || !s.fileSec) return "";
        return `<a class="tag ${s.fileSec === sec ? "primary" : ""}" href="#/book?sec=${U.esc(s.fileSec)}">${U.esc(s.title)}</a>`;
      }).join("");
    };
    return {
      html: `
      <div class="detail-grid">
        <div>
          ${fcard ? `<div class="card">
            <div class="card-pad section-title" style="border-bottom:1px solid var(--line)"><span>原始文件（标题树派生切片）</span></div>
            <div class="card-pad">${fcard.html}</div>
          </div>` : ""}
        </div>
        <div>
          <div class="card card-pad">
            <h2 style="font-size:19px">${U.esc(Store.db.book.title)}</h2>
            <div class="row wrap" style="margin-bottom:10px">
              <span class="tag primary">知识</span>
              <span class="tag">${U.esc(Store.db.book.edition)}</span>
              <span class="tag green">已导入 ${Store.db.knowledge.length} 节</span>
            </div>
            <table class="meta-table">
              <tr><th>来源</th><td>${U.esc(src ? src.name : "")}</td></tr>
              <tr><th>版本</th><td>${U.esc(src ? src.version : Store.db.book.edition)}</td></tr>
              <tr><th>更新</th><td>${U.esc(src ? src.updatedAt : "")}</td></tr>
              <tr><th>结构</th><td>${Store.db.book.chapters} 章 / ${Store.db.book.sections} 节</td></tr>
            </table>
            ${bf ? `<p class="small muted" style="margin-top:8px">${U.esc(bf.summary || "")}</p>` : ""}
          </div>
          <div class="card" style="margin-top:14px">
            <div class="card-pad section-title" style="border-bottom:1px solid var(--line)"><span>章节目录（知识）</span></div>
            <div class="card-pad">
              <select class="text" id="bk-ch" style="width:100%">
                ${Store.db.chapters.map((ch) => `<option value="${ch.id}" ${ch.id === activeCh ? "selected" : ""}>${U.esc(ch.title)}</option>`).join("")}
              </select>
              <div class="row wrap" id="bk-secs" style="margin-top:10px">${secsHtml(activeCh)}</div>
            </div>
          </div>
        </div>
      </div>`,
      mount() {
        if (fcard) fcard.mount();
        const sel = U.$("#bk-ch");
        if (sel) sel.addEventListener("change", () => {
          U.$("#bk-secs").innerHTML = secsHtml(sel.value);
        });
      },
    };
  };
})();
