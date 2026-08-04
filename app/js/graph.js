// 知识图谱：全库轻量模式（教材骨架+案例，素材按需展开）+ 局部 ego 引用图（Canvas/SVG，无第三方依赖）
// 依据 docs/adr/0004：单击浮卡、双击打开；素材不单独成点，点开案例后展开其引用。
window.Pages = window.Pages || {};
(function () {
  const G = {};
  let raf = null;

  const COLORS = {
    chapter: "#1f5fa8",   // 知识·章
    section: "#7aa7d9",   // 知识·节
    case: "#9e2b25",      // 案例
    material: "#1e7d4f",  // 素材
  };
  const NAMES = { chapter: "知识 · 章", section: "知识 · 节", case: "案例", material: "素材" };

  // 跨渲染保留节点位置，展开素材时布局不跳动
  const posCache = {};

  // opts.includeMaterials：素材也成点（默认 false）
  // opts.expanded：Set<caseId>，这些案例的素材引用临时展开
  // opts.data：直接给定 {nodes, links}（如详情页 ego 图），跳过 buildData
  // opts.noCache：不读不写全局 posCache（局部图避免与全库图串位置）
  G.buildData = (opts) => {
    opts = opts || {};
    const expanded = opts.expanded || new Set();
    const nodes = {}, links = [];
    const addNode = (id, label, type, ref) => {
      if (!nodes[id]) nodes[id] = { id, label, type, ref };
      return nodes[id];
    };
    Store.visibleCases().forEach((c) => {
      addNode(c.id, c.title, "case", { kind: "case", id: c.id });
      (c.citations || []).forEach((r) => {
        const kn = Store.knowledgeById(r.target);
        if (kn) {
          addNode(kn.id, kn.title, "section", { kind: "knowledge", id: kn.id });
          const ch = Store.db.chapters.find((x) => x.id === kn.chapterId);
          if (ch) {
            addNode(ch.id, ch.title, "chapter", { kind: "chapter", id: ch.id });
            links.push({ source: ch.id, target: kn.id, rel: "包含" });
          }
          links.push({ source: c.id, target: kn.id, rel: "引用理论" });
          return;
        }
        if (!opts.includeMaterials && !expanded.has(c.id)) return;
        const m = Store.materialById(r.target);
        if (m) {
          addNode(m.id, m.title, "material", { kind: "material", id: m.id });
          links.push({ source: c.id, target: m.id, rel: "引用素材" });
        }
      });
    });
    return { nodes: Object.values(nodes), links };
  };

  G.render = (canvas, opts) => {
    opts = opts || {};
    G.stop();
    const { nodes, links } = opts.data || G.buildData(opts);
    const highlight = opts.highlight || new Set();
    const cache = opts.noCache ? {} : posCache;
    const ctx = canvas.getContext("2d");
    const dpr = window.devicePixelRatio || 1;
    let W = 0, H = 0;
    const view = { x: 0, y: 0, k: 1 };
    let hover = null, dragNode = null, panning = null, moved = false;

    function resize() {
      const r = canvas.getBoundingClientRect();
      W = r.width; H = r.height;
      canvas.width = W * dpr; canvas.height = H * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    }
    resize();

    nodes.forEach((n, i) => {
      if (cache[n.id]) { n.x = cache[n.id].x; n.y = cache[n.id].y; }
      else {
        const ang = (i / Math.max(1, nodes.length)) * Math.PI * 2;
        const rad = n.type === "chapter" ? 60 : 120 + Math.random() * 160;
        n.x = Math.cos(ang) * rad; n.y = Math.sin(ang) * rad;
      }
      n.vx = 0; n.vy = 0;
      n.r = n.type === "case" ? 9 : n.type === "chapter" ? 8 : n.type === "section" ? 6 : 7;
    });
    const byId = {};
    nodes.forEach((n) => { byId[n.id] = n; });
    canvas._graphNodes = nodes; // 供测试与调试读取节点坐标

    let alpha = 1;
    function tick() {
      for (let i = 0; i < nodes.length; i++) {
        for (let j = i + 1; j < nodes.length; j++) {
          const a = nodes[i], b = nodes[j];
          let dx = b.x - a.x, dy = b.y - a.y;
          let d2 = dx * dx + dy * dy;
          if (d2 < 1) { d2 = 1; dx = Math.random() - .5; dy = Math.random() - .5; }
          const f = (1900 * alpha) / d2;
          const d = Math.sqrt(d2);
          const fx = (dx / d) * f, fy = (dy / d) * f;
          a.vx -= fx; a.vy -= fy; b.vx += fx; b.vy += fy;
        }
      }
      links.forEach((l) => {
        const a = byId[l.source], b = byId[l.target];
        if (!a || !b) return;
        const dx = b.x - a.x, dy = b.y - a.y;
        const d = Math.max(1, Math.hypot(dx, dy));
        const want = l.rel === "包含" ? 70 : 110;
        const f = (d - want) * 0.02 * alpha;
        const fx = (dx / d) * f, fy = (dy / d) * f;
        a.vx += fx; a.vy += fy; b.vx -= fx; b.vy -= fy;
      });
      nodes.forEach((n) => { n.vx -= n.x * 0.004 * alpha; n.vy -= n.y * 0.004 * alpha; });
      nodes.forEach((n) => {
        if (n === dragNode) return;
        n.vx *= 0.85; n.vy *= 0.85;
        n.x += n.vx; n.y += n.vy;
        cache[n.id] = { x: n.x, y: n.y };
      });
      alpha = Math.max(0.02, alpha * 0.995);
    }

    function draw() {
      ctx.clearRect(0, 0, W, H);
      ctx.save();
      ctx.translate(W / 2 + view.x, H / 2 + view.y);
      ctx.scale(view.k, view.k);
      ctx.strokeStyle = "#d8dce4";
      ctx.lineWidth = 1 / view.k;
      links.forEach((l) => {
        const a = byId[l.source], b = byId[l.target];
        if (!a || !b) return;
        ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
      });
      nodes.forEach((n) => {
        ctx.beginPath();
        ctx.arc(n.x, n.y, n.r, 0, Math.PI * 2);
        ctx.fillStyle = COLORS[n.type];
        ctx.fill();
        if (highlight.has(n.id)) {
          ctx.beginPath();
          ctx.arc(n.x, n.y, n.r + 4 / view.k, 0, Math.PI * 2);
          ctx.lineWidth = 2 / view.k; ctx.strokeStyle = "#BA1C22"; ctx.stroke();
        }
        if (n === hover) { ctx.lineWidth = 2 / view.k; ctx.strokeStyle = "#1f2329"; ctx.stroke(); }
        ctx.fillStyle = "#4b5261";
        ctx.font = `${11 / view.k}px sans-serif`;
        ctx.textAlign = "center";
        const label = n.label.length > 11 ? n.label.slice(0, 10) + "…" : n.label;
        ctx.fillText(label, n.x, n.y + n.r + 12 / view.k);
      });
      ctx.restore();
    }

    function loop() {
      tick(); draw();
      raf = requestAnimationFrame(loop);
    }
    loop();

    const toWorld = (e) => {
      const r = canvas.getBoundingClientRect();
      return {
        x: (e.clientX - r.left - W / 2 - view.x) / view.k,
        y: (e.clientY - r.top - H / 2 - view.y) / view.k,
        sx: e.clientX - r.left, sy: e.clientY - r.top,
      };
    };
    const nodeAt = (p) => {
      for (let i = nodes.length - 1; i >= 0; i--) {
        const n = nodes[i];
        if (Math.hypot(n.x - p.x, n.y - p.y) <= n.r + 3) return n;
      }
      return null;
    };

    const tip = opts.tip;
    canvas.onmousemove = (e) => {
      const p = toWorld(e);
      if (dragNode) {
        moved = true;
        dragNode.x = p.x; dragNode.y = p.y;
        dragNode.vx = 0; dragNode.vy = 0;
        alpha = Math.max(alpha, 0.1);
        return;
      }
      if (panning) {
        view.x += e.clientX - panning.x; view.y += e.clientY - panning.y;
        panning = { x: e.clientX, y: e.clientY };
        moved = true;
        return;
      }
      const n = nodeAt(p);
      hover = n;
      canvas.style.cursor = n ? "pointer" : "grab";
      if (tip) {
        if (n) {
          tip.style.display = "block";
          tip.style.left = (p.sx + 14) + "px";
          tip.style.top = (p.sy + 10) + "px";
          tip.textContent = NAMES[n.type] + " · " + n.label;
        } else tip.style.display = "none";
      }
    };
    canvas.onmousedown = (e) => {
      const p = toWorld(e);
      const n = nodeAt(p);
      moved = false;
      if (n) { dragNode = n; }
      else { panning = { x: e.clientX, y: e.clientY }; canvas.style.cursor = "grabbing"; }
    };
    canvas.onmouseup = (e) => {
      if (dragNode) alpha = Math.max(alpha, 0.08);
      dragNode = null;
      if (panning) { panning = null; canvas.style.cursor = "grab"; }
      if (moved) return; // 拖拽不算点击
      const p = toWorld(e);
      const n = nodeAt(p);
      if (n && opts.onCard) opts.onCard(n, { x: p.sx, y: p.sy });
    };
    canvas.ondblclick = (e) => {
      const p = toWorld(e);
      const n = nodeAt(p);
      if (n && opts.onOpen) opts.onOpen(n);
      else { view.x = 0; view.y = 0; view.k = 1; }
    };
    canvas.onmouseleave = () => {
      dragNode = null; panning = null;
      if (tip) tip.style.display = "none";
    };
    canvas.onwheel = (e) => {
      e.preventDefault();
      const k0 = view.k;
      view.k = Math.min(3, Math.max(0.3, view.k * (e.deltaY > 0 ? 0.9 : 1.1)));
      const r = canvas.getBoundingClientRect();
      const mx = e.clientX - r.left - W / 2, my = e.clientY - r.top - H / 2;
      view.x = mx - (mx - view.x) * (view.k / k0);
      view.y = my - (my - view.y) * (view.k / k0);
    };
    window.addEventListener("resize", resize);
  };

  G.stop = () => { if (raf) cancelAnimationFrame(raf); raf = null; };
  G.COLORS = COLORS;
  G.NAMES = NAMES;

  // ----------------------------------------------------------
  // 两跳 ego 数据装配（ADR 0008）：案例 → 引用的知识节/素材 → 同样引用该目标的其他案例（≤6）
  // citationsOverride：详情页传发布快照的引用，默认用案例当前引用
  G.egoData = (caseId, citationsOverride) => {
    const c = Store.db.cases.find((x) => x.id === caseId);
    if (!c) return { nodes: [], links: [] };
    const cites = citationsOverride || c.citations || [];
    const nodes = {}, links = [];
    const add = (id, label, type, ref) => nodes[id] || (nodes[id] = { id, label, type, ref });
    add(c.id, c.title, "case", { kind: "self", id: c.id });
    cites.forEach((r) => {
      const target = typeof r === "string" ? r : r.target;
      const kn = Store.knowledgeById(target);
      const m = kn ? null : Store.materialById(target); // 不可见素材不进图
      if (!kn && !m) return;
      const t = kn
        ? { id: kn.id, label: kn.title, type: "section", ref: { kind: "knowledge", id: kn.id } }
        : { id: m.id, label: m.title, type: "material", ref: { kind: "material", id: m.id } };
      add(t.id, t.label, t.type, t.ref);
      links.push({ source: c.id, target: t.id, rel: "引用" });
      Store.casesCiting(t.id).filter((oc) => oc.id !== c.id && Store.canSeeCase(oc)).slice(0, 6)
        .forEach((oc) => {
          add(oc.id, oc.title, "case", { kind: "case", id: oc.id });
          links.push({ source: oc.id, target: t.id, rel: "引用" });
        });
    });
    return { nodes: Object.values(nodes), links };
  };

  window.Graph = G;
})();
