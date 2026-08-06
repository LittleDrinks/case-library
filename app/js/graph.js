// 知识图谱：Canvas 力导向渲染（无第三方依赖）；数据源 = 服务端 Neo4j 图谱（WP7，/api/graph/*）。
// 交互（ADR 0004）：单击浮卡、双击直达详情；全库轻量图 = 教材骨架+案例（overview），
// 案例展开/详情页引用图 = 两跳 ego 子图。
window.Pages = window.Pages || {};
(function () {
  const G = {};
  let raf = null;

  const COLORS = {
    chapter: "#1f5fa8",   // 知识·章
    section: "#7aa7d9",   // 知识·节
    case: "#9e2b25",      // 案例
    material: "#1e7d4f",  // 素材
    tag: "#b07d2b",       // 标签
  };
  const NAMES = { chapter: "知识 · 章", section: "知识 · 节", case: "案例", material: "素材", tag: "标签" };

  // 跨渲染保留节点位置，展开素材时布局不跳动
  const posCache = {};

  // ---------------- 服务端图谱数据（WP7：Neo4j，降级时返回 {ok:false, degraded:true}） ----------------
  const get = (path) => Store.apiFetch(path).then((r) => r.json()).catch(() => null);
  G.fetchOverview = () => get("/api/graph/overview");
  G.fetchEgo = (type, id) => get("/api/graph/ego?type=" + encodeURIComponent(type)
    + "&id=" + encodeURIComponent(id));
  G.qa = (q) => Store.apiFetch("/api/graph/qa", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ q }),
  }).then((r) => r.json()).catch(() => null);

  // 子图并入基图（案例展开素材引用时布局不跳动）：按节点 id / 边三元组去重
  G.mergeData = (base, sub) => {
    const nodes = {};
    base.nodes.forEach((n) => { nodes[n.id] = n; });
    (sub.nodes || []).forEach((n) => { if (!nodes[n.id]) nodes[n.id] = n; });
    const seen = new Set(base.links.map((l) => l.source + "|" + l.target + "|" + l.rel));
    const links = base.links.slice();
    (sub.links || []).forEach((l) => {
      const k = l.source + "|" + l.target + "|" + l.rel;
      if (!seen.has(k)) { seen.add(k); links.push(l); }
    });
    return { nodes: Object.values(nodes), links };
  };

  // opts.data：{nodes, links}（必填，来自 fetchOverview/fetchEgo/mergeData）
  // opts.noCache：不读不写全局 posCache（局部图避免与全库图串位置）
  G.render = (canvas, opts) => {
    opts = opts || {};
    G.stop();
    const { nodes, links } = opts.data || { nodes: [], links: [] };
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

  window.Graph = G;
})();
