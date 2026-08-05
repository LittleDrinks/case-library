// 页面：案例工作台。作者模式（可编辑）与审核模式（只读 + 审核动作）共用同一份代码。
// 依据 docs/adr/0001：批注是所有反馈的统一载体；审核页 = 工作台只读模式。
window.Pages = window.Pages || {};
(function () {
  const P = window.Pages;
  const H = P.H;

  P.notFound = P.notFound || ((msg) => ({
    html: `<div class="card card-pad" style="max-width:520px;margin:40px auto;text-align:center">
      <p class="muted">${U.esc(msg || "内容不存在，或你无权查看")}</p>
      <a class="btn plain" href="#/home">返回首页</a></div>`,
    mount() {},
  }));

  P.workbench = (id) => P.workbenchView(id, { mode: "author" });

  P.workbenchView = (id, opts) => {
    opts = opts || {};
    const mode = opts.mode || "author";
    const reviewer = mode === "review";
    const c = Store.caseById(id);
    if (!c) return P.notFound();
    const me = Store.me();
    const mine = c.ownerId === me.id || me.admin;
    // 版本模型（ADR 0001）：只有草稿态可编辑；提交后冻结；审核模式永远只读
    const editable = () => !reviewer && mine && c.status === "draft";
    let tab = reviewer ? "anno" : "copilot";
    let resView = "list"; // 资料页签引用区：列表/图谱（ADR 0008）
    let wsResults = [];
    let pendingIntent = null, lastChipText = "";
    let selQuote = null; // 选区引用 chip：待发送的选区原文（发送/移除/切换案例后清除）
    let citeAnchor = null; // 最近一次正文选区 {text, blockIdx}：挂引用时作句级锚点（quote）
    const annoFilter = { status: new Set(["pending"]), kind: new Set() };
    const chat = [];
    let sending = false;
    const convoKey = (reviewer ? "review:" : "workbench:") + c.id; // 多轮会话键：作者/审核各自独立
    let cpView = "chat"; // Copilot 面板子页签：对话/记录
    let historyLoaded = false; // 会话历史气泡只载入一次
    let streamHandle = null;   // 进行中的流式请求句柄（页面卸载时 abort）
    let phaseTimer = null, paintTimer = null; // 阶段切换定时器与增量渲染节流
    let showDiff = false;
    let pendingFetch = null;
    let rvOpinion = "", rvFrom = "", rvReasonType = "";
    let selBtn = null;

    // ---------------- 正文模型 ----------------
    let focusBlock = 0;
    const blocksOf = () => Store.blocksOf(c);

    function logicalSections() {
      const bs = blocksOf();
      const secs = [];
      let cur = { title: "", from: 0, to: bs.length };
      bs.forEach((b, i) => {
        if (b.kind === "h2") {
          cur.to = i;
          if (cur.to > cur.from) secs.push(cur);
          cur = { title: b.text, from: i, to: bs.length };
        }
      });
      if (cur.to > cur.from) secs.push(cur);
      return secs.length ? secs : [{ title: "", from: 0, to: bs.length }];
    }
    function sectionOfBlock(idx) {
      const secs = logicalSections();
      const i = secs.findIndex((s) => idx >= s.from && idx < s.to);
      return i < 0 ? 0 : i;
    }
    function blockLabel(idx) {
      const s = logicalSections()[sectionOfBlock(idx)];
      return (s && s.title) || "正文开头";
    }

    // 引用编号按正文出现顺序自动重排（ADR 0005），并同步改写正文里的〔n〕；
    // 带 quote 的引用（WP3 句级锚点）按 quote 句位置排序，找不到 quote 时按字面〔n〕位置
    function renumberCitations() {
      const cites = c.citations || [];
      if (!cites.length) return;
      const bs = blocksOf();
      const pos = cites.map((r, i) => {
        const probe = String((r && r.quote) || "").trim().slice(0, 30);
        if (probe) {
          for (let bi = 0; bi < bs.length; bi++) {
            const p = bs[bi].text.indexOf(probe);
            if (p >= 0) return { bi, p, i };
          }
        }
        const re = new RegExp("〔" + (i + 1) + "〕");
        for (let bi = 0; bi < bs.length; bi++) {
          const m = re.exec(bs[bi].text);
          if (m) return { bi, p: m.index, i };
        }
        return { bi: bs.length + 1, p: i, i }; // 未出现在正文：保持相对顺序排尾
      });
      const newOrder = pos.slice().sort((a, b) => a.bi - b.bi || a.p - b.p).map((x) => x.i);
      if (newOrder.every((v, i) => v === i)) return;
      const map = {};
      newOrder.forEach((oi, ni) => { map[oi] = ni + 1; });
      let changed = false;
      bs.forEach((b) => {
        const t = b.text.replace(/〔(\d+)〕/g, (s, n) => {
          const oi = Number(n) - 1;
          return map[oi] != null ? "〔" + map[oi] + "〕" : s;
        });
        if (t !== b.text) { b.text = t; changed = true; }
      });
      c.citations = newOrder.map((i) => cites[i]);
      if (changed) Store.setBlocks(c, bs);
      Store.saveCase(c);
    }

    // ---------------- 文档渲染 ----------------
    // 只读模式下正文里的〔n〕渲染为可点击锚点（句级定位：有 quote 的引用跟在 quote 句后，
    // 找不到 quote 退化块尾并标「锚点漂移」；来源失效的引用带角标），点击打开证据面板
    const citeAnchorsOf = () => U.citeAnchors(blocksOf(), c.citations || []);
    const citeBad = (n) => Store.citeFailed((c.citations || [])[n - 1]);
    function markCites(text, bi) {
      return U.markCites(text, bi, citeAnchorsOf(), citeBad);
    }

    // ---------------- 证据面板（WP3） ----------------
    function evidenceVM(n) {
      const r = (c.citations || [])[n - 1];
      if (!r) return null;
      const t = H.citeName(r.target);
      const kn = t.kind === "knowledge";
      const m = kn ? null : Store.db.materials.find((x) => x.id === r.target);
      const ev = r.evidence || {};
      return {
        n, r, kn, ev, t,
        title: t.name,
        source: t.src || "",
        grade: m ? m.grade : "",
        publishedAt: m ? (m.publishedAt || "") : (kn ? (Store.db.book.edition || "") : ""),
        failed: Store.citeFailed(r),
        deepHref: kn ? "#/knowledge/" + t.id
          : "#/material/" + t.id + (ev.sec ? "?sec=" + encodeURIComponent(ev.sec) : ""),
      };
    }

    function showEvidence(n) {
      const vm = evidenceVM(n);
      const box = U.$("#evd-box");
      if (!box) return;
      if (!vm) { box.innerHTML = ""; return; }
      const ev = vm.ev;
      // 命中句高亮：quote 探针在证据片段中出现时加 mark
      let snip = U.esc(ev.snippet || "");
      const probe = String(vm.r.quote || "").trim().slice(0, 12);
      if (probe && ev.snippet && ev.snippet.indexOf(probe) >= 0) {
        snip = snip.split(U.esc(probe)).join(`<mark>${U.esc(probe)}</mark>`);
      }
      box.innerHTML = `<div class="evd-drawer">
        <div class="row spread">
          <b>证据 · 引用〔${vm.n}〕</b>
          <button class="btn sm plain" data-evd-close>×</button>
        </div>
        <div class="row wrap" style="margin:6px 0">
          ${vm.grade ? H.gradeTag(vm.grade) : ""}
          ${vm.failed ? `<span class="tag red">来源失效</span>` : ""}
          ${ev.sec ? `<span class="tag">切片 ${U.esc(ev.sec)}</span>` : ""}
        </div>
        <h5 style="margin:2px 0">${U.esc(vm.title)}</h5>
        <div class="small muted">${U.esc(vm.source)}${vm.publishedAt ? " · 发布 " + U.esc(vm.publishedAt) : ""}</div>
        ${snip ? `<div class="evd-snip">${snip}</div>` : `<div class="small muted" style="margin-top:8px">暂无证据片段（老引用未回填）</div>`}
        ${vm.r.quote ? `<div class="small muted" style="margin-top:8px">正文锚点句：${U.esc(vm.r.quote.slice(0, 60))}</div>` : ""}
        <div class="row spread" style="margin-top:10px">
          <a class="btn sm plain" href="${vm.deepHref}">打开原文切片 →</a>
          ${ev.capturedAt ? `<span class="small muted">采集 ${U.esc(ev.capturedAt)}</span>` : ""}
        </div>
      </div>`;
    }

    const refsHTML = () => {
      const cites = c.citations || [];
      if (!cites.length) return "";
      return `<div class="doc-refs" id="doc-refs">
        <div class="doc-refs-title">参考文献</div>
        ${cites.map((r, i) => {
          const t = H.citeName(r.target);
          if (t.visible === false) return "";
          return `<div class="doc-ref-item" id="ref-${i + 1}">
            <a href="javascript:void 0" data-cite-locate="${i + 1}" title="定位到正文引用处">〔${i + 1}〕</a>
            ${t.kind === "knowledge"
              ? `<a href="#/knowledge/${t.id}">${U.esc(t.name)}</a>`
              : `<a href="#/material/${t.id}">${U.esc(t.name)}</a>`}
            <span class="small muted"> — ${U.esc(t.src || "")}</span>
            ${Store.citeFailed(r) ? `<span class="tag red sm">来源失效</span>` : ""}
            <a href="javascript:void 0" class="small" data-evd="${i + 1}" title="查看证据片段">证据</a>
          </div>`;
        }).join("")}
      </div>`;
    };

    // 块渲染：h2/p 之外支持 ul/ol 列表与 blockquote 引用块（列表块 text 为一项一行，引用块为一行一段）。
    // render 为文本转义函数：编辑态传 U.esc，只读态传 markCites
    const blockHTML = (b, render) => {
      if (b.kind === "h2") return `<h2>${render(b.text)}</h2>`;
      if (b.kind === "ul" || b.kind === "ol") {
        const items = String(b.text).split("\n").map((s) => s.trim()).filter(Boolean);
        return `<${b.kind}>${items.map((t) => `<li>${render(t)}</li>`).join("")}</${b.kind}>`;
      }
      if (b.kind === "quote") {
        const lines = String(b.text).split("\n").map((s) => s.trim()).filter(Boolean);
        return `<blockquote>${lines.map((t) => render(t)).join("<br>")}</blockquote>`;
      }
      return `<p>${render(b.text)}</p>`;
    };

    const docHTML = () => `
    <div class="doc-page">
      <div class="doc-head">
        ${editable()
          ? `<input class="doc-title-input" id="wb-title" value="${U.esc(c.title)}" placeholder="案例标题">`
          : `<h1 class="doc-title">${U.esc(c.title)}</h1>`}
        <div class="doc-meta row wrap">
          ${H.typeTag(c.typeId)} ${H.audTag(c.audience)}
          <span class="tag">${U.esc(c.course || "未定课程")}</span>
          <span class="tag">${U.esc(c.purpose || "")}</span>
        </div>
        <div class="doc-meta row wrap" style="border-bottom:none;padding-bottom:10px">
          ${Store.tagsOf("case", c).map((t) => `<span class="tag blue">${U.esc(t)}${editable() ? `<a href="javascript:void 0" class="tag-x" data-tag-del="${U.esc(t)}" title="移除标签">×</a>` : ""}</span>`).join("")}
          ${editable() ? `
          <input class="tag-input" id="case-tag-add" placeholder="+ 标签">
          <button class="btn sm plain" id="tag-suggest" title="按正文关键词推荐标签">建议标签</button>` : ""}
        </div>
      </div>
      ${editable() ? `
      <div class="doc-tools">
        <button data-fmt="bold" title="加粗选中文字"><b>B</b></button>
        <button data-fmt="h2" title="将当前段落设为标题">标题</button>
        <button data-fmt="p" title="将当前段落设为正文">正文</button>
        <button data-fmt="ul" title="无序列表">• 列表</button>
        <button data-fmt="ol" title="有序列表">1. 列表</button>
        <button data-fmt="quote" title="引用块">❝ 引用</button>
      </div>` : ""}
      <div class="doc-editor" id="doc-editor" ${editable() ? "contenteditable='true' spellcheck='false'" : ""}>${blocksOf().map((b, bi) =>
        blockHTML(b, editable() ? U.esc : (txt) => markCites(txt, bi))).join("")}</div>
      ${refsHTML()}
    </div>`;

    function serializeDoc() {
      const ed = U.$("#doc-editor");
      if (!ed || !editable()) return;
      const bs = [];
      Array.from(ed.childNodes).forEach((node) => {
        if (node.nodeType === 3) {
          node.textContent.split(/\n+/).map((s) => s.trim()).filter(Boolean)
            .forEach((t) => bs.push({ kind: "p", text: t }));
          return;
        }
        if (node.nodeType !== 1) return;
        const tag = node.tagName;
        // 列表：每个 li 一项，整块存为一个 ul/ol 块（text 一项一行）
        // Chrome 的 insertUnorderedList 有时把列表嵌在 p/div 里而不是替换它，
        // 此时容器除列表外没有实质文本，等价处理（把嵌套列表提升到块级识别）
        let listEl = tag === "UL" || tag === "OL" ? node : null;
        if (!listEl && tag !== "BLOCKQUOTE") {
          const nested = node.querySelector(":scope > ul, :scope > ol");
          if (nested) {
            const ownText = Array.from(node.childNodes)
              .filter((n) => n !== nested)
              .map((n) => n.textContent.trim()).join("");
            if (!ownText) listEl = nested;
          }
        }
        if (listEl) {
          const items = Array.from(listEl.querySelectorAll("li"))
            .map((li) => li.innerText.replace(/\s*\n+\s*/g, " ").trim()).filter(Boolean);
          if (items.length) bs.push({ kind: listEl.tagName === "UL" ? "ul" : "ol", text: items.join("\n") });
          return;
        }
        // 引用块：整块存为一个 quote 块（text 一行一段）
        if (tag === "BLOCKQUOTE") {
          const lines = node.innerText.split(/\n+/).map((s) => s.trim()).filter(Boolean);
          if (lines.length) bs.push({ kind: "quote", text: lines.join("\n") });
          return;
        }
        const kind = /^H[12]$/.test(tag) ? "h2" : "p";
        node.innerText.split(/\n+/).map((s) => s.trim()).filter(Boolean)
          .forEach((t) => bs.push({ kind, text: t }));
      });
      Store.setBlocks(c, bs);
      Store.touch(c);
      Copilot.invalidateContext(c.id); // 正文变了，清该案例的 Copilot 上下文缓存
      setSaveState("已保存 " + U.now().slice(11));
    }

    // ---------------- 提案-采纳守卫基线 ----------------
    const docPlainText = () => blocksOf().map((b) => b.text).join("\n");
    // djb2 全文 hash：发送时记入 msg.meta.workHash，采纳前校验正文是否在生成后被改动
    const workHash = (s) => {
      let h = 5381;
      for (let i = 0; i < s.length; i++) h = ((h << 5) + h + s.charCodeAt(i)) >>> 0;
      return h.toString(36);
    };
    // 空白归一化后 indexOf：返回 needle 在 hay 中的原文坐标与全文档唯一性；未命中返回 null
    function matchNormalized(hay, needle) {
      const nn = String(needle || "").replace(/\s+/g, "");
      if (!nn) return null;
      const map = []; // 归一化串下标 → 原串下标
      let nh = "";
      for (let i = 0; i < hay.length; i++) {
        if (!/\s/.test(hay[i])) { nh += hay[i]; map.push(i); }
      }
      const first = nh.indexOf(nn);
      if (first < 0) return null;
      return { start: map[first], end: map[first + nn.length - 1] + 1, unique: nh.indexOf(nn, first + 1) < 0 };
    }
    // 当前节正文（不含 h2 标题行），作为 diff 与 hash 守卫的 baseText
    function curSectionBody() {
      const bs = blocksOf();
      const sec = logicalSections()[sectionOfBlock(focusBlock)] || { title: "", from: 0, to: bs.length };
      const body = bs.slice(sec.from, sec.to);
      return (body.length && body[0].kind === "h2" ? body.slice(1) : body).map((b) => b.text).join("\n");
    }

    function updateFocus() {
      const ed = U.$("#doc-editor");
      const sel = window.getSelection();
      if (!ed || !sel.anchorNode) return;
      let el = sel.anchorNode.nodeType === 1 ? sel.anchorNode : sel.anchorNode.parentElement;
      while (el && el.parentElement !== ed) el = el.parentElement;
      if (!el) return;
      const idx = Array.from(ed.children).indexOf(el);
      if (idx < 0) return;
      focusBlock = idx;
      Array.from(ed.children).forEach((x) => x.classList.remove("caret"));
      el.classList.add("caret");
      const lbl = U.$("#chat-target");
      if (lbl) lbl.textContent = "当前位置：" + blockLabel(idx);
    }

    // 保存状态字（ADR 0006）
    let saveTimer = null;
    function setSaveState(t) {
      const el = U.$("#save-state");
      if (el) el.textContent = t;
    }
    function onEditing() {
      setSaveState("保存中…");
      clearTimeout(saveTimer);
      saveTimer = setTimeout(() => serializeDoc(), 900);
    }

    // ---------------- 大纲（浮动目录，两种模式都有；作者可编辑时带逐节生成入口） ----------------
    const outlineHTML = () => {
      const hs = blocksOf().map((b, i) => ({ b, i })).filter((x) => x.b.kind === "h2" && x.b.text.trim());
      return `<div id="wb-outline" hidden>
        <div class="small muted" style="margin-bottom:6px">大纲</div>
        ${hs.map((x) => `<div class="wb-outline-row"><a href="javascript:void 0" data-outline="${x.i}">${U.esc(x.b.text)}</a>${editable() ? `<button class="wb-sec-gen" data-sec-gen="${x.i}" title="AI 生成本节">✦</button>` : ""}</div>`).join("") ||
        `<div class="small muted">正文还没有标题</div>`}
      </div>`;
    };

    // ---------------- 头部 ----------------
    const headHTML = () => {
      const checks = Store.selfChecks(c);
      const passed = checks.filter((x) => x.ok).length;
      const level = passed === checks.length ? ["高", "green"] : passed >= checks.length - 2 ? ["中", "amber"] : ["低", "red"];
      const btns = [];
      if (reviewer) {
        btns.push(`<a class="btn plain" href="#/admin/audit">返回队列</a>`);
        const submits = (c.versions || []).filter((v) => v.label.indexOf("提交版") === 0);
        if (submits.length >= 2) btns.push(`<button class="btn plain" id="wb-diff">${showDiff ? "查看当前版本" : "与上一版对比"}</button>`);
      } else {
        if (c.status === "draft" && editable()) {
          btns.push(`<button class="btn plain" id="wb-check" title="提交前自检">完整度 <span class="tag ${level[1]}">${level[0]} ${passed}/${checks.length}</span></button>`);
          btns.push(`<button class="btn" id="wb-submit">提交审核</button>`);
        }
        if (c.status === "pending" && mine) btns.push(`<button class="btn secondary" id="wb-withdraw">撤回提交</button>`);
        if (c.status === "published") btns.push(`<a class="btn secondary" href="#/case/${c.id}">查看公开页</a>`);
        if (c.status === "hidden" && me.admin) btns.push(`<button class="btn secondary" id="wb-unhide">恢复发布</button>`);
        btns.push(`<button class="btn plain" id="wb-versions">历史版本</button>`);
        btns.push(`<button class="btn plain" id="wb-export">导出</button>`);
        if (c.status === "draft" && editable()) btns.push(`<button class="btn plain" id="wb-delete">删除</button>`);
      }
      btns.push(`<button class="btn plain" id="wb-outline-btn">大纲</button>`);
      const frozenNote = c.status === "pending" ? "已提交待审，内容已冻结"
        : c.status === "reviewing" ? "管理员审核中，内容已冻结" : "";
      return `
      <div class="wb-head">
        <div class="row wrap">
          ${H.statusTag(c.status)}
          ${frozenNote ? `<span class="tag blue">${frozenNote}</span>` : ""}
          ${c.status === "hidden" ? `<span class="tag red">已被管理员隐藏</span>` : ""}
          ${editable() ? `<span class="small muted" id="save-state">已保存 ${U.esc((c.updatedAt || "").slice(11) || "")}</span>` : ""}
          <span class="small muted">更新 ${U.esc(c.updatedAt)}</span>
        </div>
        <div class="row wrap">${btns.join("")}</div>
      </div>`;
    };

    // ---------------- Copilot ----------------
    const scene = reviewer ? "review" : "write";
    // AI 未配置（flags 缺失不拦截，仅 === false 时前置提示）
    const aiOff = () => !!(Store.flags && Store.flags.aiConfigured === false);

    // 打开面板时把该会话的历史轮次载入气泡（来源 chips 无法恢复，只渲染文本）
    function ensureHistory() {
      if (historyLoaded) return;
      historyLoaded = true;
      Copilot.getHistory(convoKey).forEach((h) => {
        chat.push({ role: h.role === "user" ? "user" : "ai", text: h.content, intent: "chat", actions: [], sources: [] });
      });
    }

    // 本轮引用的来源 chips：每个来源一个小标签链接，点击跳详情页
    const srcChipsHTML = (sources) => {
      if (!sources || !sources.length) return "";
      const href = { case: "#/case/", knowledge: "#/knowledge/", material: "#/material/" };
      return `<div class="ai-srcs">${sources.map((s) => href[s.type]
        ? `<a class="ai-src" href="${href[s.type]}${U.esc(s.id)}" title="${U.esc(s.title)}">${s.n}. ${U.esc(s.title)}</a>`
        : "").join("")}</div>`;
    };

    // AI 回答正文：md 渲染后把句末〔n〕转成可点击的来源链接（输入已是安全 HTML）
    const aiBodyHTML = (m) => U.linkifyCitations(U.md(m.text), m.sources || [], { escaped: true });

    // ---------------- Agent 办公室 ----------------
    // 快捷指令 intent → 统一端点 intentHint；自由输入（chat）不带 hint，走服务端自动路由
    const AGENT_HINT = {
      "find-theory": "find-theory", "find-material": "find-material", review: "review",
      polish: "polish", "adapt-grad": "adapt", "adapt-ug": "adapt", "adapt-embed": "adapt",
      "section-draft": "section-draft",
    };
    // 非快捷指令 intent 的用户气泡标签（快捷指令标签来自 Copilot.quickCommands）
    const EXTRA_LABEL = { "section-draft": "AI 生成本节" };

    // caseContext：当前节标题/正文 + 全文摘录 + 引用列表
    function agentCaseContext() {
      const bs = blocksOf();
      const sec = logicalSections()[sectionOfBlock(focusBlock)] || { title: "", from: 0, to: bs.length };
      return {
        caseId: c.id,
        title: c.title,
        sectionTitle: sec.title || "正文开头",
        sectionText: bs.slice(sec.from, sec.to).map((b) => b.text).join("\n").slice(0, 4000),
        bodyExcerpt: bs.map((b) => b.text).join("\n").slice(0, 1500),
        citations: (c.citations || []).map((r, i) => {
          const t = H.citeName(r.target);
          const ev = r.evidence || {};
          return { n: i + 1, target: r.target, title: t.name, kind: t.kind, note: r.note || "",
                   source: t.src || "", sec: ev.sec || "", snippet: ev.snippet || "" };
        }),
      };
    }

    // 过程链角色徽章（含其工具调用行）；active 为当前工作角色（呼吸高亮）
    const agentRowHTML = (a) => `<div class="cp-agent${a.active ? " on" : ""}">
      <div class="cp-agent-badge"><b>${U.esc(a.label || a.agent || "Agent")}</b>${a.model ? `<span class="cp-agent-model">· ${U.esc(a.model)}</span>` : ""}</div>
      ${a.skill ? `<div class="cp-agent-skill">${U.esc(a.skill)}</div>` : ""}
      ${(a.tools || []).map(agentToolHTML).join("")}
    </div>`;

    const agentToolHTML = (t) => {
      let name = t.tool || "tool";
      if (t.tool === "fetch_url" && t.args && t.args.url) {
        try { name += "（" + new URL(t.args.url).hostname + "）"; } catch (e) { /* ignore */ }
      }
      const icon = t.tool === "fetch_url" ? "🌐" : "🔍";
      return `<div class="cp-agent-tool">${icon} 调用了 ${U.esc(name)}${t.summary ? "：" + U.esc(t.summary) : ""}</div>`;
    };

    // 结果卡片顶部折叠为一行的过程链，点击展开完整链
    const agentsCollapsedHTML = (m, i) => {
      const agents = m.agents || [];
      const names = agents.map((a) => a.label || a.agent).join(" → ");
      const tools = agents.reduce((n, a) => n + (a.tools || []).length, 0);
      return `<div class="cp-agents done">
        <button class="cp-agents-toggle" data-agents-toggle="${i}">
          <span>过程：${U.esc(names)}${tools ? " · " + tools + " 次工具调用" : ""}</span>
          <span class="cp-agents-arrow">${m.agentsOpen ? "收起 ▴" : "展开 ▾"}</span>
        </button>
        ${m.agentsOpen ? `<div class="cp-agents-body">${agents.map(agentRowHTML).join("")}</div>` : ""}
      </div>`;
    };

    // 双候选切换条：主推（模型名）｜备选（模型名）
    const candSwitchHTML = (m, i) => {
      const alt = m.candidates && m.candidates.alt;
      if (!alt || !alt.text) return "";
      return `<div class="cp-cand-switch view-toggle sm">
        <button data-cand="${i}:main" class="${m.cand !== "alt" ? "on" : ""}">主推（${U.esc(m.candidates.main.model || "模型一")}）</button>
        <button data-cand="${i}:alt" class="${m.cand === "alt" ? "on" : ""}">备选（${U.esc(alt.model || "模型二")}）</button>
      </div>`;
    };

    // 改写类提案卡：正文区域从全文展示改为内嵌 diff（baseText 生成时原文 vs 当前候选）
    const useDiff = (m) => !!(m.meta && m.meta.baseText != null &&
      (m.actions || []).some((a) => a.type === "replace" || a.type === "replace-sel"));

    // 行级 diff 渲染：复用版本对比的 diff-add/del/same 行配色；连续未变行超过 6 行折叠（首尾各留 3 行），点击展开
    const diffBodyHTML = (m, i) => {
      const lines = U.diffLines(m.meta.baseText || "", m.text || "");
      const row = (l) => l.t === "+"
        ? `<p class="diff-add">+ ${U.esc(l.s)}</p>`
        : l.t === "-"
          ? `<p class="diff-del">- ${U.esc(l.s)}</p>`
          : `<p class="diff-same">${U.esc(l.s)}</p>`;
      const out = [];
      let k = 0;
      while (k < lines.length) {
        if (lines[k].t !== " ") { out.push(row(lines[k])); k++; continue; }
        let j = k;
        while (j < lines.length && lines[j].t === " ") j++;
        if (j - k > 6 && !(m.diffOpen && m.diffOpen[k])) {
          for (let x = k; x < k + 3; x++) out.push(row(lines[x]));
          out.push(`<button class="cp-diff-fold" data-diff-open="${i}:${k}">… ${j - k - 6} 行未变，点击展开 …</button>`);
          for (let x = j - 3; x < j; x++) out.push(row(lines[x]));
        } else {
          for (let x = k; x < j; x++) out.push(row(lines[x]));
        }
        k = j;
      }
      return `<div class="diff-view cp-diff">${out.join("")}</div>`;
    };

    // 渲染用守卫状态：moved=正文生成后有改动但可确认采纳；stale=改写类按钮禁用并给重发入口
    function guardTag(msg) {
      const meta = msg.meta || {};
      if (!meta.workHash) return null;
      const types = (msg.actions || []).map((a) => a.type);
      if (!types.some((x) => ["replace", "append", "newsec", "replace-sel", "sec-fill"].includes(x))) return null;
      if (workHash(docPlainText()) === meta.workHash) return null;
      if (types.includes("replace") || types.includes("replace-sel")) {
        const m = matchNormalized(docPlainText(), meta.baseText || "");
        return m && m.unique ? "moved" : "stale";
      }
      return "moved"; // append/newsec/sec-fill 不覆盖原文，仅提示确认
    }

    // 审校逐条核对表：✓ 通过 / ! 风险 / ? 待人工确认
    const REVIEW_STATUS = { pass: ["✓", "通过", "green"], risk: ["!", "风险", "red"], confirm: ["?", "待人工确认", "amber"] };
    const reviewTableHTML = (items) => `<div class="cp-review-table">${(items || []).map((it) => {
      const st = REVIEW_STATUS[it.status] || REVIEW_STATUS.confirm;
      return `<div class="cp-review-row">
        <span class="cp-review-ico ${st[2]}">${st[0]}</span>
        <div class="cp-review-body">
          <div class="cp-review-std"><b>${U.esc(it.standard || "未命名检查项")}</b><span class="tag ${st[2]}">${st[1]}</span></div>
          ${it.note ? `<div class="small muted">${U.esc(it.note)}</div>` : ""}
          ${it.ref ? `<div class="small muted">原文：${U.esc(it.ref)}</div>` : ""}
        </div>
      </div>`;
    }).join("")}</div>`;

    // Agent 文本正文：沿用 aiBodyHTML，再把 m-xxx / kn-xxx 素材引用转成可点击链接
    const agentBodyHTML = (m) => aiBodyHTML(m).replace(/\b(?:m|kn)-[a-z0-9][a-z0-9-]*\b/gi, (s) => {
      const id = s.toLowerCase();
      const kn = id.indexOf("kn-") === 0;
      const t = kn ? Store.knowledgeById(id) : Store.materialById(id);
      if (!t) return s;
      return `<a class="ai-cite" href="${kn ? "#/knowledge/" : "#/material/"}${U.esc(id)}" title="${U.esc(kn ? t.chapter + " " + t.title : t.title)}">${s}</a>`;
    });

    // 审校条目 → parseReview 可识别的问题类型（引用/事实/文字/格式/风险）；
    // 引用蕴含不支持（unsupported）按风险批注入库（WP3）
    const reviewAnnoType = (it) => {
      const s = String((it && it.standard) || "");
      if (/蕴含/.test(s) && it && it.status === "risk") return "风险";
      if (/引用|出处|来源/.test(s)) return "引用";
      if (/事实|数据|真实/.test(s)) return "事实";
      if (/文字|错别|标点|语病/.test(s)) return "文字";
      if (/格式|排版/.test(s)) return "格式";
      return it && it.status === "risk" ? "风险" : "事实";
    };

    // 「记录」子页签：该案例的历史 AI 任务，可重放指令
    const taskLogHTML = () => {
      const tasks = c.tasks || [];
      return `<div class="panel-scroll">
        ${tasks.map((t) => `<div class="res-item">
          <div class="row spread"><h5>${U.esc(t.label)}</h5>
            <span class="tag ${t.status === "done" ? "green" : "red"}">${t.status === "done" ? "完成" : "失败"}</span></div>
          <div class="small muted">${U.esc(t.at)} · ${U.esc(t.intent)}${t.elapsed ? " · " + (t.elapsed / 1000).toFixed(1) + "s" : ""}</div>
          ${t.excerpt ? `<div class="small muted task-excerpt">${U.esc(t.excerpt)}</div>` : ""}
          ${t.error ? `<div class="small" style="color:var(--red)">${U.esc(t.error)}</div>` : ""}
          <div style="margin-top:6px"><button class="btn sm plain" data-task-replay="${t.id}">重放该指令</button></div>
        </div>`).join("") || H.empty("暂无 AI 任务记录")}
      </div>`;
    };

    const chatHTML = () => {
      ensureHistory();
      const off = aiOff();
      const subnav = `<div class="cp-subnav row spread">
        <span class="view-toggle sm">
          <button data-cp-view="chat" class="${cpView === "chat" ? "on" : ""}">对话</button>
          <button data-cp-view="log" class="${cpView === "log" ? "on" : ""}">记录</button>
        </span>
        ${cpView === "chat" && chat.length ? `<button class="btn sm plain" data-chat-clear title="清空本会话的对话历史">清空对话</button>` : ""}
      </div>`;
      if (cpView === "log") return subnav + taskLogHTML();
      const msgs = chat.map((m, i) => {
        // 流式消息：生成中（真实阶段指示 + 增量渲染）/ 失败（错误 + 重试）
        if (m.stream) {
          if (m.status === "fail") {
            return `<div class="chat-msg"><div class="bubble">
              <div class="small" style="color:var(--red)">${U.esc(m.error || "生成失败，请重试")}</div>
              <div class="actions"><button class="btn sm plain" data-retry="${i}">重试</button></div>
            </div></div>`;
          }
          return `<div class="chat-msg"><div class="bubble" style="width:100%">
            <div class="cp-agents live" id="cp-agents"${(m.agents || []).length ? "" : " hidden"}>${(m.agents || []).map(agentRowHTML).join("")}</div>
            <div class="stream-phase" id="stream-phase"><span class="dot"></span>${U.esc(m.phase)}</div>
            <div id="stream-bubble">${m.text ? U.md(m.text) : ""}</div>
          </div></div>`;
        }
        const guard = m.role === "user" ? null : guardTag(m);
        const acts = (m.actions || []).map((a, j) => {
          // stale：改写类按钮替换为禁用态，并附重发入口（沿用现有重试 payload）
          if (guard === "stale" && (a.type === "replace" || a.type === "replace-sel")) {
            return `<button class="btn sm ${j === 0 ? "" : "plain"}" disabled title="正文在生成后有改动，已无法定位原文">正文已变化，请重新生成</button>`;
          }
          return `<button class="btn sm ${j === 0 ? "" : "plain"}" data-act="${i}:${j}"${a.transferred ? " disabled" : ""}>${U.esc(a.transferred ? "已转 " + a.transferred + " 条批注" : a.label)}</button>`;
        }).join("") + (guard === "stale" && m.retryPayload ? `<button class="btn sm plain" data-retry="${i}">重新生成</button>` : "");
        let body;
        if (m.role === "user") body = U.esc(m.text);
        else if (m.review) body = reviewTableHTML(m.review);
        else if (m.candidates) body = candSwitchHTML(m, i) + (useDiff(m) ? diffBodyHTML(m, i) : agentBodyHTML(m));
        else if (useDiff(m)) body = diffBodyHTML(m, i);
        else body = m.agent ? agentBodyHTML(m) : aiBodyHTML(m);
        const chain = m.role !== "user" && (m.agents || []).length ? agentsCollapsedHTML(m, i) : "";
        // 禁用词命中警示（WP4b）：服务端在候选 risks 里标注 banned 项，采纳时转 risk 批注
        const bannedHits = (m.risks || []).filter((r) => r.banned);
        const bannedBar = bannedHits.length
          ? `<div class="cp-guard soft">⚠ 命中你的禁用词：${U.esc(bannedHits.map((r) => r.quote).join("、"))}（采纳时将转为风险批注）</div>` : "";
        // hash 守卫提示条：确认态（点采纳后）带确认/取消按钮；moved 为被动提示
        const guardBar = m.confirming
          ? `<div class="cp-guard"><span>正文在生成后有改动${useDiff(m) ? "，以下 diff 基于生成时版本" : ""}，确认采纳？</span><span class="cp-guard-btns"><button class="btn sm" data-guard-ok="${i}">确认采纳</button><button class="btn sm plain" data-guard-no="${i}">取消</button></span></div>`
          : guard === "moved" ? `<div class="cp-guard soft">正文在生成后有改动${useDiff(m) ? "，diff 基于生成时版本" : ""}；采纳前会请你确认。</div>` : "";
        return `<div class="chat-msg ${m.role === "user" ? "user" : ""}"><div class="bubble">${chain}${guardBar}${bannedBar}${body}
          ${m.meta ? `<div class="small" style="opacity:.65;margin-top:6px">${U.esc(m.meta.model || "")} · ${(m.meta.ms / 1000).toFixed(1)}s</div>` : ""}
          ${m.role !== "user" ? srcChipsHTML(m.sources) : ""}
          ${acts ? `<div class="actions">${acts}</div>` : ""}
        </div></div>`;
      }).join("");
      return subnav + `
      ${off ? `<div class="ai-off-banner">${U.esc(Copilot.AI_NOT_CONFIGURED)}</div>` : ""}
      <div class="panel-scroll" id="chat-scroll">
        ${msgs || `<div class="empty">${reviewer ? "让 Copilot 辅助审校，或直接向它提问" : "选择上方快捷指令，或直接输入需求"}</div>`}
      </div>
      <div class="chat-input">
        <div class="quick-chips">${Copilot.quickCommands(c, scene).map((q) =>
          `<button data-quick="${q.intent}" ${off ? "disabled" : ""}>${U.esc(q.label)}</button>`).join("")}</div>
        ${selQuote ? `<div class="cp-sel-chip"><span class="cp-sel-chip-text">选区引用：${U.esc(selQuote.slice(0, 50))}${selQuote.length > 50 ? "…" : ""}</span><button data-sel-clear title="移除选区引用">×</button></div>` : ""}
        <textarea id="chat-text" ${off ? "disabled" : ""} placeholder="${selQuote ? "对选中内容的修改指令…" : reviewer ? "向 Copilot 提问，或让它审校正文" : "输入需求，回车发送；粘贴链接采集素材，粘贴素材 ID（m-xxx）添加引用"}"></textarea>
        <div class="row spread" style="margin-top:6px">
          ${editable() ? `<span class="small muted" id="chat-target">当前位置：${U.esc(blockLabel(focusBlock))}</span>` : `<span></span>`}
          <button class="btn sm" id="chat-send" ${sending || off ? "disabled" : ""}>发送</button>
        </div>
      </div>`;
    };

    // 流式发送：统一 Agent 端点。过程链随 role/tool 帧实时渲染，token 增量渲染 ~80ms 节流
    // opts：{selection?, baseText?, caseContext?, secFrom?, secTitle?}（选区改写/逐节生成入口的附加上下文）
    function sendChat(text, intent, skipDirective, opts) {
      if (sending) return;
      intent = intent || "chat";
      opts = opts || {};
      const sel = opts.selection ? String(opts.selection).slice(0, 2000) : "";

      // 粘贴素材/知识 ID（m-xxx / kn-xxx）→ 直接挂接引用（ADR 0005）
      if (editable() && intent === "chat") {
        const ids = (text.match(/\b(?:m|kn)-[a-z0-9][a-z0-9-]*/gi) || [])
          .filter((x) => Store.citeTarget(x));
        if (ids.length) {
          chat.push({ role: "user", text });
          ids.forEach((x) => cite(x, true));
          const names = ids.map((x) => H.citeName(x).name);
          chat.push({
            role: "ai", intent: "chat", meta: { model: "id-cite", ms: 0 }, actions: [], sources: [],
            text: "已把以下资源加入本案例引用，并在当前位置插入标注：\n" + names.map((n, i) => `${i + 1}. ${n}`).join("\n"),
          });
          drawAll();
          return;
        }
      }

      const label = sel ? "修改选中内容"
        : (Copilot.quickCommands(c, scene).find((q) => q.intent === intent) || {}).label || EXTRA_LABEL[intent] || text.slice(0, 24);
      chat.push({ role: "user", text: intent === "chat" ? text : label + (text ? "：" + text : "") });
      const startAt = Date.now();
      const smsg = { role: "ai", stream: true, status: "doing", phase: "正在接入主Agent…", text: "", altText: "", agents: [] };
      chat.push(smsg);
      sending = true;
      drawPanel();

      // 粘贴链接 → 采集素材（非模型调用，单段等待后直接出结果）
      const urlMatch = text.match(/https?:\/\/[^\s)）]+/);
      if (urlMatch && intent === "chat" && !reviewer) {
        smsg.phase = "正在采集网页…";
        handleFetch(urlMatch[0]).then((res) => {
          sending = false;
          recordTask(label, intent, res, text);
          const idx = chat.indexOf(smsg);
          if (idx >= 0) chat.splice(idx, 1);
          if (res.ok) {
            chat.push({ role: "ai", text: res.content, intent, sources: [],
              meta: { model: res.model || "url-fetch", ms: res.elapsed_ms || 0 }, actions: res.actions || [] });
          } else {
            chat.push({ role: "ai", stream: true, status: "fail",
              error: res.error || "采集失败", retryPayload: { text, intent, skipDirective } });
          }
          drawPanel();
        });
        return;
      }

      // 提案-采纳守卫基线：先冲刷编辑器，再记录全文 hash 与生成目标原文（选区改写时为选区原文）
      if (editable()) serializeDoc();
      const wHash = workHash(docPlainText());
      const baseText = sel || (opts.baseText != null ? opts.baseText : curSectionBody());
      const handle = Copilot.agent({
        text, intentHint: AGENT_HINT[intent],
        caseContext: opts.caseContext || agentCaseContext(),
        selection: sel || undefined,
        conversationKey: convoKey,
        // role：按 agent 名去重复用徽章，最新角色进入呼吸高亮，阶段指示同步为真实进度
        onRole(j) {
          let a = smsg.agents.find((x) => x.agent === j.agent);
          if (!a) { a = { agent: j.agent, label: j.agent, model: "", skill: "", tools: [] }; smsg.agents.push(a); }
          a.label = j.label || a.label;
          a.model = j.model || a.model;
          a.skill = j.skill || a.skill;
          smsg.lastModel = a.model || smsg.lastModel;
          smsg.agents.forEach((x) => { x.active = x === a; });
          setStreamPhase(smsg, (a.label || "Agent") + " 工作中…");
          paintAgents(smsg);
        },
        onTool(j) {
          let a = smsg.agents.find((x) => x.agent === j.agent);
          if (!a) { a = { agent: j.agent, label: j.agent, model: "", skill: "", tools: [] }; smsg.agents.push(a); }
          a.tools.push({ tool: j.tool, args: j.args, summary: j.summary });
          paintAgents(smsg);
        },
        // token：气泡只显示 main 流；writer 备选（alt）在后台静默积累
        onToken(j) {
          if (j.which === "alt") { smsg.altText += j.text || ""; return; }
          smsg.text += j.text || "";
          scheduleStreamPaint();
        },
        onResult() { setStreamPhase(smsg, "整理结果…"); },
        onDone(result) {
          clearTimeout(phaseTimer); clearTimeout(paintTimer); paintTimer = null;
          sending = false; streamHandle = null;
          const ms = Date.now() - startAt;
          smsg.agents.forEach((x) => { x.active = false; });
          if (!result) {
            smsg.status = "fail";
            smsg.error = "Agent 未返回结果，请重试";
            smsg.retryPayload = { text, intent, skipDirective, opts };
            recordTask(label, intent, { ok: false, error: smsg.error }, text);
            drawPanel();
            return;
          }
          const idx = chat.indexOf(smsg);
          if (idx >= 0) chat.splice(idx, 1);
          // 会话历史由 Copilot.agent 内部 appendTurn 记录，页面不再重复补记
          const content = Copilot.agentResultText(result);
          recordTask(label, intent, { ok: true, elapsed_ms: ms, content }, text);
          const msg = {
            role: "ai", intent, agent: true, text: content, actions: [],
            meta: { model: result.model || smsg.lastModel || "", ms },
            sources: [], agents: smsg.agents, agentsOpen: false,
            retryPayload: { text, intent, skipDirective, opts }, // 守卫 stale 态的「重新生成」沿用
          };
          if (result.kind === "candidates" && result.main) {
            // 写作双候选：msg.text 始终镜像当前显示候选，采纳/追加/新节对当前候选生效；
            // chunks 为本次检索资料（采纳时把〔n〕落成真实引用），risks 为后处理校验出的无源引用
            msg.candidates = { main: result.main, alt: result.alt || null };
            msg.cand = "main";
            msg.text = result.main.text || "";
            msg.chunks = result.chunks || [];
            msg.risks = result.main.risks || [];
            msg.meta.model = result.main.model || msg.meta.model;
            msg.meta.workHash = wHash;   // 采纳守卫基线
            msg.meta.baseText = baseText;
            if (editable()) msg.actions = adoptActionsFor(msg, sel, opts);
          } else if (result.kind === "review") {
            msg.review = result.items || [];
            const n = msg.review.filter((it) => it.status !== "pass").length;
            if (n) msg.actions = [{ label: "转为批注（" + n + " 条）", type: "review-annos", items: msg.review }];
          } else {
            msg.text = result.text || "";
            msg.meta.workHash = wHash;
            msg.meta.baseText = baseText;
            msg.actions = editable() && (sel || intent === "section-draft")
              ? adoptActionsFor(msg, sel, opts)
              : actionsFor(intent, msg.text);
          }
          chat.push(msg);
          drawPanel();
        },
        onError(err) {
          clearTimeout(phaseTimer); clearTimeout(paintTimer); paintTimer = null;
          sending = false; streamHandle = null;
          smsg.status = "fail";
          smsg.error = (err && err.message) || String(err || "模型调用失败");
          smsg.retryPayload = { text, intent, skipDirective, opts };
          recordTask(label, intent, { ok: false, error: smsg.error }, text);
          drawPanel();
        },
      });
      streamHandle = handle;
    }

    // 输入框发送（按钮与回车共用）：有选区引用时默认 intent=polish 并携带 selection，发送后清 chip
    function sendFromInput(ta) {
      if (!ta) return;
      const v = (ta.value || "").trim();
      if (!v) return;
      ta.value = "";
      const intent = pendingIntent || (selQuote ? "polish" : "chat");
      const skip = pendingIntent != null;
      const opts = selQuote ? { selection: selQuote } : null;
      pendingIntent = null;
      selQuote = null;
      sendChat(v, intent, skip, opts);
    }

    // 结果卡采纳动作：选区改写只保留「替换选中内容」；逐节生成为写入本节/存为新节；其余写作类为现状三件套
    function adoptActionsFor(msg, sel, opts) {
      if (sel) return [{ label: "替换选中内容", type: "replace-sel" }];
      if (msg.intent === "section-draft") {
        msg.meta.secFrom = opts.secFrom;
        msg.meta.secTitle = opts.secTitle;
        return [{ label: "写入本节", type: "sec-fill" }, { label: "存为新节", type: "newsec" }];
      }
      return [
        { label: "替换当前节", type: "replace" },
        { label: "追加到当前节", type: "append" },
        { label: "存为新节", type: "newsec" },
      ];
    }

    function setStreamPhase(smsg, phase) {
      if (smsg.phase === phase) return;
      smsg.phase = phase;
      const el = U.$("#stream-phase");
      if (el) el.innerHTML = `<span class="dot"></span>${U.esc(phase)}`;
    }

    // 过程链增量渲染：节点少，直接按 smsg.agents 重绘容器，避免全量重绘面板
    function paintAgents(smsg) {
      const box = U.$("#cp-agents");
      if (!box) return;
      box.hidden = false;
      box.innerHTML = smsg.agents.map(agentRowHTML).join("");
      const scroll = U.$("#chat-scroll");
      if (scroll) scroll.scrollTop = scroll.scrollHeight;
    }

    // 增量渲染节流：直接改写流式气泡内容，避免每个 token 全量重绘面板
    function scheduleStreamPaint() {
      if (paintTimer) return;
      paintTimer = setTimeout(() => {
        paintTimer = null;
        const smsg = chat[chat.length - 1];
        const el = U.$("#stream-bubble");
        if (el && smsg && smsg.stream && smsg.status === "doing") {
          el.innerHTML = U.md(smsg.text);
          const scroll = U.$("#chat-scroll");
          if (scroll) scroll.scrollTop = scroll.scrollHeight;
        } else drawPanel();
      }, 80);
    }

    function recordTask(label, intent, res, prompt) {
      c.tasks = c.tasks || [];
      c.tasks.unshift({
        id: U.uid("t"), label, intent, at: U.now(),
        prompt: prompt != null ? prompt : label,
        status: res.ok ? "done" : "fail",
        elapsed: res.elapsed_ms || 0, error: res.error || "",
        excerpt: String(res.content || res.error || "").replace(/\s+/g, " ").trim().slice(0, 140),
      });
      c.tasks = c.tasks.slice(0, 30);
      Store.saveCase(c);
    }

    function actionsFor(intent, content) {
      const acts = [];
      if (editable() && ["polish", "adapt-grad", "adapt-ug", "adapt-embed", "draft"].includes(intent)) {
        acts.push({ label: "替换当前节", type: "replace" }, { label: "追加到当前节", type: "append" }, { label: "存为新节", type: "newsec" });
      } else if (intent === "review") {
        const annos = Copilot.parseReview(c, content);
        if (annos.length) acts.push({ label: `加入批注（${annos.length} 条）`, type: "annos", annos });
      }
      return acts;
    }

    // 采纳守卫层（不改既有分支语义）：hash 一致直接放行；不一致时 append/newsec/sec-fill 仅确认，
    // replace/replace-sel 需 baseText 在当前正文唯一匹配（confirm），匹配失败阻断（stale）
    function adoptGuard(msg, type) {
      const meta = msg.meta || {};
      if (!meta.workHash) return "ok";
      if (editable()) serializeDoc(); // 冲刷未落块的编辑，保证 hash 对的是最新正文
      const same = workHash(docPlainText()) === meta.workHash;
      if (type === "append" || type === "newsec" || type === "sec-fill") return same ? "ok" : "confirm";
      if (same && type === "replace") return "ok"; // 现状路径：整节替换不依赖文本匹配
      const m = matchNormalized(docPlainText(), meta.baseText || "");
      if (m && m.unique) return same ? "ok" : "confirm";
      return same ? "ok" : "stale";
    }

    // 采纳 AI 内容后（WP3）：把〔n〕落成真实引用（quote=所在句、evidence 来自本次检索 chunk）；
    // 服务端后处理标「待核实」的无源引用 → risk 批注（不静默放行）
    async function adoptEvidence(msg) {
      Copilot.materializeCitations(c, msg);
      Store.markAiAssist(c, msg.meta && msg.meta.model); // AI 起草/改写打标 origin + 模型
      for (const rk of msg.risks || []) {
        await Store.addAnnotation(c, {
          kind: "risk", status: "pending", section: 0,
          quote: String(rk.quote || "").replace(/〔\d+[^〕]*〕/g, "").slice(0, 60),
          text: rk.banned
            ? "【教师偏好·禁用词】" + (rk.note || ("命中禁用词「" + rk.quote + "」"))
            : "AI 生成内容中的引用〔" + rk.n + "〕没有对应的检索资料，正文已标「待核实」，请人工核实来源。",
          author: "Copilot", lowRisk: false,
        });
      }
    }

    async function runAction(msg, act, force) {
      const paras = msg.text.split(/\n+/).map((s) => s.trim()).filter(Boolean);
      if (editable() && ["replace", "append", "newsec", "replace-sel", "sec-fill"].includes(act.type)) {
        // hash 守卫层：stale 阻断；confirm 先在结果卡顶部弹确认条，确认后带 force 重进
        const guard = adoptGuard(msg, act.type);
        if (guard === "stale") { msg.confirming = null; U.toast("正文已变化，请重新生成"); drawPanel(); return; }
        if (guard === "confirm" && !force) { msg.confirming = act.type; drawPanel(); return; }
        msg.confirming = null;
        if (act.type === "replace-sel") { await applyReplaceSel(msg); return; }
        if (act.type === "sec-fill") { await applySecFill(msg); return; }
        const bs = blocksOf().slice();
        const secs = logicalSections();
        const sec = secs[sectionOfBlock(focusBlock)] || { title: "", from: 0, to: bs.length };
        if (act.type === "replace") {
          const head = bs[sec.from] && bs[sec.from].kind === "h2" ? [bs[sec.from]] : [];
          bs.splice(sec.from, sec.to - sec.from, ...head, ...paras.map((t) => ({ kind: "p", text: t })));
        } else if (act.type === "append") {
          bs.splice(sec.to, 0, ...paras.map((t) => ({ kind: "p", text: t })));
        } else {
          const h = (paras[0] || "新小节").replace(/^#+\s*/, "").slice(0, 30);
          const rest = paras.length > 1 ? paras.slice(1) : paras;
          bs.splice(sec.to, 0, { kind: "h2", text: h }, ...rest.map((t) => ({ kind: "p", text: t })));
        }
        Store.setBlocks(c, bs);
        Store.touch(c);
        Copilot.invalidateContext(c.id); // AI 内容写入正文，清上下文缓存
        await adoptEvidence(msg);
        U.toast("已写入");
        drawAll();
        return;
      }
      // 审校核对表 → 批注：risk/confirm 条目组装成 parseReview 可解析文本，复用既有批注入库路径
      if (act.type === "review-annos") {
        if (act.transferred) return;
        const lines = (act.items || [])
          .filter((it) => it.status === "risk" || it.status === "confirm")
          .map((it) => "[" + reviewAnnoType(it) + "] " + (it.ref || "") + " | " + (it.note || it.standard || ""));
        const annos = Copilot.parseReview(c, lines.join("\n"));
        if (!annos.length) { U.toast("没有可转入的批注"); return; }
        for (const a of annos) await Store.addAnnotation(c, a);
        act.transferred = annos.length;
        U.toast("已转 " + annos.length + " 条批注");
        drawPanel();
        return;
      }
      if (act.type === "annos") {
        for (const a of act.annos) await Store.addAnnotation(c, a);
        U.toast(`已加入 ${act.annos.length} 条批注`);
        tab = "anno";
        drawAll();
        return;
      }
      if (act.type === "fetch-force" && pendingFetch) {
        const pf = pendingFetch;
        pendingFetch = null;
        const r = await addFetchedMaterial(pf.url, pf.res, true);
        if (r.ok) U.toast("已采集入库（候选池，待管理员确认后进入检索语料）");
        else U.toast(r.error || "采集失败", 3000);
        tab = "res";
        drawAll();
      }
    }

    // 选区改写采纳：在当前正文唯一匹配选区原文（可跨块），替换为提案文本
    async function applyReplaceSel(msg) {
      const m = matchNormalized(docPlainText(), msg.meta.baseText || "");
      if (!m || !m.unique) { U.toast("原文已变化，无法唯一匹配选中内容，请重新生成"); drawPanel(); return; }
      const bs = blocksOf().slice();
      const offs = [];
      let acc = 0;
      bs.forEach((b) => { offs.push(acc); acc += b.text.length + 1; }); // +1 为 docPlainText 拼接的换行
      const locate = (pos) => {
        for (let i = bs.length - 1; i >= 0; i--) if (pos >= offs[i]) return i;
        return 0;
      };
      const sB = locate(m.start);
      const eB = locate(Math.max(m.start, m.end - 1));
      const before = bs[sB].text.slice(0, m.start - offs[sB]);
      const after = bs[eB].text.slice(Math.min(bs[eB].text.length, m.end - offs[eB]));
      const parts = (before + msg.text + after).split(/\n+/).map((s) => s.trim()).filter(Boolean);
      if (!parts.length) parts.push("");
      bs.splice(sB, eB - sB + 1, ...parts.map((t, k) => ({ kind: k === 0 ? bs[sB].kind : "p", text: t })));
      Store.setBlocks(c, bs);
      Store.touch(c);
      Copilot.invalidateContext(c.id);
      await adoptEvidence(msg);
      U.toast("已替换选中内容");
      drawAll();
    }

    // 逐节生成采纳：目标节当前为空 → replace 该节；非空 → append。优先按发送时的块索引定位，失败按标题唯一匹配
    async function applySecFill(msg) {
      const bs = blocksOf().slice();
      const secs = logicalSections();
      const from = msg.meta.secFrom;
      let sec = null;
      if (from != null && bs[from] && bs[from].kind === "h2" && bs[from].text === msg.meta.secTitle) {
        sec = secs.find((s) => s.from === from);
      }
      if (!sec) {
        const cand = secs.filter((s) => s.title && s.title === msg.meta.secTitle);
        if (cand.length === 1) sec = cand[0];
      }
      if (!sec) { U.toast("未找到目标小节「" + (msg.meta.secTitle || "") + "」，请重新生成"); drawPanel(); return; }
      const paras = msg.text.split(/\n+/).map((s) => s.trim()).filter(Boolean);
      if (paras.length && paras[0].replace(/^#+\s*/, "") === msg.meta.secTitle) paras.shift(); // 模型复述节标题则去掉
      if (!paras.length) { U.toast("没有可写入的内容"); return; }
      const empty = sec.to - sec.from <= 1; // 只有 h2 标题行
      if (empty) {
        const head = bs[sec.from] && bs[sec.from].kind === "h2" ? [bs[sec.from]] : [];
        bs.splice(sec.from, sec.to - sec.from, ...head, ...paras.map((t) => ({ kind: "p", text: t })));
      } else {
        bs.splice(sec.to, 0, ...paras.map((t) => ({ kind: "p", text: t })));
      }
      Store.setBlocks(c, bs);
      Store.touch(c);
      Copilot.invalidateContext(c.id);
      await adoptEvidence(msg);
      U.toast(empty ? "已写入本节" : "已追加到本节");
      drawAll();
    }

    // 逐节生成入口（大纲面板 ✦）：caseContext 带目标节标题与现有内容；模板里能找到该节时带上写作定位
    function sectionDraft(bi) {
      const bs = blocksOf();
      const b = bs[bi];
      if (!b || b.kind !== "h2") return;
      const secs = logicalSections();
      const sec = secs.find((s) => s.from === bi) || { title: b.text, from: bi, to: bi + 1 };
      const body = bs.slice(sec.from + 1, sec.to).map((x) => x.text).join("\n");
      const tp = ((Store.typeById(c.typeId) || {}).templates || []).find((x) => (x.sections || []).includes(b.text));
      const req = tp
        ? `本节为「${Store.typeName(c.typeId)}·${tp.name}」第 ${tp.sections.indexOf(b.text) + 1} 节，需符合该节在模板中的写作定位`
        : "紧扣本节标题，表达书面、简练";
      const ctx = agentCaseContext();
      ctx.sectionTitle = b.text;
      ctx.sectionText = body.slice(0, 4000);
      tab = "copilot";
      cpView = "chat";
      sendChat(`请为「${b.text}」生成本节内容。要求：${req}。结合案例主题「${c.title}」。`,
        "section-draft", false, { baseText: body, caseContext: ctx, secFrom: bi, secTitle: b.text });
    }

    // 采集载荷：按白名单定可信度并映射信源等级（high→A / low→C），gradeReason 记录定级依据
    function collectPayload(url, res) {
      const link = (res && (res.finalUrl || res.url)) || url;
      const credibility = Copilot.credibilityFor(link);
      return {
        title: (res && res.title) || url, kind: "链接",
        source: (() => { try { return new URL(link).hostname; } catch (e) { return url; } })(),
        sourceUrl: url, publishedAt: U.plainDate(U.now()),
        level: 0, credibility,
        grade: credibility === "high" ? "A" : "C",
        gradeReason: credibility === "high" ? "来源在权威白名单内，自动定 A 级" : "非白名单来源，自动定 C 级，引用前需核验",
        scope: "全体教师" + (credibility === "low" ? "（非白名单来源，引用前需核验）" : ""),
        summary: "通过 Copilot 采集的网页内容。",
        excerpt: ((res && res.text) || "").slice(0, 2000),
      };
    }

    async function addFetchedMaterial(url, res, force) {
      return Store.addMaterial(collectPayload(url, res), force);
    }

    // 采集查重双闸（ADR 0003，服务端执行）：URL 查重直接拦；相似素材提示可复用，force 仍要采集
    async function handleFetch(url, force) {
      const res = await Copilot.fetchUrl(url);
      if (!res.ok) return { ok: false, error: res.error || "采集失败" };
      const r = await addFetchedMaterial(url, res, force);
      if (r.ok) {
        return {
          ok: true, model: "url-fetch", elapsed_ms: 0,
          content: `已采集网页并保存内容副本：\n标题：${r.material.title}\n来源：${r.material.source}\n信源等级：${r.material.grade} 级\n副本：${(res.text || "").length} 字\n\n已进入「候选」池，管理员确认入库后进入检索语料。`,
        };
      }
      if (r.code === "dup") {
        return { ok: true, model: "url-fetch", elapsed_ms: 0, content: r.error };
      }
      if (r.code === "similar") {
        pendingFetch = { url, res };
        return {
          ok: true, model: "url-fetch", elapsed_ms: 0, actions: [{ label: "仍要采集", type: "fetch-force" }],
          content: `库中已有相似素材，建议优先复用：\n${r.similar.map((m, i) => `${i + 1}. ${m.title}（${m.source}）`).join("\n")}\n\n如确属不同内容，可点击「仍要采集」。`,
        };
      }
      return { ok: false, error: r.error || "采集失败" };
    }

    // ---------------- 批注 ----------------
    const KINDS = { ai: "AI 建议", admin: "审核员", risk: "风险提示", selfcheck: "系统自检", author: "我的批注" };
    const ASTATUS = { pending: "待处理", accepted: "已采纳", rejected: "已拒绝", resolved: "已解决", outdated: "已失效" };
    const kindTagCls = (k) => k === "risk" ? "red" : k === "admin" ? "amber" : k === "selfcheck" ? "amber" : k === "author" ? "green" : "blue";

    const annoHTML = () => {
      const chips = `
      <div class="filter-chips">
        ${Object.keys(ASTATUS).map((s) => `<button data-afs="${s}" class="${annoFilter.status.has(s) ? "on" : ""}">${ASTATUS[s]}</button>`).join("")}
        <span style="width:8px"></span>
        ${Object.keys(KINDS).map((k) => `<button data-afk="${k}" class="${annoFilter.kind.has(k) ? "on" : ""}">${KINDS[k]}</button>`).join("")}
      </div>
      <div class="row spread" style="margin-bottom:8px">
        <span class="small muted">${c.annotations.filter((a) => a.status === "pending").length} 条待处理 · 在正文选中文字可添加批注</span>
        ${editable() ? `<button class="btn sm plain" id="anno-batch">批量采纳低风险</button>` : ""}
      </div>`;
      const list = c.annotations.filter((a) =>
        (annoFilter.status.size === 0 || annoFilter.status.has(a.status)) &&
        (annoFilter.kind.size === 0 || annoFilter.kind.has(a.kind)));
      const cards = list.map((a) => {
        const replies = (a.replies || []).map((r) => `
          <div class="anno-reply"><b>${U.esc(r.byName)}</b>：${U.esc(r.text)}
            <span class="small muted"> · ${U.esc(r.at)}</span></div>`).join("");
        const reopen = reviewer && a.status === "resolved";
        return `
      <div class="anno-card ${a.kind} ${a.status === "outdated" ? "outdated" : ""}">
        <div class="row spread">
          <span class="tag ${kindTagCls(a.kind)}">${KINDS[a.kind] || a.kind}</span>
          <span class="tag">${ASTATUS[a.status] || a.status}</span>
        </div>
        ${a.quote ? `<div class="anno-quote" data-locate="${a.id}" title="定位到正文">${U.esc(a.quote)}</div>` : ""}
        <div>${U.esc(a.text)}</div>
        <div class="small muted" style="margin-top:4px">${U.esc(a.author || "")} · ${U.esc(a.createdAt || "")} · ${U.esc(blockLabel(a.section || 0))}</div>
        ${replies ? `<div class="anno-replies">${replies}</div>` : ""}
        <div class="row" style="margin-top:8px">
          ${a.status === "pending" && editable() && (a.kind === "ai" || a.kind === "risk") ? `
            <button class="btn sm secondary" data-anno-ok="${a.id}">采纳</button>
            <button class="btn sm plain" data-anno-no="${a.id}">拒绝</button>` : ""}
          ${a.status === "pending" && editable() ? `<button class="btn sm plain" data-anno-done="${a.id}">标记解决</button>` : ""}
          ${a.status === "pending" && reviewer ? `<button class="btn sm plain" data-anno-done="${a.id}">确认解决</button>` : ""}
          ${a.status === "outdated" && editable() ? `<button class="btn sm secondary" data-anno-remount="${a.id}">请 Copilot 重新判断</button>` : ""}
        </div>
        <div class="row" style="margin-top:6px">
          <input class="text sm" data-reply-for="${a.id}" placeholder="${reviewer ? "追问或回应…" : "回应（可说明处理情况）…"}">
          <button class="btn sm plain" data-anno-reply="${a.id}" data-reopen="${reopen ? 1 : 0}">${reopen ? "追问并重开" : "回复"}</button>
        </div>
      </div>`;
      }).join("");
      return `<div class="panel-scroll">${chips}${cards || H.empty("当前筛选下没有批注")}</div>`;
    };

    async function remountAnno(a) {
      let best = -1, bestBlock = 0;
      blocksOf().forEach((b, i) => {
        for (let len = Math.min(20, a.quote.length); len >= 6; len -= 2) {
          if (b.text.includes(a.quote.slice(0, len))) { best = len; bestBlock = i; break; }
        }
      });
      if (best >= 6) {
        if (await Store.setAnnoStatus(c, a.id, "pending", { section: bestBlock })) {
          U.toast(`检测到表述调整，已将批注重新挂载至「${blockLabel(bestBlock)}」`);
        }
      } else {
        U.toast("无法在当前正文中重新定位，保持失效状态", 3200);
      }
      drawAll();
    }

    // ---------------- 选区浮动条（+ 批注 / ✦ 发送 Copilot，作者与审核员都可用） ----------------
    function hideSelBtn() { if (selBtn) { selBtn.remove(); selBtn = null; } }

    function onDocMouseUp() {
      hideSelBtn();
      const ed = U.$("#doc-editor");
      if (!ed) return;
      const sel = window.getSelection();
      if (!sel || sel.isCollapsed || !sel.anchorNode || !ed.contains(sel.anchorNode)) return;
      const text = sel.toString().trim();
      if (text.length < 4) return;
      let blockEl = sel.anchorNode.nodeType === 1 ? sel.anchorNode : sel.anchorNode.parentElement;
      while (blockEl && blockEl.parentElement !== ed) blockEl = blockEl.parentElement;
      const idx = Math.max(0, Array.from(ed.children).indexOf(blockEl));
      citeAnchor = { text: text.slice(0, 200), blockIdx: idx }; // 供挂引用时作句级锚点
      const rect = sel.getRangeAt(0).getBoundingClientRect();
      selBtn = document.createElement("div");
      selBtn.className = "sel-float";
      selBtn.style.top = (window.scrollY + rect.top - 46) + "px";
      selBtn.style.left = (window.scrollX + rect.left) + "px";
      const annoBtn = document.createElement("button");
      annoBtn.className = "btn sm";
      annoBtn.textContent = "+ 批注";
      annoBtn.addEventListener("mousedown", (e) => {
        e.preventDefault();
        addAnnotationFromSelection(text, idx);
      });
      selBtn.appendChild(annoBtn);
      if (editable()) {
        const cpBtn = document.createElement("button");
        cpBtn.className = "btn sm plain";
        cpBtn.textContent = "✦ 发送到 Copilot 修改";
        cpBtn.title = "选中内容发给 Copilot，附修改指令后生成改写提案";
        cpBtn.addEventListener("mousedown", (e) => {
          e.preventDefault();
          sendSelectionToCopilot(text);
        });
        selBtn.appendChild(cpBtn);
      }
      document.body.appendChild(selBtn);
    }

    // 选区 → Copilot 改写：chip 记录选区原文（超 2000 字截断），切到对话页签等用户补指令
    function sendSelectionToCopilot(text) {
      hideSelBtn();
      if (text.length > 2000) {
        U.toast("选中内容超过 2000 字，已截断", 3000);
        text = text.slice(0, 2000);
      }
      selQuote = text;
      const sel = window.getSelection();
      if (sel) sel.removeAllRanges();
      tab = "copilot";
      cpView = "chat";
      drawPanel();
      const ta = U.$("#chat-text");
      if (ta) ta.focus();
    }

    function addAnnotationFromSelection(quote, blockIdx) {
      const close = U.modal(`
      <div class="modal-head"><b>添加批注</b><button class="modal-close" data-close>×</button></div>
      <div class="modal-body">
        <div class="anno-quote" style="margin-bottom:10px">${U.esc(quote.slice(0, 120))}</div>
        <textarea class="text" id="sa-text" style="height:120px" placeholder="批注内容"></textarea>
      </div>
      <div class="modal-foot">
        <button class="btn plain" data-close>取消</button>
        <button class="btn" id="sa-go">保存批注</button>
      </div>`, { sticky: true });
      U.$("#sa-text").focus();
      U.$("#sa-go").addEventListener("click", async () => {
        const text = U.$("#sa-text").value.trim();
        if (!text) { U.toast("请填写批注内容"); return; }
        const saved = await Store.addAnnotation(c, {
          kind: reviewer ? "admin" : "author",
          status: "pending", section: blockIdx, quote: quote.slice(0, 60),
          text, author: me.name, lowRisk: false,
        });
        if (!saved) return;
        close();
        window.getSelection().removeAllRanges();
        tab = "anno";
        U.toast("批注已添加");
        drawAll();
      });
    }

    // ---------------- 资料 ----------------
    const resHTML = () => {
      const cites = (c.citations || []).map((r, i) => {
        const t = H.citeName(r.target);
        if (t.visible === false) return "";
        return `<div class="res-item">
          <div class="row spread"><h5>〔${i + 1}〕${t.kind === "knowledge"
              ? `<a href="#/knowledge/${t.id}">${U.esc(t.name)}</a>`
              : `<a href="#/material/${t.id}">${U.esc(t.name)}</a>`}
            ${Store.citeFailed(r) ? `<span class="tag red sm">来源失效</span>` : ""}</h5>
            <span class="row" style="gap:6px">
              <button class="btn sm plain" data-evd="${i + 1}" title="查看证据片段">证据</button>
              <button class="btn sm plain" data-cite-locate="${i + 1}" title="定位到正文引用处">定位</button>
              ${editable() ? `<button class="btn sm plain" data-uncite="${U.esc(r.target)}">移除</button>` : ""}
            </span></div>
          <div class="small muted">${U.esc(t.src || "")}${r.note ? " · " + U.esc(r.note) : ""}</div>
        </div>`;
      }).join("");
      return `<div class="panel-scroll">
        <div class="section-title small row spread"><span>本案例引用（${(c.citations || []).length}）</span>
          ${(c.citations || []).length ? `<span class="view-toggle sm">
            <button data-res-view="list" class="${resView === "list" ? "on" : ""}">列表</button>
            <button data-res-view="graph" class="${resView === "graph" ? "on" : ""}">图谱</button>
          </span>` : ""}
        </div>
        <div id="cite-body">${cites || H.empty("还没有引用")}</div>
        ${editable() ? `
        <hr class="hr">
        <div class="section-title small"><span>搜索知识库与素材库</span></div>
        <div class="row" style="margin-bottom:6px">
          <input class="text" id="rs-q" placeholder="输入关键词，检索教材知识、学习资料与素材，回车搜索">
          <button class="btn sm" id="rs-go">搜索</button>
        </div>
        <div id="rs-results" style="margin-bottom:12px"></div>
        <hr class="hr">
        <div class="section-title small"><span>采集网页为素材</span></div>
        <div class="row" style="margin-bottom:12px">
          <input class="text" id="fetch-url" placeholder="粘贴 http/https 链接">
          <button class="btn sm" id="fetch-btn">采集</button>
        </div>
        ${Store.flags.webSearch ? `
        <div class="section-title small"><span>联网检索公开资源</span></div>
        <div class="row" style="margin-bottom:6px">
          <input class="text" id="ws-q" placeholder="检索权威来源的公开资料">
          <button class="btn sm" id="ws-go">检索</button>
        </div>
        <div id="ws-results" style="margin-bottom:12px"></div>` : ""}` : ""}
        <div class="section-title small"><span>推荐素材（按本案例上下文）</span></div>
        <div id="rel-m"><div class="small muted">加载中…</div></div>
        <div class="section-title small" style="margin-top:10px"><span>相关知识</span></div>
        <div id="rel-kn"><div class="small muted">加载中…</div></div>
        <div class="section-title small" style="margin-top:10px"><span>最近引用</span></div>
        <div id="rel-recent"><div class="small muted">加载中…</div></div>
      </div>`;
    };

    // 相关/推荐资料：知识走服务端检索，素材走服务端 recommendFor 上下文推荐（共享 kn 节/标签/共引），
    // 最近引用从本人案例引用清单派生（个人层）；均异步填充（渲染路径保持同步）
    async function fillRelated() {
      const knBox = U.$("#rel-kn"), mBox = U.$("#rel-m"), rcBox = U.$("#rel-recent");
      if (!knBox || !mBox || !rcBox) return;
      const citeBtn = (id) => Store.isCited(c, id) ? `<span class="tag green">已引用</span>`
        : (editable() ? `<div style="margin-top:6px"><button class="btn sm plain" data-cite-m="${id}">引用</button></div>` : "");
      const matCard = (m) => `
        <div class="res-item">
          <div class="row spread"><h5><a href="#/material/${m.id}">${U.esc(m.title)}</a></h5>${H.gradeTag(m.grade)}</div>
          <div class="small muted">${U.esc(m.source)} · 被引 ${m.citedCount || 0} · ${U.esc((m.excerpt || m.summary || "").slice(0, 60))}</div>
          ${citeBtn(m.id)}
        </div>`;
      const [rel, recM, recent] = await Promise.all([
        Store.relatedForCase(c),
        Store.recommendedMaterials(c.id),
        Store.recentCitedMaterials(),
      ]);
      if (!U.$("#rel-kn")) return; // 面板已切换
      knBox.innerHTML = rel.knowledge.map((r) => `
        <div class="res-item">
          <h5>${U.esc(r.item.chapter)} · ${U.esc(r.item.title)}</h5>
          <div class="small muted">${U.esc((r.item.text || "").slice(0, 70))}…</div>
          ${editable() ? `<div style="margin-top:6px"><button class="btn sm plain" data-cite-kn="${r.item.id}">引用</button></div>` : ""}
        </div>`).join("") || H.empty("暂无匹配");
      mBox.innerHTML = recM.map(matCard).join("") || H.empty("暂无推荐（引用更多素材后推荐会更准）");
      rcBox.innerHTML = recent.map(matCard).join("") || `<div class="small muted">你还没有在案例中引用过素材</div>`;
    }

    function cite(target, silent) {
      const already = Store.isCited(c, target);
      // 用户选中了正文句子时挂引用：quote=选中文本（句内锚点/文本指纹），blockId 作次级锚
      const anchor = (!already && citeAnchor && citeAnchor.text) ? citeAnchor : null;
      citeAnchor = null;
      const bs = blocksOf();
      const opts = {};
      if (anchor && bs[anchor.blockIdx] && bs[anchor.blockIdx].text.includes(anchor.text.slice(0, 20))) {
        opts.quote = anchor.text.slice(0, 120);
        const b = bs[anchor.blockIdx];
        if (!b.id) b.id = U.uid("b");
        opts.blockId = b.id;
      }
      Store.cite(c, target, opts);
      const n = (c.citations || []).findIndex((r) => r.target === target) + 1;
      const ed = U.$("#doc-editor");
      let domDirty = false;
      if (ed && editable() && !already) {
        if (opts.quote) {
          // 句级锚点：标记插到被引用句后（数据层修改，drawAll 重建 DOM）
          const b = bs[anchor.blockIdx];
          const p = b.text.indexOf(anchor.text.slice(0, 20));
          const full = b.text.indexOf(anchor.text, p);
          const end = full >= 0 ? full + anchor.text.length : p + anchor.text.slice(0, 20).length;
          b.text = b.text.slice(0, end) + `〔${n}〕` + b.text.slice(end);
          Store.setBlocks(c, bs);
          domDirty = true;
        } else {
          ed.focus();
          try { document.execCommand("insertText", false, `〔${n}〕`); } catch (e) { /* ignore */ }
          serializeDoc();
        }
      }
      renumberCitations();
      Store.touch(c);
      if (!silent) U.toast(already ? "该资源已在引用中" : `已添加引用〔${n}〕`);
      if (!silent || domDirty) drawAll();
    }

    // 库内搜索：筛选资料是写作前最耗人工的环节，这里直接检索全库知识/素材并可一键引用（ADR 0005）
    async function doResSearch() {
      const inp = U.$("#rs-q");
      const box = U.$("#rs-results");
      if (!inp || !box) return;
      const q = (inp.value || "").trim();
      if (!q) return;
      box.innerHTML = `<div class="small muted">检索中…</div>`;
      const r = await Store.search(q);
      const kn = (r.knowledge || []).slice(0, 5);
      const ms = (r.materials || []).slice(0, 6);
      if (!kn.length && !ms.length) {
        box.innerHTML = `<div class="small muted">没有命中，换个关键词试试</div>`;
        return;
      }
      box.innerHTML =
        kn.map((x) => `<div class="res-item">
          <div class="row spread"><h5><a href="#/knowledge/${x.item.id}">${U.esc(x.item.chapter)} · ${U.esc(x.item.title)}</a></h5><span class="tag">知识</span></div>
          <div class="small muted">${U.esc((x.item.text || "").slice(0, 70))}…</div>
          <div class="small muted">${U.esc((x.reasons || []).slice(0, 3).join(" · "))}</div>
          ${Store.isCited(c, x.item.id) ? `<span class="tag green">已引用</span>` : `<div style="margin-top:6px"><button class="btn sm plain" data-cite-kn="${x.item.id}">引用</button></div>`}
        </div>`).join("") +
        ms.map((x) => `<div class="res-item">
          <div class="row spread"><h5><a href="#/material/${x.item.id}">${U.esc(x.item.title)}</a></h5>${H.gradeTag(x.item.grade)}</div>
          <div class="small muted">${U.esc(x.item.source || "")} · 被引 ${x.item.citedCount || 0} · ${U.esc((x.item.excerpt || x.item.summary || "").slice(0, 60))}</div>
          <div class="small muted">${U.esc((x.reasons || []).slice(0, 3).join(" · "))}</div>
          ${Store.isCited(c, x.item.id) ? `<span class="tag green">已引用</span>` : `<div style="margin-top:6px"><button class="btn sm plain" data-cite-m="${x.item.id}">引用</button></div>`}
        </div>`).join("");
    }

    // ---------------- 审核动作区（仅审核模式） ----------------
    const pendingReviewAnnos = () =>
      c.annotations.filter((a) => a.status === "pending" && ["admin", "ai", "risk"].includes(a.kind)).length;

    const reviewBoxHTML = () => {
      if (c.status === "pending") {
        return `<div class="card card-pad" style="margin-bottom:12px">
          <div class="section-title small"><span>审核动作</span></div>
          <p class="small muted" style="margin-bottom:10px">开始审核后内容冻结为待审快照，作者不可再撤回。</p>
          <button class="btn" id="rv-start" style="width:100%">开始审核（冻结待审版本）</button>
        </div>`;
      }
      if (c.status !== "reviewing") {
        return `<div class="card card-pad" style="margin-bottom:12px">
          <div class="section-title small"><span>审核动作</span></div>
          <p class="small muted">该案例当前不在审核流程中。</p>
        </div>`;
      }
      const n = pendingReviewAnnos();
      return `<div class="card card-pad" style="margin-bottom:12px">
        <div class="section-title small"><span>审核动作</span></div>
        ${n
          ? `<div class="small muted" style="margin-bottom:8px">已挂批注 ${n} 条（退回/要求补充至少需一条）</div>`
          : `<div class="small" style="color:var(--amber);margin-bottom:8px">退回或要求补充前，请先在正文选中文字添加至少一条批注。</div>`}
        <label class="field"><span>总评（可选）</span>
          <textarea class="text" id="rv-opinion" style="height:72px" placeholder="整体评价，可不填">${U.esc(rvOpinion)}</textarea></label>
        <label class="field"><span>退回类型（退回/要求补充必选）</span>
          <select class="text" id="rv-reason-type">
            <option value="">请选择退回类型…</option>
            ${Object.entries(Store.reasonTypeNames).map(([k, n]) =>
              `<option value="${k}" ${rvReasonType === k ? "selected" : ""}>${n}</option>`).join("")}
          </select></label>
        <label class="field"><span>线下意见来源（可选）</span>
          <select class="text" id="rv-from">
            ${["无", "教研室讨论", "专家评审会", "上级部门意见"].map((x) =>
              `<option ${rvFrom === x ? "selected" : ""}>${x}</option>`).join("")}
          </select></label>
        <div style="display:flex;flex-direction:column;gap:8px">
          <button class="btn" id="rv-approve">通过并发布</button>
          <button class="btn secondary" id="rv-return">退回修改</button>
          <button class="btn secondary" id="rv-supplement">要求补充</button>
          <button class="btn plain" id="rv-hide">暂时隐藏</button>
        </div>
      </div>`;
    };

    const reviewHistHTML = () => {
      const recs = Store.db.reviews.filter((r) => r.caseId === c.id && r.action in REVIEW_ACT_NAMES);
      if (!recs.length) return "";
      return `<div class="card card-pad">
        <div class="section-title small"><span>历史审核记录</span></div>
        ${recs.map((r) => `<div style="padding:6px 0;border-bottom:1px solid var(--line)">
          <div class="row spread"><b class="small">${U.esc(REVIEW_ACT_NAMES[r.action])}${r.reasonType ? `<span class="tag amber" style="margin-left:6px">${U.esc(Store.reasonTypeNames[r.reasonType] || r.reasonType)}</span>` : ""}</b>
          <span class="small muted">第 ${r.round || 1} 轮 · ${U.esc(r.at)}</span></div>
          ${r.opinion ? `<div class="small muted">${U.esc(r.opinion)}</div>` : ""}
        </div>`).join("")}
      </div>`;
    };
    // 服务端留痕动作 → 显示名（reject 即退回修改）
    const REVIEW_ACT_NAMES = { approve: "通过并发布", reject: "退回修改", return: "退回修改", supplement: "要求补充", hide: "暂时隐藏" };

    async function doReview(action) {
      if ((action === "return" || action === "supplement") && pendingReviewAnnos() === 0) {
        U.toast("批注即意见：请先在正文选中文字，添加至少一条批注", 3200);
        tab = "anno";
        drawPanel();
        return;
      }
      const opinion = (U.$("#rv-opinion") ? U.$("#rv-opinion").value : rvOpinion).trim();
      const from = U.$("#rv-from") ? U.$("#rv-from").value : "";
      const reasonType = U.$("#rv-reason-type") ? U.$("#rv-reason-type").value : rvReasonType;
      if ((action === "return" || action === "supplement") && !reasonType) {
        U.toast("退回/要求补充必须选择退回类型", 3200);
        return;
      }
      const verb = REVIEW_ACT_NAMES[action] || action;
      if (!(await U.confirmModal(`确认「${verb}」该案例？`, { danger: action === "hide" }))) return;
      if (await Store.reviewCase(c, action, opinion, from === "无" ? "" : from, reasonType)) {
        U.toast("已完成：" + verb);
        location.hash = "#/admin/audit";
      }
    }

    // ---------------- 版本对比 ----------------
    // 快照转纯文本行：列表/引用块加前缀（与导出 markdown 同规则）
    function snapText(snap) {
      return Store.blocksOf(snap).map((b) => {
        if (b.kind === "h2") return "■ " + b.text;
        if (b.kind === "ul") return String(b.text).split("\n").map((s) => "- " + s).join("\n");
        if (b.kind === "ol") return String(b.text).split("\n").map((s, i) => (i + 1) + ". " + s).join("\n");
        if (b.kind === "quote") return String(b.text).split("\n").map((s) => "> " + s).join("\n");
        return b.text;
      }).join("\n");
    }
    // 行级 diff 渲染：审核员整页对比与作者版本弹窗对比共用
    const diffViewHTML = (oldSnap, newSnap) => {
      const lines = U.diffLines(snapText(oldSnap), snapText(newSnap));
      return `<div class="diff-view">${lines.map((l) =>
        l.t === " " ? `<p class="diff-same">${U.esc(l.s)}</p>`
        : l.t === "+" ? `<p class="diff-add">${U.esc(l.s)}</p>`
        : `<p class="diff-del">${U.esc(l.s)}</p>`).join("")}</div>`;
    };
    const diffHTML = () => {
      const submits = (c.versions || []).filter((v) => v.label.indexOf("提交版") === 0 && v.snapshot);
      if (submits.length < 2) return "";
      const prev = submits[submits.length - 2], cur = submits[submits.length - 1];
      return `<div class="doc-page">
        <div class="doc-head"><h1 class="doc-title">版本对比：${U.esc(prev.label)} → ${U.esc(cur.label)}</h1>
        <div class="doc-meta small muted">绿色为新增，红色为删除。当前送审的是 ${U.esc(cur.label)}。</div></div>
        ${diffViewHTML(prev.snapshot, cur.snapshot)}
      </div>`;
    };

    // ---------------- 导出 ----------------
    function restrictedCites() {
      return (c.citations || []).map((r, i) => ({ r, i, t: H.citeName(r.target) }))
        .filter((x) => x.t.kind === "material" && (x.t.level || 0) > 0);
    }

    function exportModal() {
      const restricted = restrictedCites();
      const draftMark = c.status !== "published";
      const close = U.modal(`
      <div class="modal-head"><b>导出教学材料</b><button class="modal-close" data-close>×</button></div>
      <div class="modal-body">
        <label class="field"><span>版本</span>
          <div class="row">
            <label class="row" style="gap:6px"><input type="radio" name="ex-mode" value="internal" checked style="width:auto"> 校内完整版</label>
            <label class="row" style="gap:6px"><input type="radio" name="ex-mode" value="external" style="width:auto"> 对外申报/分享版</label>
          </div></label>
        <div id="ex-warn"></div>
        <label class="field"><span>包含内容</span>
          <div class="row wrap">
            ${[["body", "案例正文", true], ["design", "教学设计", !!(c.kit && c.kit.design), 1], ["discussion", "讨论题", !!(c.kit && (c.kit.discussion || []).length), 1], ["ppt", "PPT 提纲", !!(c.kit && (c.kit.ppt || []).length), 1], ["refs", "参考文献", (c.citations || []).length > 0]].map(([k, n, on, isKit]) => {
              const disabled = isKit && !on; // kit 项无内容时禁用，引导去案例详情页生成
              return `<label class="row" style="gap:5px${disabled ? ";opacity:.6" : ""}"><input type="checkbox" data-ex-part="${k}" ${on ? "checked" : ""} ${disabled ? "disabled" : ""} style="width:auto"> ${n}${disabled ? `<span class="small muted">（暂无，可在案例详情页生成）</span>` : ""}</label>`;
            }).join("")}
          </div></label>
        ${draftMark ? `<p class="small" style="color:var(--amber)">当前案例未定稿，导出文件将带有“草稿 / 仅供内部教学参考”标识。</p>` : ""}
      </div>
      <div class="modal-foot">
        <button class="btn plain" data-close>取消</button>
        <button class="btn" id="ex-go">导出 Word</button>
      </div>`);

      const drawWarn = () => {
        const external = U.$('input[name=ex-mode]:checked').value === "external";
        U.$("#ex-warn").innerHTML = external && restricted.length ? `
          <div class="card-pad" style="background:var(--red-soft);border-radius:6px;margin-bottom:12px">
            <b class="small" style="color:var(--red)">以下内容不允许外发，导出时将自动移除：</b>
            ${restricted.map((x) => `<div class="small">〔${x.i + 1}〕${U.esc(x.t.name)}（${x.t.level === 2 ? "受限" : "校内"}）</div>`).join("")}
            <label class="row small" style="gap:6px;margin-top:8px"><input type="checkbox" id="ex-confirm" style="width:auto"> 已确认脱敏处理</label>
          </div>` : "";
      };
      U.$$('input[name=ex-mode]').forEach((r) => r.addEventListener("change", drawWarn));
      drawWarn();

      U.$("#ex-go").addEventListener("click", async () => {
        const external = U.$('input[name=ex-mode]:checked').value === "external";
        if (external && restricted.length && !(U.$("#ex-confirm") && U.$("#ex-confirm").checked)) {
          U.toast("请先确认脱敏处理");
          return;
        }
        await doExport({ external });
        close();
      });
    }

    async function doExport(opts) {
      const external = opts.external;
      const drop = new Set(external ? restrictedCites().map((x) => x.i) : []);
      const parts = [];
      const want = {};
      U.$$("[data-ex-part]").forEach((b) => { want[b.dataset.exPart] = b.checked; });
      if (want.body) {
        parts.push({
          heading: "案例正文",
          // 列表/引用块输出标准 markdown 前缀行，与服务端 export-docx 渲染规则一致
          markdown: Store.blocksOf(c).map((b) => {
            if (b.kind === "h2") return "## " + b.text;
            if (b.kind === "ul") return String(b.text).split("\n").map((s) => "- " + s).join("\n");
            if (b.kind === "ol") return String(b.text).split("\n").map((s, i) => (i + 1) + ". " + s).join("\n");
            if (b.kind === "quote") return String(b.text).split("\n").map((s) => "> " + s).join("\n");
            return b.text;
          }).join("\n\n"),
        });
      }
      if (want.design && c.kit && c.kit.design) parts.push({ heading: "教学设计", markdown: c.kit.design });
      if (want.discussion && c.kit && (c.kit.discussion || []).length)
        parts.push({ heading: "课堂讨论题", markdown: c.kit.discussion.map((d, i) => `${i + 1}. ${d}`).join("\n") });
      if (want.ppt && c.kit && (c.kit.ppt || []).length)
        parts.push({ heading: "PPT 提纲", markdown: c.kit.ppt.map((d, i) => `${i + 1}. ${d}`).join("\n") });
      let refs = [];
      if (want.refs) {
        refs = (c.citations || []).filter((r, i) => !drop.has(i)).map((r) => {
          const t = H.citeName(r.target);
          return { title: t.name, source: t.src || "" };
        });
      }
      const statusNote = c.status === "published" ? "已发布公开版" : "草稿（仅供内部教学参考）";
      const footerNote = `上海大学思政教学案例智能平台 · 生成时间：${U.now()} · 状态：${statusNote} · ${external ? "对外申报版（已脱敏）" : "校内完整版"}`;
      const cm = c.meta || {}; // AI 生成标识：服务端写入页脚追踪元数据
      const resp = await fetch("/api/export-docx", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: c.title,
          meta: {
            author: c.author || Store.userById(c.ownerId).name,
            audience: Store.audienceName(c.audience),
            caseType: Store.typeName(c.typeId), course: c.course || "-",
            mode: external ? "对外申报版" : "校内完整版",
            statusNote, footerNote,
            origin: cm.origin || "human",
            modelVersions: cm.modelVersions || [],
            reviewedBy: cm.reviewedBy || "",
          },
          parts, refs,
        }),
      });
      if (!resp.ok) { U.toast("导出失败"); return; }
      const blob = await resp.blob();
      U.download(c.title + (external ? "（对外版）" : "") + ".docx", blob);
      U.toast("已导出");
    }

    // ---------------- 提交前自检（未过项即批注，ADR 0001；批注由服务端同步） ----------------
    function checklistModal() {
      const checks = Store.selfChecks(c);
      const passed = checks.filter((x) => x.ok).length;
      const level = passed === checks.length ? ["高", "green"] : passed >= checks.length - 2 ? ["中", "amber"] : ["低", "red"];
      const close = U.modal(`
      <div class="modal-head"><b>提交前自检</b><button class="modal-close" data-close>×</button></div>
      <div class="modal-body">
        <div class="row" style="margin-bottom:12px">
          <span>完整度评估：</span><span class="tag ${level[1]}" style="font-size:14px">${level[0]}</span>
          <span class="small muted">${passed} / ${checks.length} 项通过</span>
        </div>
        ${checks.map((x) => `<div class="row" style="padding:5px 0">
          <span class="tag ${x.ok ? "green" : "red"}" style="min-width:52px;text-align:center">${x.ok ? "通过" : "未过"}</span>
          <span style="${x.ok ? "" : "color:var(--red)"}">${U.esc(x.name)}</span>
          ${!x.ok ? `<a href="javascript:void 0" class="small" data-goto-anno style="margin-left:auto">看批注</a>` : ""}
        </div>`).join("")}
        <p class="small muted" style="margin-top:10px">未过项已同步为「系统自检」批注，处理后自动标记解决。提交后生成待审版本并冻结，管理员开始审核前可撤回。</p>
      </div>
      <div class="modal-foot">
        <button class="btn plain" data-close>继续完善</button>
        <button class="btn" id="submit-go">仍要提交</button>
      </div>`, { sticky: true });
      U.$$("[data-goto-anno]").forEach((b) => b.addEventListener("click", () => {
        close(); tab = "anno"; annoFilter.kind = new Set(["selfcheck"]); drawPanel();
      }));
      U.$("#submit-go").addEventListener("click", async () => {
        close();
        if (await Store.submitCase(c)) {
          U.toast("已提交审核，内容已冻结");
          drawAll();
        }
      });
    }

    // ---------------- 历史版本 ----------------
    function versionsModal() {
      const vs = (c.versions || []).slice().reverse();
      const snapVs = (c.versions || []).filter((v) => v.snapshot); // 时间正序，供对比选择
      const close = U.modal(`
      <div class="modal-head"><b>历史版本</b><button class="modal-close" data-close>×</button></div>
      <div class="modal-body">
        ${!reviewer && mine ? `
        <div class="row" style="margin-bottom:12px">
          <input class="text" id="v-new-label" placeholder="版本备注（可空）">
          <button class="btn sm" id="v-save">手动存版本</button>
        </div>` : ""}
        ${vs.map((v) => `
        <div class="res-item">
          <div class="row spread"><h5>${U.esc(v.label)}</h5>
          <span class="row" style="gap:6px">
            ${v.snapshot ? `<button class="btn sm plain" data-vview="${v.id}">查看</button>` : ""}
            ${v.snapshot && editable() ? `<button class="btn sm plain" data-vroll="${v.id}">回滚到此版本</button>` : ""}
          </span></div>
          <div class="small muted">${U.esc(v.at)} · ${U.esc(v.note || "")}</div>
        </div>`).join("") || H.empty("暂无版本记录")}
        ${snapVs.length >= 2 ? `
        <hr class="hr">
        <div class="section-title small"><span>版本对比</span></div>
        <div class="row" style="margin-bottom:8px">
          <select class="text" id="v-diff-a">${snapVs.map((v, i) => `<option value="${v.id}" ${i === snapVs.length - 2 ? "selected" : ""}>${U.esc(v.label)}</option>`).join("")}</select>
          <span class="small muted">→</span>
          <select class="text" id="v-diff-b">${snapVs.map((v, i) => `<option value="${v.id}" ${i === snapVs.length - 1 ? "selected" : ""}>${U.esc(v.label)}</option>`).join("")}</select>
          <button class="btn sm plain" id="v-diff-go">对比</button>
        </div>
        <div id="v-diff-box"></div>` : ""}
      </div>
      <div class="modal-foot"><button class="btn plain" data-close>关闭</button></div>`);
      U.$$("[data-vview]").forEach((b) => b.addEventListener("click", () => {
        const v = (c.versions || []).find((x) => x.id === b.dataset.vview);
        if (!v || !v.snapshot) return;
        U.modal(`
        <div class="modal-head"><b>${U.esc(v.label)} · ${U.esc(v.at)}</b><button class="modal-close" data-close>×</button></div>
        <div class="modal-body article">
          <h3 style="border:none;padding:0">${U.esc(v.snapshot.title)}</h3>
          ${Store.blocksOf(v.snapshot).map((x) => blockHTML(x, U.esc)).join("")}
        </div>
        <div class="modal-foot"><button class="btn plain" data-close>关闭</button></div>`, { sticky: true });
      }));
      // 回滚：confirm 弹窗会替换本弹窗（U.modal 单例），确认成功后重开版本列表
      U.$$("[data-vroll]").forEach((b) => b.addEventListener("click", async () => {
        const v = (c.versions || []).find((x) => x.id === b.dataset.vroll);
        if (!v || !v.snapshot) return;
        if (!(await U.confirmModal(`回滚到「${v.label}」？当前内容会先自动打「回滚前自动快照」留退路。`))) return;
        if (await Store.rollbackVersion(c.id, v.id)) {
          Copilot.invalidateContext(c.id);
          U.toast("已回滚到「" + v.label + "」");
          drawAll();
          versionsModal();
        }
      }));
      const saveBtn = U.$("#v-save");
      if (saveBtn) saveBtn.addEventListener("click", async () => {
        const label = (U.$("#v-new-label") && U.$("#v-new-label").value) || "";
        const v = await Store.saveVersion(c.id, label);
        if (!v) return; // 失败提示由 Store 统一弹出
        U.toast("已保存版本「" + v.label + "」");
        close();
        versionsModal();
      });
      // 作者侧版本对比：任选两个带快照的版本做行级 diff（复用 U.diffLines）
      const diffGo = U.$("#v-diff-go");
      if (diffGo) diffGo.addEventListener("click", () => {
        const a = snapVs.find((x) => x.id === U.$("#v-diff-a").value);
        const b2 = snapVs.find((x) => x.id === U.$("#v-diff-b").value);
        if (!a || !b2 || a.id === b2.id) { U.toast("请选择两个不同的版本"); return; }
        U.$("#v-diff-box").innerHTML =
          `<div class="small muted" style="margin-bottom:6px">${U.esc(a.label)} → ${U.esc(b2.label)}：绿色新增，红色删除</div>` +
          diffViewHTML(a.snapshot, b2.snapshot);
      });
      return close;
    }

    // ---------------- 面板 ----------------
    // 资料页签引用区图谱：两跳力导向图，单击节点直达详情（ADR 0008）
    function renderCiteBody() {
      const body = U.$("#cite-body");
      if (!body || tab !== "res" || resView !== "graph" || !(c.citations || []).length) return;
      body.innerHTML = `<div class="ego-force" style="height:260px"><canvas id="wb-ego-canvas"></canvas><div class="graph-tip" id="wb-ego-tip"></div></div>`;
      Graph.render(U.$("#wb-ego-canvas", body), {
        data: Graph.egoData(c.id), noCache: true,
        tip: U.$("#wb-ego-tip", body),
        onCard: (n) => {
          if (n.ref.kind === "self") return;
          location.hash = n.ref.kind === "case" ? "#/case/" + n.ref.id
            : n.ref.kind === "knowledge" ? "#/knowledge/" + n.ref.id : "#/material/" + n.ref.id;
        },
      });
    }

    function drawPanel() {
      const box = U.$("#wb-panel");
      if (!box) return;
      // Copilot 是工作台主力功能：激活时右栏加宽加高，批注/资料时恢复窄栏
      const grid = U.$(".wb-grid");
      if (grid) grid.classList.toggle("cp-main", tab === "copilot");
      U.$$("#wb-tabs button").forEach((b) => b.classList.toggle("active", b.dataset.tab === tab));
      if (tab === "copilot") box.innerHTML = chatHTML();
      else if (tab === "anno") box.innerHTML = annoHTML();
      else box.innerHTML = resHTML();
      if (tab === "res") fillRelated();
      const scroll = U.$("#chat-scroll");
      if (scroll) scroll.scrollTop = scroll.scrollHeight;
      if (tab !== "res") Graph.stop();
      renderCiteBody();
      const rv = U.$("#rv-box");
      if (rv) {
        const kept = U.$("#rv-opinion") ? U.$("#rv-opinion").value : rvOpinion;
        rv.innerHTML = reviewBoxHTML() + reviewHistHTML();
        const op = U.$("#rv-opinion");
        if (op) op.value = kept;
      }
    }

    function drawAll() {
      renumberCitations();
      U.$("#wb-head-box").innerHTML = headHTML();
      U.$("#wb-secs").innerHTML = showDiff ? diffHTML() : docHTML();
      U.$("#wb-outline-box").innerHTML = outlineHTML();
      drawPanel();
    }

    // ---------------- 组装 ----------------
    const TABS = reviewer
      ? [["anno", "批注"], ["copilot", "Copilot"], ["res", "资料"]]
      : [["copilot", "Copilot"], ["anno", "批注"], ["res", "资料"]];

    return {
      html: `
      <div id="wb-head-box">${headHTML()}</div>
      <div id="wb-outline-box">${outlineHTML()}</div>
      <div class="wb-grid">
        <div id="wb-secs">${docHTML()}</div>
        <div class="wb-side">
          ${reviewer ? `<div id="rv-box">${reviewBoxHTML()}${reviewHistHTML()}</div>` : ""}
          <div class="wb-tabs" id="wb-tabs">
            ${TABS.map(([k, n]) => `<button data-tab="${k}" class="${tab === k ? "active" : ""}">${n}</button>`).join("")}
          </div>
          <div class="wb-panel" id="wb-panel"></div>
        </div>
      </div>
      <div id="evd-box"></div>`,
      mount(el) {
        // 工具栏按钮 mousedown 阻止默认行为：避免点击按钮时编辑器失焦、选区丢失，
        // 否则 execCommand 会作用在错误位置或失效（contenteditable 工具栏惯例）
        el.addEventListener("mousedown", (e) => {
          if (e.target.closest("[data-fmt]")) e.preventDefault();
        });
        el.addEventListener("click", async (e) => {
          const t = e.target.closest("[data-tab],[data-quick],[data-act],[data-retry],[data-afs],[data-afk],[data-anno-ok],[data-anno-no],[data-anno-done],[data-anno-remount],[data-anno-reply],[data-locate],[data-cite-kn],[data-cite-m],[data-uncite],[data-cite-locate],[data-cite-jump],[data-evd],[data-evd-close],[data-outline],[data-goto-intent],[data-fmt],[data-ws-add],[data-tag-del],[data-res-view],[data-cp-view],[data-chat-clear],[data-task-replay],[data-cand],[data-agents-toggle],[data-sec-gen],[data-diff-open],[data-guard-ok],[data-guard-no],[data-sel-clear]");
          if (t) {
            if (t.dataset.tab) { tab = t.dataset.tab; drawPanel(); return; }
            if (t.dataset.resView) { resView = t.dataset.resView; drawPanel(); return; }
            if (t.dataset.cpView) { cpView = t.dataset.cpView; drawPanel(); return; }
            if (t.dataset.chatClear != null) {
              Copilot.clearHistory(convoKey);
              chat.length = 0;
              U.toast("已清空对话历史");
              drawPanel();
              return;
            }
            if (t.dataset.taskReplay) {
              const task = (c.tasks || []).find((x) => x.id === t.dataset.taskReplay);
              if (task) {
                cpView = "chat";
                drawPanel();
                const ta = U.$("#chat-text");
                if (ta) {
                  ta.value = task.prompt || task.label;
                  ta.focus();
                  ta.setSelectionRange(ta.value.length, ta.value.length);
                }
              }
              return;
            }
            if (t.dataset.quick) {
              const cmd = Copilot.quickCommands(c, scene).find((x) => x.intent === t.dataset.quick);
              const ta = U.$("#chat-text");
              if (cmd && ta) {
                ta.value = cmd.prompt || cmd.label;
                lastChipText = ta.value;
                pendingIntent = cmd.intent;
                ta.focus();
                ta.setSelectionRange(ta.value.length, ta.value.length);
              }
              return;
            }
            if (t.dataset.act) {
              const [mi, ai] = t.dataset.act.split(":").map(Number);
              const msg = chat[mi];
              if (msg && msg.actions && msg.actions[ai]) runAction(msg, msg.actions[ai]);
              return;
            }
            // 双候选切换：只换显示内容与采纳作用对象（msg.text 镜像当前候选）；diff 重算，折叠状态重置
            if (t.dataset.cand) {
              const [mi, which] = t.dataset.cand.split(":");
              const msg = chat[Number(mi)];
              if (msg && msg.candidates && msg.candidates[which] && msg.cand !== which) {
                msg.cand = which;
                msg.text = msg.candidates[which].text || "";
                msg.risks = msg.candidates[which].risks || [];
                msg.diffOpen = null;
                msg.meta = msg.meta || {};
                if (msg.candidates[which].model) msg.meta.model = msg.candidates[which].model;
                drawPanel();
              }
              return;
            }
            // 过程链折叠/展开
            if (t.dataset.agentsToggle != null) {
              const msg = chat[Number(t.dataset.agentsToggle)];
              if (msg) { msg.agentsOpen = !msg.agentsOpen; drawPanel(); }
              return;
            }
            // 大纲 ✦：逐节生成入口
            if (t.dataset.secGen != null) {
              if (!sending) sectionDraft(Number(t.dataset.secGen));
              return;
            }
            // diff 折叠行展开
            if (t.dataset.diffOpen != null) {
              const [mi, k] = t.dataset.diffOpen.split(":");
              const msg = chat[Number(mi)];
              if (msg) { msg.diffOpen = msg.diffOpen || {}; msg.diffOpen[k] = true; drawPanel(); }
              return;
            }
            // hash 守卫确认条：确认采纳（带 force 重进 runAction）/ 取消
            if (t.dataset.guardOk != null) {
              const msg = chat[Number(t.dataset.guardOk)];
              const act = msg && (msg.actions || []).find((a) => a.type === msg.confirming);
              if (msg && act) runAction(msg, act, true);
              return;
            }
            if (t.dataset.guardNo != null) {
              const msg = chat[Number(t.dataset.guardNo)];
              if (msg) { msg.confirming = null; drawPanel(); }
              return;
            }
            // 移除选区引用 chip
            if (t.dataset.selClear != null) {
              selQuote = null;
              drawPanel();
              const ta = U.$("#chat-text");
              if (ta) ta.focus();
              return;
            }
            if (t.dataset.retry != null) {
              const msg = chat[Number(t.dataset.retry)];
              const p = msg && (msg.retryPayload || (msg.task && msg.task.retryPayload));
              if (p) sendChat(p.text, p.intent, p.skipDirective, p.opts);
              return;
            }
            if (t.dataset.afs) { toggleSet(annoFilter.status, t.dataset.afs); drawPanel(); return; }
            if (t.dataset.afk) { toggleSet(annoFilter.kind, t.dataset.afk); drawPanel(); return; }
            if (t.dataset.annoOk) { if (await Store.setAnnoStatus(c, t.dataset.annoOk, "accepted")) drawAll(); return; }
            if (t.dataset.annoNo) { if (await Store.setAnnoStatus(c, t.dataset.annoNo, "rejected")) drawAll(); return; }
            if (t.dataset.annoDone) { if (await Store.setAnnoStatus(c, t.dataset.annoDone, "resolved")) drawAll(); return; }
            if (t.dataset.annoReply) {
              const inp = U.$(`[data-reply-for="${t.dataset.annoReply}"]`);
              const v = inp && inp.value.trim();
              if (!v) { U.toast("请先填写回复内容"); return; }
              if (await Store.replyAnnotation(c, t.dataset.annoReply, v, t.dataset.reopen === "1")) {
                U.toast(t.dataset.reopen === "1" ? "已追问，批注重新打开" : "已回复");
                drawAll();
              }
              return;
            }
            if (t.dataset.annoRemount) {
              const a = c.annotations.find((x) => x.id === t.dataset.annoRemount);
              if (a) await remountAnno(a);
              return;
            }
            if (t.dataset.locate) {
              const a = c.annotations.find((x) => x.id === t.dataset.locate);
              if (a) locateBlock(a.section || 0);
              return;
            }
            if (t.dataset.outline) {
              locateBlock(Number(t.dataset.outline));
              return;
            }
            if (t.dataset.citeKn) { cite(t.dataset.citeKn); return; }
            if (t.dataset.citeM) { cite(t.dataset.citeM); return; }
            if (t.dataset.uncite) {
              Store.uncite(c, t.dataset.uncite);
              renumberCitations();
              Store.touch(c);
              drawAll();
              return;
            }
            if (t.dataset.citeLocate) {
              const n = Number(t.dataset.citeLocate);
              const ed = U.$("#doc-editor");
              if (ed) {
                const mark = Array.from(ed.querySelectorAll(".cite-mark")).find((x) => x.dataset.citeJump === String(n));
                const target = mark || Array.from(ed.children).find((x) => x.textContent.includes("〔" + n + "〕"));
                if (target) {
                  target.scrollIntoView({ behavior: "smooth", block: "center" });
                  target.classList.add("flash");
                  setTimeout(() => target.classList.remove("flash"), 1600);
                } else U.toast("正文中未找到该引用的标注位置");
              }
              return;
            }
            if (t.dataset.citeJump) {
              showEvidence(Number(t.dataset.citeJump));
              const item = U.$("#ref-" + t.dataset.citeJump);
              if (item) {
                item.scrollIntoView({ behavior: "smooth", block: "center" });
                item.classList.add("flash");
                setTimeout(() => item.classList.remove("flash"), 1600);
              }
              return;
            }
            if (t.dataset.evd) { showEvidence(Number(t.dataset.evd)); return; }
            if (t.dataset.evdClose != null) { U.$("#evd-box").innerHTML = ""; return; }
            if (t.dataset.gotoIntent) {
              tab = "copilot";
              sendChat("", t.dataset.gotoIntent);
              return;
            }
            if (t.dataset.tagDel != null) {
              Store.setCaseTags(c, Store.tagsOf("case", c).filter((x) => x !== t.dataset.tagDel));
              drawAll();
              return;
            }
            if (t.dataset.fmt) {
              const ed = U.$("#doc-editor");
              if (ed && editable()) {
                ed.focus();
                if (t.dataset.fmt === "bold") document.execCommand("bold");
                else if (t.dataset.fmt === "ul") document.execCommand("insertUnorderedList");
                else if (t.dataset.fmt === "ol") document.execCommand("insertOrderedList");
                else if (t.dataset.fmt === "quote") document.execCommand("formatBlock", false, "<blockquote>");
                else document.execCommand("formatBlock", false, t.dataset.fmt === "h2" ? "<h2>" : "<p>");
                updateFocus();
                serializeDoc();
              }
              return;
            }
            if (t.dataset.wsAdd != null) {
              const r = wsResults[Number(t.dataset.wsAdd)];
              if (r) {
                const payload = collectPayload(r.url, { title: r.title, text: r.content, finalUrl: r.url });
                payload.summary = "通过联网检索采集的公开资料。";
                const r0 = await Store.addMaterial(payload);
                if (r0.ok) {
                  r.collected = true;
                  U.toast("已采集入库（候选池，待管理员确认）");
                  drawPanel();
                  return;
                }
                if (r0.code === "dup") { U.toast(r0.error, 3600); return; }
                if (r0.code === "similar") {
                  const yes = await U.confirmModal(
                    "库中已有相似素材：" + r0.similar.map((m) => "「" + m.title + "」").join("、") + "。仍要采集？");
                  if (yes) {
                    const r2 = await Store.addMaterial(payload, true);
                    if (r2.ok) { r.collected = true; U.toast("已采集入库（候选池）"); drawPanel(); }
                  }
                  return;
                }
                U.toast(r0.error || "采集失败", 3000);
              }
              return;
            }
          }
          if (e.target.id === "chat-send") {
            sendFromInput(U.$("#chat-text"));
            return;
          }
          if (e.target.id === "anno-batch") {
            let n = 0;
            for (const a of c.annotations) {
              if (a.status === "pending" && a.lowRisk) {
                if (await Store.setAnnoStatus(c, a.id, "accepted")) n++;
              }
            }
            U.toast(n ? `已批量采纳 ${n} 条低风险建议` : "没有可批量采纳的低风险建议");
            drawAll();
            return;
          }
          if (e.target.id === "fetch-btn") {
            const inp = U.$("#fetch-url");
            const url = (inp.value || "").trim();
            if (!url) return;
            inp.disabled = true; e.target.disabled = true;
            const res = await handleFetch(url);
            inp.disabled = false; e.target.disabled = false;
            tab = "copilot";
            chat.push({ role: "user", text: "采集链接：" + url });
            if (res.ok) chat.push({ role: "ai", text: res.content, intent: "chat", meta: { model: "url-fetch", ms: 0 }, actions: res.actions || [] });
            else chat.push({ role: "ai", text: "采集失败：" + (res.error || ""), intent: "chat", meta: { model: "url-fetch", ms: 0 }, actions: [] });
            drawAll();
            return;
          }
          if (e.target.id === "ws-go") {
            const inp = U.$("#ws-q");
            const q = (inp.value || "").trim();
            if (!q) return;
            const box = U.$("#ws-results");
            e.target.disabled = true;
            box.innerHTML = `<div class="small muted">检索中…</div>`;
            const res = await Copilot.webSearch(q, 6);
            e.target.disabled = false;
            if (!res.ok) { box.innerHTML = `<div class="small" style="color:var(--red)">${U.esc(res.error || "检索失败")}</div>`; return; }
            wsResults = res.results || [];
            box.innerHTML = wsResults.map((r, i) => {
              const cred = Copilot.credibilityFor(r.url);
              let host = r.url;
              try { host = new URL(r.url).hostname; } catch (err) { /* ignore */ }
              return `<div class="res-item">
                <div class="row spread"><h5>${U.esc(r.title || r.url)}</h5>${H.credTag(cred)}</div>
                <div class="small muted">${U.esc(host)} · ${U.esc((r.content || "").slice(0, 80))}</div>
                <div style="margin-top:6px">
                  ${r.collected ? `<span class="tag green">已入库</span>` : `<button class="btn sm plain" data-ws-add="${i}">采集入库</button>`}
                  <a class="btn sm plain" href="${U.esc(r.url)}" target="_blank" rel="noopener">原页</a>
                </div>
              </div>`;
            }).join("") || `<div class="small muted">无结果</div>`;
            return;
          }
          if (e.target.id === "rs-go") { doResSearch(); return; }
          if (e.target.id === "tag-suggest") {
            const cur = Store.tagsOf("case", c);
            const add = Store.suggestTags(c).filter((x) => !cur.includes(x));
            if (add.length) {
              Store.setCaseTags(c, cur.concat(add));
              U.toast(`已补充标签：${add.join("、")}`);
            } else U.toast("没有可补充的标签");
            drawAll();
            return;
          }
          if (e.target.id === "wb-submit") {
            const checks = Store.selfChecks(c);
            if (checks.every((x) => x.ok)) {
              if (await Store.submitCase(c)) {
                U.toast("已提交审核，内容已冻结");
                drawAll();
              }
            } else {
              checklistModal();
            }
            return;
          }
          if (e.target.id === "wb-check") { checklistModal(); return; }
          if (e.target.id === "wb-withdraw") {
            if (await Store.withdrawCase(c)) {
              U.toast("已撤回，可继续修改");
              drawAll();
            }
            return;
          }
          if (e.target.id === "wb-unhide") { if (await Store.unhideCase(c)) drawAll(); return; }
          if (e.target.id === "wb-versions") { versionsModal(); return; }
          if (e.target.id === "wb-export") { exportModal(); return; }
          if (e.target.id === "wb-diff") { showDiff = !showDiff; drawAll(); return; }
          if (e.target.id === "wb-outline-btn") {
            const o = U.$("#wb-outline");
            if (o) o.hidden = !o.hidden;
            return;
          }
          if (e.target.id === "rv-start") { if (await Store.startReview(c)) drawAll(); return; }
          if (e.target.id === "rv-approve") { doReview("approve"); return; }
          if (e.target.id === "rv-return") { doReview("return"); return; }
          if (e.target.id === "rv-supplement") { doReview("supplement"); return; }
          if (e.target.id === "rv-hide") { doReview("hide"); return; }
          if (e.target.id === "wb-delete") {
            if (await U.confirmModal("删除该案例？此操作不可恢复。", { danger: true })) {
              if (await Store.deleteCase(c.id)) {
                location.hash = reviewer ? "#/admin/audit" : "#/mine";
              }
            }
            return;
          }
        });

        function locateBlock(idx) {
          const ed = U.$("#doc-editor");
          const blk = ed && ed.children[idx];
          if (blk) {
            blk.scrollIntoView({ behavior: "smooth", block: "center" });
            blk.classList.add("flash");
            setTimeout(() => blk.classList.remove("flash"), 1600);
          }
        }

        // 编辑器事件（委托到挂载根节点：drawAll 重渲染后仍然生效）
        if (editable()) {
          try { document.execCommand("defaultParagraphSeparator", false, "p"); } catch (err) { /* ignore */ }
        }
        const inEditor = (e) => e.target && e.target.closest && e.target.closest("#doc-editor");
        el.addEventListener("keyup", (e) => { if (inEditor(e)) updateFocus(); });
        el.addEventListener("click", (e) => { if (inEditor(e)) updateFocus(); });
        el.addEventListener("focusin", (e) => { if (inEditor(e)) updateFocus(); });
        el.addEventListener("input", (e) => { if (inEditor(e)) onEditing(); });
        el.addEventListener("focusout", (e) => { if (inEditor(e)) serializeDoc(); });
        el.addEventListener("paste", (e) => {
          if (!inEditor(e)) return;
          e.preventDefault();
          const text = (e.clipboardData || window.clipboardData).getData("text/plain");
          document.execCommand("insertText", false, text);
        });
        // 选区批注（作者与审核员都可用，委托绑定）
        el.addEventListener("mouseup", (e) => { if (inEditor(e)) onDocMouseUp(); });
        const hideOnDown = (e) => { if (selBtn && !selBtn.contains(e.target)) hideSelBtn(); };
        document.addEventListener("mousedown", hideOnDown);

        el.addEventListener("focusout", (e) => {
          if (e.target.id === "wb-title") {
            c.title = e.target.value.trim() || c.title;
            Store.touch(c);
          }
        });
        el.addEventListener("input", (e) => {
          if (e.target.id === "chat-text" && e.target.value !== lastChipText) pendingIntent = null;
          if (e.target.id === "rv-opinion") rvOpinion = e.target.value;
        });
        el.addEventListener("change", (e) => {
          if (e.target.id === "rv-from") rvFrom = e.target.value;
          if (e.target.id === "rv-reason-type") rvReasonType = e.target.value;
        });
        el.addEventListener("keydown", (e) => {
          if (e.target.id === "case-tag-add" && e.key === "Enter") {
            e.preventDefault();
            const v = e.target.value.trim();
            if (v) {
              Store.setCaseTags(c, Store.tagsOf("case", c).concat([v]));
              drawAll();
            }
            return;
          }
          if (e.target.id === "rs-q" && e.key === "Enter") {
            e.preventDefault();
            doResSearch();
            return;
          }
          if (e.target.id === "chat-text" && e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            sendFromInput(e.target);
          }
        });

        drawPanel();

        this._unmount = () => {
          document.removeEventListener("mousedown", hideOnDown);
          hideSelBtn();
          Graph.stop();
          // 路由切换会 clone #view 重渲染：取消进行中的流式请求与渲染定时器
          if (streamHandle) { streamHandle.abort(); streamHandle = null; }
          clearTimeout(phaseTimer); phaseTimer = null;
          clearTimeout(paintTimer); paintTimer = null;
        };
      },
      unmount() {
        if (this._unmount) this._unmount();
      },
    };

    function toggleSet(set, v) { set.has(v) ? set.delete(v) : set.add(v); }
  };
})();
