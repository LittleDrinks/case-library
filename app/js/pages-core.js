// 页面：公共组件、首页（推荐+动态卡）、我的案例、新建案例、偏好设置
// 依据 docs/adr/0002（首页与信息架构）与 0006（新建流程）
window.Pages = window.Pages || {};
(function () {
  const P = window.Pages;
  const H = {};
  P.H = H;

  const STATUS = {
    draft: ["草稿", ""], checking: ["机审中", "amber"], pending: ["待审", "amber"],
    reviewing: ["审核中", "blue"], published: ["已发布", "green"], hidden: ["已隐藏", "red"],
  };
  H.statusTag = (s) => {
    const t = STATUS[s] || [s, ""];
    return `<span class="tag ${t[1]}">${t[0]}</span>`;
  };
  H.levelTag = (lv) => ["<span class='tag green'>公开</span>", "<span class='tag blue'>校内</span>", "<span class='tag red'>受限</span>"][lv] || "";
  H.credTag = (c) => c === "high" ? "<span class='tag green'>权威来源</span>"
    : c === "low" ? "<span class='tag amber'>待核实</span>" : "<span class='tag'>一般来源</span>";
  // 信源等级（ADR 0005 三档可信度之上的治理定级）：S/A/B/C 四色 + 未定级灰
  H.gradeTag = (g) => {
    const cls = { S: "amber", A: "green", B: "blue", C: "red" }[g];
    return cls ? `<span class="tag ${cls}" title="信源等级 ${g} 级">${g} 级</span>`
      : `<span class="tag" title="信源等级未定">未定级</span>`;
  };
  H.typeTag = (id) => `<span class="tag primary">${U.esc(Store.typeName(id))}</span>`;
  H.audTag = (a) => `<span class="tag">${U.esc(Store.audienceName(a))}</span>`;

  H.citeName = (target) => {
    const kn = Store.knowledgeById(target);
    if (kn) return { kind: "knowledge", id: kn.id, name: kn.chapter + " · " + kn.title, src: Store.db.book.title };
    const m = Store.db.materials.find((x) => x.id === target);
    if (m) return { kind: "material", id: m.id, name: m.title, src: m.source, level: m.level, visible: !!Store.materialById(target) };
    return { kind: "unknown", id: target, name: target, src: "" };
  };

  H.caseItem = (c, href) => `
    <a class="case-item" href="${href}">
      <div class="row spread">
        <h4>${U.esc(c.title)}</h4>${H.statusTag(c.status)}
      </div>
      <div class="row wrap small muted" style="margin-top:4px">
        ${H.typeTag(c.typeId)} ${H.audTag(c.audience)}
        <span>更新 ${U.esc(U.plainDate(c.updatedAt))}</span>
        ${c.likes ? `<span>赞 ${c.likes}</span>` : ""}
      </div>
    </a>`;

  H.materialLine = (m, href) => `
    <a class="case-item" href="${href}">
      <div class="row spread"><h4>${U.esc(m.title)}</h4>${H.levelTag(m.level)}</div>
      <div class="row wrap small muted" style="margin-top:4px">
        ${H.credTag(m.credibility)}<span>${U.esc(m.source)}</span><span>${U.esc(U.plainDate(m.publishedAt))}</span>
      </div>
    </a>`;

  H.empty = (t) => `<div class="empty">${U.esc(t)}</div>`;

  // ------------------------------------------------------------ 首页（推荐 + 动态卡）
  let newsCache = null; // {at, items} 会话内缓存，避免每次进首页都联网

  P.home = () => {
    const rec = Store.recommendFor();
    const delta = Store.platformDelta();
    const anns = Store.activeAnnouncements();
    const me = Store.me();
    const recCases = rec.cases.slice(0, 5);
    const recMats = rec.materials.slice(0, 6);

    return {
      html: `
      <div class="dyn-grid">
        <div class="card card-pad dyn-card">
          <div class="section-title small"><span>平台动态</span><a class="small" href="#/search">检索全部</a></div>
          <div class="dyn-nums">
            <div><b>${delta.newCases}</b><span>近 7 天新案例</span></div>
            <div><b>${delta.newMaterials}</b><span>近 7 天新素材</span></div>
            <div><b>${delta.newPublished}</b><span>近 7 天新发布</span></div>
          </div>
          <div class="small muted" style="margin-top:8px">全库 ${delta.totalPublished} 个已发布案例 · ${delta.totalMaterials} 条素材 · ${delta.totalKnowledge} 节教材</div>
        </div>
        <div class="card card-pad dyn-card">
          <div class="section-title small"><span>时政要闻</span></div>
          <div id="news-box">${newsCache ? "" : `<div class="small muted">加载中<span class="loading-dots">…</span></div>`}</div>
        </div>
        <div class="card card-pad dyn-card">
          <div class="section-title small"><span>平台公告</span></div>
          ${anns.length ? anns.slice(0, 3).map((a) => `
            <div style="padding:5px 0;border-bottom:1px solid var(--line)">
              <b class="small">${U.esc(a.title)}</b>
              <div class="small muted">${U.esc(a.text.slice(0, 60))}${a.text.length > 60 ? "…" : ""}</div>
            </div>`).join("") : `<div class="small muted">暂无公告</div>`}
        </div>
      </div>
      <div class="home-grid">
        <div>
          <div class="card">
            <div class="card-pad section-title" style="border-bottom:1px solid var(--line)">
              <span>推荐案例</span><span class="small muted">按 ${U.esc(Store.audienceName(me.audience))} · 质量与热度</span>
            </div>
            <div>${recCases.map((c) => H.caseItem(c, "#/case/" + c.id)).join("") || H.empty("暂无推荐")}</div>
          </div>
        </div>
        <div>
          <div class="card">
            <div class="card-pad section-title" style="border-bottom:1px solid var(--line)">
              <span>推荐素材</span><a href="#/search" class="small">检索</a>
            </div>
            <div>${recMats.map((m) => H.materialLine(m, "#/material/" + m.id)).join("") || H.empty("暂无推荐")}</div>
          </div>
        </div>
      </div>`,
      mount() {
        const box = U.$("#news-box");
        const renderNews = (items) => {
          if (!box) return;
          box.innerHTML = items.length ? items.map((n) => `
            <div style="padding:5px 0;border-bottom:1px solid var(--line)">
              <a href="${U.esc(n.url)}" target="_blank" rel="noopener" class="small"><b>${U.esc(n.title)}</b></a>
              <div class="small muted">${U.esc(n.host)} · 点击跳原文</div>
            </div>`).join("") : `<div class="small muted">暂时没有可展示的新闻</div>`;
        };
        if (newsCache && Date.now() - newsCache.at < 30 * 60 * 1000) { renderNews(newsCache.items); return; }
        if (!Store.flags.webSearch) { renderNews([]); return; }
        Copilot.webSearch("思政教育 高校 课程思政 教育政策 最新", 5).then((res) => {
          const items = (res.ok ? res.results || [] : []).map((r) => {
            let host = r.url;
            try { host = new URL(r.url).hostname; } catch (e) { /* ignore */ }
            return { title: r.title || r.url, url: r.url, host };
          });
          newsCache = { at: Date.now(), items };
          renderNews(items);
        }).catch(() => renderNews([]));
      },
    };
  };

  // ------------------------------------------------------------ 我的案例（分组 + 分页 + 待办 + 备课材料）
  const MINE_PAGE = 5;
  const minePages = { doing: 1, reviewing: 1, published: 1 };

  P.myCases = () => {
    const me = Store.me();
    const mine = Store.db.cases.filter((c) => c.ownerId === me.id);
    const todos = Store.todos();
    const preps = Store.myPreps();

    const groups = [
      ["doing", "进行中", mine.filter((c) => c.status === "draft")
        .sort((a, b) => String(b.updatedAt).localeCompare(String(a.updatedAt)))],
      ["reviewing", "审核中", mine.filter((c) => c.status === "pending" || c.status === "reviewing")
        .sort((a, b) => String(b.submittedAt || b.updatedAt).localeCompare(String(a.submittedAt || a.updatedAt)))],
      ["published", "已发布", mine.filter((c) => c.status === "published" || c.status === "hidden")
        .sort((a, b) => String(b.publishedAt || b.updatedAt).localeCompare(String(a.publishedAt || a.updatedAt)))],
    ];

    const groupHTML = ([key, name, list]) => {
      const pages = Math.max(1, Math.ceil(list.length / MINE_PAGE));
      minePages[key] = Math.min(minePages[key], pages);
      const pg = minePages[key];
      const items = list.slice((pg - 1) * MINE_PAGE, pg * MINE_PAGE);
      return `
      <div class="result-group">
        <div class="section-title"><span>${name}（${list.length}）</span></div>
        <div class="card">
          ${items.map((c) => H.caseItem(c, c.status === "published" ? "#/case/" + c.id : "#/workbench/" + c.id)).join("") ||
            H.empty(key === "doing" ? "没有进行中的案例，点击右上角新建" : "暂无")}
        </div>
        ${pages > 1 ? `<div class="pager">
          <button data-mine-page="${key}:${pg - 1}" ${pg <= 1 ? "disabled" : ""}>上一页</button>
          <span class="pager-dots">${pg} / ${pages}</span>
          <button data-mine-page="${key}:${pg + 1}" ${pg >= pages ? "disabled" : ""}>下一页</button>
        </div>` : ""}
      </div>`;
    };

    const todoRows = [];
    todos.returned.forEach((c) => {
      const pendingAnno = c.annotations.filter((a) => a.kind === "admin" && a.status === "pending").length;
      todoRows.push(`<div class="case-item">
        <div class="row spread"><h4>${U.esc(c.title)}</h4><span class="tag red">退回待改</span></div>
        <div class="small muted">${pendingAnno ? `${pendingAnno} 条审核批注待处理` : "审核员已退回，查看批注后修改"}</div>
        <div style="margin-top:6px"><a class="btn sm secondary" href="#/workbench/${c.id}">去修改</a></div>
      </div>`);
    });
    mine.forEach((c) => {
      if (Store.isReturned(c)) return;
      const n = c.annotations.filter((a) => a.status === "pending").length;
      if (n) todoRows.push(`<div class="case-item">
        <div class="row spread"><h4>${U.esc(c.title)}</h4><span class="tag amber">${n} 条待处理批注</span></div>
        <div style="margin-top:6px"><a class="btn sm plain" href="#/workbench/${c.id}">去处理</a></div>
      </div>`);
    });
    (todos.reviewQueue || []).forEach((c) => {
      todoRows.push(`<div class="case-item">
        <div class="row spread"><h4>${U.esc(c.title)}</h4>${H.statusTag(c.status)}</div>
        <div class="small muted">${U.esc(Store.userById(c.ownerId).name)} 提交于 ${U.esc(c.submittedAt || c.updatedAt)}</div>
        <div style="margin-top:6px"><a class="btn sm secondary" href="#/admin/review/${c.id}">去审核</a></div>
      </div>`);
    });

    const PREP_NAME = { "kit-design": "教学设计", "kit-discussion": "讨论题", "kit-ppt": "PPT 提纲" };

    return {
      html: `
      <div class="row spread" style="margin-bottom:14px">
        <h2 style="font-size:18px">我的案例</h2>
        <a class="btn" href="#/new">新建案例</a>
      </div>
      <div class="card" style="margin-bottom:18px">
        <div class="card-pad section-title" style="border-bottom:1px solid var(--line)"><span>待办</span></div>
        <div>${todoRows.join("") || `<div class="card-pad muted small">没有待处理的事项</div>`}</div>
      </div>
      <div class="home-grid">
        <div>
          ${groups.slice(0, 2).map(groupHTML).join("")}
        </div>
        <div>
          ${groupHTML(groups[2])}
          <div class="result-group">
            <div class="section-title"><span>我的备课材料（${preps.length}）</span></div>
            <div class="card">
              ${preps.map((p) => `
                <div class="case-item">
                  <div class="row spread">
                    <h4><span class="tag primary">${U.esc(p.kindName || PREP_NAME[p.kind] || "材料")}</span> ${U.esc(p.caseTitle)}</h4>
                    <span class="row" style="gap:6px">
                      <button class="btn sm plain" data-prep-view="${p.id}">查看</button>
                      <button class="btn sm plain" data-prep-del="${p.id}">删除</button>
                    </span>
                  </div>
                  <div class="small muted" style="margin-top:4px">${U.esc(p.at)} · 来自 <a href="#/case/${p.caseId}">案例详情页</a></div>
                </div>`).join("") || H.empty("还没有备课材料。在已发布案例的详情页可以生成教学设计、讨论题和 PPT 提纲。")}
            </div>
          </div>
        </div>
      </div>`,
      mount(el) {
        el.addEventListener("click", async (e) => {
          const pg = e.target.closest("[data-mine-page]");
          if (pg && !pg.disabled) {
            const [key, n] = pg.dataset.minePage.split(":");
            minePages[key] = Number(n);
            P.rerender();
            return;
          }
          const pv = e.target.closest("[data-prep-view]");
          if (pv) {
            const p = Store.myPreps().find((x) => x.id === pv.dataset.prepView);
            if (p) U.modal(`
              <div class="modal-head"><b>${U.esc(p.kindName || "备课材料")} · ${U.esc(p.caseTitle)}</b><button class="modal-close" data-close>×</button></div>
              <div class="modal-body article">${U.md(p.content)}</div>
              <div class="modal-foot"><button class="btn plain" data-close>关闭</button></div>`);
            return;
          }
          const pd = e.target.closest("[data-prep-del]");
          if (pd) {
            if (await U.confirmModal("删除这份备课材料？", { danger: true })) {
              Store.delPrep(pd.dataset.prepDel);
              P.rerender();
            }
          }
        });
      },
    };
  };

  // ------------------------------------------------------------ 新建案例（一页式：学段 → 类型 → 模板就地展开）
  P.newCase = (params) => {
    const me = Store.me();
    const state = {
      audience: me.prefs.defaultStage || me.audience,
      typeId: params.type || null,
      templateId: null,
    };

    const typeDesc = (t) => {
      const ps = Array.from(new Set(t.templates.map((tp) => tp.purpose || "日常授课")));
      return `${t.templates.length} 个模板 · ${ps.join("、")}`;
    };

    return {
      html: `
      <div style="max-width:820px;margin:0 auto">
        <div class="card card-pad">
          <h2 style="font-size:18px">新建案例</h2>
          <hr class="hr">
          <label class="field"><span>课程与学段</span>
            <div class="row wrap" id="nc-aud">
              ${["grad", "ug", "embed"].map((a) => `<button class="btn sm plain" data-aud="${a}">${Store.audienceName(a)}</button>`).join("")}
            </div>
          </label>
          <label class="field"><span>案例类型</span>
            <div class="nc-type-grid" id="nc-types"></div>
          </label>
          <div id="nc-templates"></div>
          <div class="row" style="justify-content:flex-end;gap:8px;margin-top:14px">
            <a class="btn plain" href="#/mine">取消</a>
            <button class="btn" id="nc-create">创建并进入工作台</button>
          </div>
        </div>
      </div>`,
      mount(el) {
        const drawAud = () => U.$$("[data-aud]", el).forEach((b) => {
          b.classList.toggle("secondary", b.dataset.aud === state.audience);
          b.classList.toggle("plain", b.dataset.aud !== state.audience);
        });
        const drawTypes = () => {
          U.$("#nc-types", el).innerHTML = Store.db.caseTypes.map((t) => `
            <button class="nc-type-card ${t.id === state.typeId ? "on" : ""}" data-type="${t.id}">
              <b>${U.esc(t.name)}</b>
              <span class="small muted">${U.esc(typeDesc(t))}</span>
            </button>`).join("");
          U.$$("[data-type]", el).forEach((b) => b.addEventListener("click", () => {
            state.typeId = b.dataset.type;
            drawTypes(); drawTemplates();
          }));
        };
        const drawTemplates = () => {
          const t = Store.typeById(state.typeId);
          const box = U.$("#nc-templates", el);
          if (!t) { box.innerHTML = ""; return; }
          const list = t.templates.filter((tp) => tp.stages.includes(state.audience));
          const show = list.length ? list : t.templates;
          if (!show.find((x) => x.id === state.templateId)) state.templateId = show[0] ? show[0].id : null;
          box.innerHTML = `
          <label class="field"><span>模板（${U.esc(t.name)}）</span>
            <div>${show.map((tp) => `
              <label class="opt-card ${tp.id === state.templateId ? "on" : ""}">
                <input type="radio" name="nc-tp" value="${tp.id}" ${tp.id === state.templateId ? "checked" : ""} hidden>
                <b>${U.esc(tp.name)} <span class="tag primary">${U.esc(tp.purpose || "日常授课")}</span></b>
                <span class="nc-tpl-secs">${tp.sections.map((s, i) => `${i > 0 ? `<i>→</i>` : ""}<em>${U.esc(s)}</em>`).join("")}</span>
              </label>`).join("") || H.empty("该类型暂无适配模板，将使用空白结构")}</div>
          </label>`;
          U.$$("input[name=nc-tp]", el).forEach((r) => r.addEventListener("change", () => {
            state.templateId = r.value; drawTemplates();
          }));
        };
        U.$$("[data-aud]", el).forEach((b) => b.addEventListener("click", (e) => {
          e.preventDefault();
          state.audience = b.dataset.aud;
          drawAud(); drawTemplates();
        }));
        U.$("#nc-create", el).addEventListener("click", async () => {
          if (!state.typeId) { U.toast("请先选择案例类型"); return; }
          const t = Store.typeById(state.typeId);
          const tp = t && t.templates.find((x) => x.id === state.templateId);
          const c = {
            id: U.uid("c"), title: "未命名案例",
            typeId: state.typeId, audience: state.audience,
            course: me.courses[0] || "", purpose: (tp && tp.purpose) || "日常授课",
            ownerId: me.id, status: "draft",
            author: me.name, org: me.org, summary: "", theoryPoints: [],
            blocks: (tp ? tp.sections : ["案例背景", "案例正文", "分析讨论"]).map((s) => ({ kind: "h2", text: s })),
            citations: [], kit: { design: "", discussion: [], ppt: [], reflist: [] },
            annotations: [], versions: [{ id: U.uid("v"), label: "新建", at: U.now(), note: "创建案例" }],
            tasks: [], likes: 0, likedBy: [],
            createdAt: U.now(), updatedAt: U.now(),
          };
          const saved = await Store.addCase(c);
          if (!saved) return; // 失败提示由 Store 统一弹出
          U.toast("已创建");
          location.hash = "#/workbench/" + c.id;
        });
        drawAud(); drawTypes(); drawTemplates();
      },
    };
  };

  // ------------------------------------------------------------ 偏好设置
  P.prefsModal = () => {
    const me = Store.me();
    const p = me.prefs || {};
    const close = U.modal(`
      <div class="modal-head"><b>教学偏好</b><button class="modal-close" data-close>×</button></div>
      <div class="modal-body">
        <label class="field"><span>默认学段</span>
          <select class="text" id="pf-stage">
            <option value="grad" ${p.defaultStage === "grad" ? "selected" : ""}>硕博公共思政</option>
            <option value="ug" ${p.defaultStage === "ug" ? "selected" : ""}>本科思政</option>
            <option value="embed" ${p.defaultStage === "embed" ? "selected" : ""}>专业课程思政</option>
          </select></label>
        <label class="field"><span>语言风格</span>
          <input class="text" id="pf-style" value="${U.esc(p.style || "")}"></label>
        <label class="field"><span>常用课堂形式</span>
          <input class="text" id="pf-form" value="${U.esc(p.classForm || "")}"></label>
        <label class="row" style="gap:6px"><input type="checkbox" id="pf-auth" ${p.authorityFirst ? "checked" : ""} style="width:auto"> 优先权威来源</label>
      </div>
      <div class="modal-foot">
        <button class="btn plain" data-close>取消</button>
        <button class="btn" id="pf-save">保存</button>
      </div>`);
    U.$("#pf-save").addEventListener("click", () => {
      Store.savePrefs({
        defaultStage: U.$("#pf-stage").value,
        style: U.$("#pf-style").value.trim(),
        classForm: U.$("#pf-form").value.trim(),
        authorityFirst: U.$("#pf-auth").checked,
      });
      close();
      U.toast("偏好已保存");
    });
  };
})();
