// 通用工具
(function () {
  const U = {};

  U.$ = (sel, root) => (root || document).querySelector(sel);
  U.$$ = (sel, root) => Array.from((root || document).querySelectorAll(sel));

  U.esc = (s) => String(s == null ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");

  U.uid = (p) => (p || "id") + "-" + Date.now().toString(36) + "-" + Math.random().toString(36).slice(2, 7);

  U.now = () => {
    const d = new Date();
    const p = (n) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
  };

  U.debounce = (fn, ms) => {
    let t;
    return function (...args) { clearTimeout(t); t = setTimeout(() => fn.apply(this, args), ms); };
  };

  U.toast = (msg, ms) => {
    const root = U.$("#toast-root");
    const el = document.createElement("div");
    el.className = "toast";
    el.textContent = msg;
    root.appendChild(el);
    setTimeout(() => el.remove(), ms || 2400);
  };

  U.modal = (html, opts) => {
    const root = U.$("#modal-root");
    root.innerHTML = `<div class="modal-mask"><div class="modal">${html}</div></div>`;
    const close = () => { root.innerHTML = ""; };
    U.$(".modal-mask", root).addEventListener("mousedown", (e) => {
      if (e.target.classList.contains("modal-mask") && !(opts && opts.sticky)) close();
    });
    U.$$("[data-close]", root).forEach((b) => b.addEventListener("click", close));
    return close;
  };

  U.confirmModal = (msg, opts) => new Promise((resolve) => {
    const danger = opts && opts.danger;
    const close = U.modal(`
      <div class="modal-head"><b>${U.esc((opts && opts.title) || "确认操作")}</b><button class="modal-close" data-close>×</button></div>
      <div class="modal-body"><p>${U.esc(msg)}</p></div>
      <div class="modal-foot">
        <button class="btn plain" data-close>取消</button>
        <button class="btn ${danger ? "danger" : ""}" id="cm-ok">确认</button>
      </div>`, { sticky: true });
    const done = (v) => { close(); resolve(v); };
    U.$("#cm-ok").addEventListener("click", () => done(true));
    U.$$("[data-close]").forEach((b) => b.addEventListener("click", () => done(false)));
    U.$(".modal-mask").addEventListener("mousedown", (e) => {
      if (e.target.classList.contains("modal-mask")) done(false);
    });
  });

  // 中文查询理解：切分 → 去停用词 → 长词补子串召回 → 同义扩展
  const STOP_WORDS = ["的", "了", "和", "与", "及", "或", "而", "并", "关于", "有关", "相关", "主题", "案例", "素材", "知识", "我想", "想找", "我要", "请", "帮我", "有没有", "哪些", "什么", "怎么", "怎样", "如何", "一下", "能否", "可以", "推荐", "查找", "寻找", "搜索", "介绍", "讲解", "分析", "一篇", "围绕", "需要"];

  const SYNONYMS = {
    "科技兴国": ["科教兴国", "科技报国", "科技自立自强"],
    "科教兴国": ["科技兴国", "科技报国"],
    "科技强国": ["科技自立自强", "科技报国", "科教兴国"],
    "卡脖子": ["科技自立自强", "供应链", "断供"],
    "断供": ["供应链", "卡脖子"],
    "大思政": ["大思政课"],
    "思政课": ["课程思政"],
    "场馆": ["实践教学基地", "图书馆"],
    "图书馆": ["场馆", "实践教学基地"],
    "芯片": ["微电子", "集成电路"],
    "医工": ["医工交叉", "交叉创新"],
    "交叉": ["交叉创新", "交叉学科", "医工交叉"],
    "人工智能": ["生成式人工智能", "AIGC", "智能控制"],
    "aigc": ["生成式人工智能", "人工智能"],
    "科学家": ["科学家精神"],
  };

  U.terms = (q) => {
    const chunks = String(q || "").split(/[\s,，、。；;：:？?！!（）()《》“”"'·\-—/]+/).filter(Boolean);
    const words = new Set();
    chunks.forEach((chunk) => {
      let parts = [chunk];
      STOP_WORDS.forEach((sw) => {
        const next = [];
        parts.forEach((p) => p.split(sw).forEach((x) => next.push(x)));
        parts = next;
      });
      parts.forEach((p) => { if (p.length >= 2) words.add(p); });
    });
    // 长词补充 2-3 字子串，提升召回
    Array.from(words).slice().forEach((w) => {
      if (w.length >= 4) {
        for (let i = 0; i + 3 <= w.length; i++) words.add(w.slice(i, i + 3));
        for (let i = 0; i + 2 <= w.length; i++) words.add(w.slice(i, i + 2));
      }
    });
    // 同义扩展
    Array.from(words).slice().forEach((w) => {
      const syn = SYNONYMS[w] || SYNONYMS[w.toLowerCase()];
      if (syn) syn.forEach((x) => words.add(x));
    });
    return Array.from(words).slice(0, 30);
  };

  // 在文本中查找命中片段，长词权重更高，返回 {score, hits:[{term, context}]}
  U.matchText = (text, terms) => {
    let score = 0;
    const hits = [];
    const t = String(text || "");
    for (const term of terms) {
      const w = term.length >= 4 ? 3 : term.length === 3 ? 2 : 1;
      let idx = t.indexOf(term), count = 0;
      while (idx >= 0 && count < 20) { count++; idx = t.indexOf(term, idx + term.length); }
      if (count) {
        score += count * w;
        if (hits.length < 3) {
          const at = t.indexOf(term);
          hits.push({ term, context: t.slice(Math.max(0, at - 24), at + term.length + 24) });
        }
      }
    }
    return { score, hits };
  };

  U.highlight = (text, terms) => {
    let html = U.esc(text);
    for (const term of terms) {
      html = html.split(U.esc(term)).join(`<mark>${U.esc(term)}</mark>`);
    }
    return html;
  };

  // 〔n〕引用链接化：默认先 escape 原文再做标记替换；escaped:true 表示输入已是安全 HTML（如 U.md 输出）
  // sources 为 [{n, type, id, title}]，type 取 case/knowledge/material（兼容中文 案例/知识/素材），n 缺省按数组序号
  const CITE_TYPES = { "案例": "case", "知识": "knowledge", "素材": "material", case: "case", knowledge: "knowledge", material: "material" };
  const CITE_HREF = { case: "#/case/", knowledge: "#/knowledge/", material: "#/material/" };
  const CITE_NAMES = { case: "案例", knowledge: "知识", material: "素材" };
  U.linkifyCitations = (text, sources, opts) => {
    const html = opts && opts.escaped ? String(text == null ? "" : text) : U.esc(text);
    const byN = {};
    (sources || []).forEach((s, i) => {
      if (!s) return;
      const n = s.n != null ? Number(s.n) : i + 1;
      byN[n] = { type: CITE_TYPES[s.type] || s.type, id: s.id, title: s.title || "" };
    });
    return html.replace(/〔(\d{1,2})〕/g, (m, n) => {
      const s = byN[Number(n)];
      if (!s || !s.id || !CITE_HREF[s.type]) return m;
      return `<a class="ai-cite" href="${CITE_HREF[s.type]}${U.esc(s.id)}" title="${U.esc(CITE_NAMES[s.type])}｜${U.esc(s.title)}">〔${n}〕</a>`;
    });
  };

  // ------------------------------------------------------------ 句级引用锚点（WP3）
  // 引用带 quote（被引用句原文片段，文本指纹）时，〔n〕上标定位到 quote 对应句子后；
  // quote 在正文中找不到时退化为块尾并标「锚点漂移」；无 quote 的引用保持字面位置。
  // 返回 {blockIdx: [{n, at(quote 在该块文本中的结束位置, -1=块尾), drift}]}
  U.citeAnchors = (blocks, citations) => {
    const anchors = {};
    const push = (bi, a) => { (anchors[bi] = anchors[bi] || []).push(a); };
    (citations || []).forEach((r, i) => {
      const n = i + 1;
      const probe = String((r && r.quote) || "").trim().slice(0, 30);
      if (!probe) return;
      let hit = -1, at = -1;
      (blocks || []).forEach((b, bi) => {
        if (hit >= 0) return;
        const p = String(b.text || "").indexOf(probe);
        if (p >= 0) { hit = bi; at = p + probe.length; }
      });
      if (hit >= 0) { push(hit, { n, at, drift: false }); return; }
      // 锚点漂移：挂到字面〔n〕所在块（没有则最后一块）的块尾
      let bi2 = (blocks || []).findIndex((b) => String(b.text || "").includes("〔" + n + "〕"));
      if (bi2 < 0) bi2 = Math.max(0, (blocks || []).length - 1);
      push(bi2, { n, at: -1, drift: true });
    });
    return anchors;
  };

  const citeMarkHTML = (n, isBad, drift) =>
    `<a class="cite-mark${drift ? " drift" : ""}" data-cite-jump="${n}"` +
    (drift ? ` title="锚点漂移：被引用句已改动，标记移至块尾"` : "") + `>〔${n}〕</a>` +
    (isBad && isBad(n) ? `<i class="cite-bad" title="素材已停用或来源失效">来源失效</i>` : "");

  // 渲染一个正文块：有锚点的引用从字面位置剔除、按锚点放置（占位符先于转义插入，避免转义改变偏移）；
  // isBad(n) 判定该编号引用的来源是否失效（角标）
  U.markCites = (text, blockIdx, anchors, isBad) => {
    const anchored = {};
    Object.keys(anchors || {}).forEach((k) => (anchors[k] || []).forEach((a) => { anchored[a.n] = true; }));
    let t = String(text == null ? "" : text).replace(/〔(\d+)〕/g,
      (m, n) => (anchored[Number(n)] ? "" : m));
    const marks = ((anchors || {})[blockIdx] || []).slice();
    marks.filter((a) => a.at >= 0).sort((a, b) => b.at - a.at).forEach((a) => {
      t = t.slice(0, a.at) + "\u0001" + a.n + (a.drift ? "d" : "") + "\u0002" + t.slice(a.at);
    });
    marks.filter((a) => a.at < 0).forEach((a) => { t += "\u0001" + a.n + "d\u0002"; });
    return U.esc(t)
      .replace(/〔(\d+)〕/g, (m, n) => citeMarkHTML(Number(n), isBad, false))
      .replace(/\u0001(\d+)(d?)\u0002/g, (m, n, d) => citeMarkHTML(Number(n), isBad, d === "d"));
  };

  U.download = (filename, blob) => {
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 800);
  };

  U.postJSON = async (url, payload) => {
    const resp = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload || {}),
    });
    const ctype = resp.headers.get("Content-Type") || "";
    if (ctype.includes("application/json")) return resp.json();
    return resp;
  };

  U.plainDate = (s) => String(s || "").slice(0, 10);

  // 行级文字 diff（LCS），返回 [{t:" "|"+"|"-", s}]，供版本对比用
  U.diffLines = (oldText, newText) => {
    const a = String(oldText || "").split("\n");
    const b = String(newText || "").split("\n");
    const n = a.length, m = b.length;
    const dp = Array.from({ length: n + 1 }, () => new Array(m + 1).fill(0));
    for (let i = n - 1; i >= 0; i--) {
      for (let j = m - 1; j >= 0; j--) {
        dp[i][j] = a[i] === b[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1]);
      }
    }
    const out = [];
    let i = 0, j = 0;
    while (i < n && j < m) {
      if (a[i] === b[j]) { out.push({ t: " ", s: a[i] }); i++; j++; }
      else if (dp[i + 1][j] >= dp[i][j + 1]) { out.push({ t: "-", s: a[i] }); i++; }
      else { out.push({ t: "+", s: b[j] }); j++; }
    }
    while (i < n) out.push({ t: "-", s: a[i++] });
    while (j < m) out.push({ t: "+", s: b[j++] });
    return out;
  };

  // 派生切片（ADR 0010，与 tools/build_data.py 同一规则）：
  // 按 #{1,3} 标题行把文件切成标题树；文件是数据源，切片是派生物。
  // 地址 = 结构路径：出现的标题级别按 # 数排序为第 1..K 层，
  // 路径 = 各级序号拼接（缺层不占位），如教材 "2.1.1"（章.节.目）、学习资料 "1.4"。
  // 标题前的正文为「文首」块（path "0"）。不合并、不二次切分。
  U.chunkMd = (text) => {
    const lines = String(text || "").split("\n");
    const present = new Set();
    lines.forEach((ln) => {
      const m = /^(#{1,3})\s+/.exec(ln);
      if (m) present.add(m[1].length);
    });
    const ranks = {};
    Array.from(present).sort().forEach((h, i) => { ranks[h] = i + 1; });

    const chunks = [];
    const counters = [0, 0, 0, 0];
    let cur = null;
    const flush = () => {
      if (!cur) return;
      const body = cur.buf.join("\n").trim();
      if (cur.h || body) {
        chunks.push({ a: "s-" + (chunks.length + 1), path: cur.path, level: cur.level, h: cur.h, text: body });
      }
      cur = null;
    };
    lines.forEach((ln) => {
      const m = /^(#{1,3})\s+(.+)$/.exec(ln);
      if (m) {
        flush();
        const r = ranks[m[1].length];
        counters[r] += 1;
        for (let i = r + 1; i <= 3; i++) counters[i] = 0;
        cur = {
          h: m[2].trim(), buf: [], level: r,
          path: counters.slice(1, r + 1).filter((n) => n > 0).join("."),
        };
      } else if (cur) {
        cur.buf.push(ln);
      } else {
        cur = { h: "", buf: [ln], path: "0", level: 0 };
      }
    });
    flush();
    return chunks;
  };

  // 极简 Markdown 渲染（先转义，仅支持粗体/斜体/行内码/标题/列表/段落）
  U.md = (text) => {    let h = U.esc(text == null ? "" : text);
    h = h.replace(/`([^`\n]+)`/g, "<code>$1</code>");
    h = h.replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>");
    h = h.replace(/__([^_]+)__/g, "<b>$1</b>");
    h = h.replace(/(^|\s)\*([^*\n]+)\*(?=\s|$|[，。；：、）])/g, "$1<i>$2</i>");
    h = h.replace(/^\s{0,3}#{1,4}\s+(.+)$/gm, "<b>$1</b>");
    h = h.replace(/^\s*[-*•]\s+(.+)$/gm, "<li>$1</li>");
    h = h.replace(/^\s*(\d{1,2})[.、)]\s*(.+)$/gm, "<li>$1. $2</li>");
    return h.split(/\n{2,}/)
      .map((p) => "<p>" + p.replace(/\n/g, "<br>") + "</p>")
      .join("");
  };

  window.U = U;
})();
