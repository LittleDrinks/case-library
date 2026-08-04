// 数据层：组装静态数据、权限、服务端业务数据缓存、检索
(function () {
  const LS_DB = "sizheng-db-v4";
  const LS_USER = "sizheng-user";
  const LS_TOKEN = "sizheng-token";

  const S = { db: null, userId: null, flags: {}, token: localStorage.getItem(LS_TOKEN) || "" };

  // ------------------------------------------------------------ 组装
  // 案例/批注/版本/审核留痕/收藏/点赞的权威在服务端 SQLite（db.py），
  // db.cases/db.reviews/db.favorites 只是登录后从服务端拉取的本地缓存；
  // localStorage 只保留纯前端偏好与本地素材登记（模板改动、上传前登记、公告、备课材料等）
  function buildBase() {
    const R = window.RAWDATA, D = window.SEED;
    const db = {
      users: JSON.parse(JSON.stringify(D.users)),
      caseTypes: JSON.parse(JSON.stringify(D.caseTypes)),
      knowledgeSources: JSON.parse(JSON.stringify(D.knowledgeSources)),
      whitelist: D.whitelist.slice(),
      reviews: [],
      materialOverrides: {},
      customMaterials: [],
      favorites: {},
      announcements: [],
      prepMaterials: [],
      knowledge: R.knowledge,
      chapters: R.chapters,
      book: R.book,
      materials: [],
      cases: [],
      serverMaterials: [],
      fileIndex: {},
    };

    // 素材：手工登记 + 中心组学习资料（教材是知识不是素材，见 db.bookFile，ADR 0011）
    db.bookFile = R.bookFile || null;
    db.materials = D.extraMaterials.map((m) => Object.assign({}, m));
    R.learnDocs.forEach((d) => {
      db.materials.push({
        id: d.id, title: d.title, kind: "资料包", fileId: d.fileId,
        source: "上海大学党委宣传部 · 中心组学习资料",
        sourceUrl: "", publishedAt: d.year + " 年（总第" + d.issue + "期）",
        collectedAt: "2026-07-18", level: 1, credibility: "high",
        scope: "校内教师", status: "正常",
        summary: "校党委中心组学习资料，" + d.year + " 年出版，全文约 " + Math.round(d.chars / 1000) + " 千字。",
        excerpt: d.excerpt || "",
        noSnapshot: !d.excerpt,
      });
    });
    return db;
  }

  function applyOverrides(db) {
    Object.keys(db.materialOverrides).forEach((id) => {
      const m = db.materials.find((x) => x.id === id);
      if (m) Object.assign(m, db.materialOverrides[id]);
    });
  }

  function load() {
    const base = buildBase();
    try {
      const raw = localStorage.getItem(LS_DB);
      if (raw) {
        const saved = JSON.parse(raw);
        ["users", "caseTypes", "knowledgeSources", "whitelist", "materialOverrides", "customMaterials", "announcements", "prepMaterials"].forEach((k) => {
          if (saved[k] != null) base[k] = saved[k];
        });
      }
    } catch (e) { console.warn("本地数据读取失败，使用初始数据", e); }
    base.customMaterials.forEach((m) => {
      if (!base.materials.find((x) => x.id === m.id)) base.materials.unshift(m);
    });
    applyOverrides(base);
    S.db = base;
    S.userId = localStorage.getItem(LS_USER) || "u-chen";
    if (!base.users.find((u) => u.id === S.userId)) S.userId = base.users[0].id;
  }

  let persistTimer = null;
  const persist = () => {
    clearTimeout(persistTimer);
    persistTimer = setTimeout(() => {
      try {
        localStorage.setItem(LS_DB, JSON.stringify({
          users: S.db.users, caseTypes: S.db.caseTypes,
          // 运行时知识源（runtime 标记）权威在服务端 /api/knowledge，不随本地数据持久化
          knowledgeSources: S.db.knowledgeSources.filter((s) => !s.runtime),
          whitelist: S.db.whitelist,
          materialOverrides: S.db.materialOverrides,
          customMaterials: S.db.customMaterials,
          announcements: S.db.announcements,
          prepMaterials: S.db.prepMaterials,
        }));
      } catch (e) { console.warn("保存失败", e); }
    }, 250);
  };

  // ------------------------------------------------------------ 账号与权限
  S.me = () => S.db.users.find((u) => u.id === S.userId);
  S.setUser = (id) => { S.userId = id; localStorage.setItem(LS_USER, id); };
  S.userById = (id) => S.db.users.find((u) => u.id === id);

  // ------------------------------------------------------------ 演示鉴权与服务端文件库（ADR 0009）
  // 页头切换账号 = 登录：账号 ID 换 HMAC token；服务端按 token 校验写操作与文件密级
  S.login = async (id) => {
    try {
      const r = await U.postJSON("/api/auth/login", { userId: id });
      if (r && r.ok) {
        S.token = r.token;
        localStorage.setItem(LS_TOKEN, r.token);
      } else {
        S.token = "";
        localStorage.removeItem(LS_TOKEN);
      }
      return r;
    } catch (e) {
      return { ok: false, error: "登录服务不可用" };
    }
  };
  S.authHeaders = () => (S.token ? { Authorization: "Bearer " + S.token } : {});
  S.apiFetch = (path, opts) => {
    opts = opts || {};
    opts.headers = Object.assign({}, opts.headers || {}, S.authHeaders());
    return fetch(path, opts);
  };

  // 服务端上传素材并入 db.materials（权威在服务端，不写入 localStorage）
  function mergeServerMaterials() {
    const overrides = S.db.materialOverrides;
    S.db.materials = S.db.materials.filter((m) => !m.uploaded);
    (S.db.serverMaterials || []).forEach((m) => {
      const up = uploadTexts[m.id];
      // 已拉到全文的素材补一份摘录，供素材卡片与 Copilot 上下文引用
      const ex = m.excerpt || (up ? up.text.slice(0, 2000) : "");
      S.db.materials.unshift(Object.assign({}, m, ex ? { excerpt: ex } : {}, overrides[m.id] || {}));
    });
  }

  // 上传素材全文：服务端对 md/txt/docx 上传抽取了纯文本（textPath），登录态下拉取
  // 供素材卡片摘录与素材详情页切片预览；拉取失败/未登录静默降级为 title/summary。
  const LS_UPTEXT = "sizheng-uptext";
  const UPTEXT_MAX = 200 * 1000; // 单文件文本缓存上限（防 localStorage 爆配额）
  const uploadTexts = {}; // materialId -> { text }（运行时数据，不持久化）

  function upCacheLoad() {
    try { return JSON.parse(localStorage.getItem(LS_UPTEXT) || "{}") || {}; } catch (e) { return {}; }
  }
  function applyUploadText(m, text) {
    if (text && text.trim()) uploadTexts[m.id] = { text: text };
    else delete uploadTexts[m.id];
  }
  async function fetchUploadTexts() {
    if (!S.token) return false; // 未登录：保持现状（仅 title/summary 可见）
    const cache = upCacheLoad();
    const next = {};
    let fetched = false;
    const jobs = (S.db.serverMaterials || []).map(async (m) => {
      if (!m.fileId) return;
      const fi = (S.db.fileIndex || {})[m.fileId] || {};
      if ("textPath" in fi && !fi.textPath) return; // 索引明确标记无可抽取文本
      const key = m.fileId + "|" + (fi.textPath || "") + "|" + (fi.size || 0);
      if (cache[key] !== undefined) {
        next[key] = cache[key];
        applyUploadText(m, cache[key]);
        return;
      }
      try {
        const resp = await S.apiFetch("/api/files/" + encodeURIComponent(m.fileId) + "/text");
        const d = await resp.json();
        const text = d && d.ok ? String(d.text || "").slice(0, UPTEXT_MAX) : "";
        next[key] = text;
        fetched = true;
        applyUploadText(m, text);
      } catch (e) { /* 静默降级：仅 title/summary 可见 */ }
    });
    await Promise.all(jobs);
    if (fetched) {
      try { localStorage.setItem(LS_UPTEXT, JSON.stringify(next)); } catch (e) { /* 配额满则不缓存 */ }
    }
    return fetched;
  }

  // 异步语料扩充后，若当前停留在检索/知识/素材/案例页则原地重渲染（Pages.rerender 由 main.js 注入）
  function rerenderIfReading() {
    try {
      const v = U.$("#view");
      if (!v || !v.innerHTML) return; // 首轮渲染尚未发生，路由会自然使用新语料
      if (!/#\/(search|knowledge|book|material|case)/.test(location.hash)) return;
      if (window.Pages && window.Pages.rerender) window.Pages.rerender();
    } catch (e) { /* 渲染层未就绪时忽略 */ }
  }

  S.syncServerMaterials = async () => {
    try {
      const resp = await S.apiFetch("/api/files");
      const d = await resp.json();
      if (d && d.ok) {
        S.db.serverMaterials = d.materials || [];
        S.db.fileIndex = d.files || {};
        const got = await fetchUploadTexts();
        mergeServerMaterials();
        if (got) rerenderIfReading();
      }
    } catch (e) { /* 服务端不可用时保持本地数据 */ }
  };
  S.fileInfo = (fileId) => (S.db.fileIndex || {})[fileId] || null;
  S.uploadMaterialFile = async (payload) => {
    try {
      const resp = await S.apiFetch("/api/files", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const d = await resp.json();
      if (d && d.ok) await S.syncServerMaterials();
      return d;
    } catch (e) {
      return { ok: false, error: "上传请求失败（服务不可用）" };
    }
  };
  S.deleteMaterialFile = async (fileId) => {
    try {
      const resp = await S.apiFetch("/api/files/" + encodeURIComponent(fileId), { method: "DELETE" });
      const d = await resp.json();
      if (d && d.ok) await S.syncServerMaterials();
      return d;
    } catch (e) {
      return { ok: false, error: "删除请求失败（服务不可用）" };
    }
  };

  S.canSeeMaterial = (m) => m.level <= S.me().maxLevel && m.status !== "停用";
  S.canSeeCase = (c) => c.status === "published" || c.ownerId === S.userId || S.me().admin;
  S.visibleMaterials = () => S.db.materials.filter(S.canSeeMaterial);
  S.visibleCases = () => S.db.cases.filter(S.canSeeCase);
  S.materialById = (id) => {
    const m = S.db.materials.find((x) => x.id === id);
    return m && S.canSeeMaterial(m) ? m : null;
  };
  S.knowledgeById = (id) => S.db.knowledge.find((k) => k.id === id);
  S.caseById = (id) => {
    const c = S.db.cases.find((x) => x.id === id);
    return c && S.canSeeCase(c) ? c : null;
  };
  S.typeById = (id) => S.db.caseTypes.find((t) => t.id === id);
  S.typeName = (id) => { const t = S.typeById(id); return t ? t.name : "通用案例"; };
  S.audienceName = (a) => S.db.audienceNames ? S.db.audienceNames[a] : (window.SEED.audienceNames[a] || a);
  S.citeTarget = (id) => S.knowledgeById(id) || S.materialById(id);

  // ------------------------------------------------------------ 服务端业务数据（案例闭环）
  async function apiJSON(path, opts) {
    opts = opts || {};
    opts.headers = Object.assign({ "Content-Type": "application/json" }, opts.headers || {});
    const resp = await S.apiFetch(path, opts);
    try { return await resp.json(); } catch (e) { return null; }
  }
  // 写操作失败必须让用户看见（不静默丢数据、不假装成功）
  const apiFail = (d, verb) => {
    U.toast(verb + "失败：" + ((d && d.error) || "服务不可用，请稍后重试"), 3600);
    return null;
  };

  // 服务端返回的案例整体替换本地缓存（保持对象身份，页面持有的引用不失效）
  function replaceCase(fresh) {
    const cur = S.db.cases.find((x) => x.id === fresh.id);
    if (!cur) { S.db.cases.unshift(fresh); return fresh; }
    Object.keys(cur).forEach((k) => { if (!(k in fresh)) delete cur[k]; });
    Object.assign(cur, fresh);
    return cur;
  }

  // 登录后/切换账号后拉取业务数据；审核留痕仅 admin 可见，收藏按当前账号
  S.syncCases = async () => {
    try {
      const d = await apiJSON("/api/cases");
      if (!d || !d.ok) throw new Error((d && d.error) || "cases");
      S.db.cases = d.cases || [];
      if (S.me() && S.me().admin) {
        const r = await apiJSON("/api/reviews");
        S.db.reviews = (r && r.ok) ? r.reviews : [];
      } else S.db.reviews = [];
      const f = await apiJSON("/api/favorites");
      S.db.favorites = {};
      if (f && f.ok) S.db.favorites[S.userId] = f.caseIds || [];
      return true;
    } catch (e) {
      U.toast("案例数据加载失败：服务不可用，请稍后刷新重试", 4000);
      return false;
    }
  };

  // 高频编辑（正文/引用/kit/标签）先落本地缓存保持编辑流畅，再防抖 PATCH 到服务端；
  // 失败明确提示；响应里的服务端自检批注（selfcheck）同步回本地
  const caseSyncTimers = {};
  function syncCaseSoon(c) {
    clearTimeout(caseSyncTimers[c.id]);
    caseSyncTimers[c.id] = setTimeout(async () => {
      delete caseSyncTimers[c.id];
      try {
        const d = await apiJSON("/api/cases/" + encodeURIComponent(c.id), {
          method: "PATCH", body: JSON.stringify(c),
        });
        if (!d || !d.ok) { apiFail(d, "保存"); return; }
        c.updatedAt = d.case.updatedAt;
        c.annotations = d.case.annotations;
      } catch (e) { apiFail(null, "保存"); }
    }, 400);
  }

  // ------------------------------------------------------------ 变更
  // persist 仍负责 localStorage 里的前端偏好；传入案例时同步内容到服务端
  S.saveCase = (c) => { persist(); if (c) syncCaseSoon(c); };
  S.touch = (c) => { c.updatedAt = U.now(); syncCaseSoon(c); };

  S.addCase = async (c) => {
    try {
      const d = await apiJSON("/api/cases", { method: "POST", body: JSON.stringify(c) });
      if (!d || !d.ok) return apiFail(d, "创建案例");
      return replaceCase(d.case);
    } catch (e) { return apiFail(null, "创建案例"); }
  };
  S.deleteCase = async (id) => {
    try {
      const d = await apiJSON("/api/cases/" + encodeURIComponent(id), { method: "DELETE" });
      if (!d || !d.ok) { apiFail(d, "删除案例"); return false; }
      S.db.cases = S.db.cases.filter((c) => c.id !== id);
      return true;
    } catch (e) { apiFail(null, "删除案例"); return false; }
  };

  // 提交轮次 = 已生成的「提交版」数量
  S.submitRound = (c) => c.versions.filter((v) => v.label.indexOf("提交版") === 0).length;

  // 审核流转：先调 API，成功后用服务端返回的案例与留痕更新本地缓存
  async function caseAction(c, path, body, verb) {
    try {
      const d = await apiJSON("/api/cases/" + encodeURIComponent(c.id) + "/" + path, {
        method: "POST", body: JSON.stringify(body || {}),
      });
      if (!d || !d.ok) { apiFail(d, verb); return false; }
      replaceCase(d.case);
      if (d.reviews) {
        S.db.reviews = d.reviews.concat(S.db.reviews.filter((r) => r.caseId !== c.id));
      }
      return true;
    } catch (e) { apiFail(null, verb); return false; }
  }
  S.submitCase = (c) => caseAction(c, "submit", {}, "提交审核");
  // 仅在管理员开始审核前可撤回（服务端校验）
  S.withdrawCase = (c) => caseAction(c, "withdraw", {}, "撤回");
  S.startReview = (c) => caseAction(c, "review", { action: "start" }, "开始审核");
  // 批注即意见：具体问题以批注形式挂在正文上，opinion 只是可选总评
  S.reviewCase = (c, action, opinion, offlineFrom) =>
    caseAction(c, "review", {
      action: action === "return" ? "reject" : action,
      reason: opinion || "", offlineFrom: offlineFrom || "",
    }, "审核操作");
  S.unhideCase = (c) => caseAction(c, "review", { action: "unhide" }, "恢复公开");

  // 被打回待改：草稿态且最近一次流转是退回/要求补充
  S.isReturned = (c) => {
    if (c.status !== "draft") return false;
    const acts = c.versions.filter((v) =>
      v.label === "退回" || v.label === "要求补充" || v.label.indexOf("提交版") === 0);
    const last = acts[acts.length - 1];
    return !!last && (last.label === "退回" || last.label === "要求补充");
  };

  // 手动版本快照：结构与自动快照一致（at/label/正文序列化），仅作者本人
  S.saveVersion = async (caseId, label) => {
    const c = S.db.cases.find((x) => x.id === caseId);
    if (!c) return null;
    try {
      const d = await apiJSON("/api/cases/" + encodeURIComponent(caseId) + "/versions", {
        method: "POST", body: JSON.stringify({ label: label || "" }),
      });
      if (!d || !d.ok) { apiFail(d, "保存版本"); return null; }
      c.versions = d.versions;
      return d.version;
    } catch (e) { apiFail(null, "保存版本"); return null; }
  };

  // 版本回滚：服务端先给当前正文打「回滚前自动快照」留退路，再恢复指定版本；仅作者本人
  S.rollbackVersion = async (caseId, versionId) => {
    const c = S.db.cases.find((x) => x.id === caseId);
    if (!c) return false;
    try {
      const d = await apiJSON("/api/cases/" + encodeURIComponent(caseId) +
        "/versions/" + encodeURIComponent(versionId) + "/rollback", { method: "POST", body: "{}" });
      if (!d || !d.ok) { apiFail(d, "回滚"); return false; }
      replaceCase(d.case);
      return true;
    } catch (e) { apiFail(null, "回滚"); return false; }
  };

  // 批注：先调 API，成功后用服务端返回的批注列表更新本地缓存（含服务端自检批注）
  S.setAnnoStatus = async (c, annoId, status, extra) => {
    try {
      const d = await apiJSON("/api/annotations/" + encodeURIComponent(annoId), {
        method: "PATCH", body: JSON.stringify(Object.assign({ status: status }, extra || {})),
      });
      if (!d || !d.ok) { apiFail(d, "更新批注"); return false; }
      const a = c.annotations.find((x) => x.id === annoId);
      if (a) Object.assign(a, d.annotation);
      return true;
    } catch (e) { apiFail(null, "更新批注"); return false; }
  };
  S.addAnnotation = async (c, anno) => {
    anno = Object.assign({ id: U.uid("an"), createdAt: U.now(), status: "pending", replies: [] }, anno);
    try {
      const d = await apiJSON("/api/cases/" + encodeURIComponent(c.id) + "/annotations", {
        method: "POST", body: JSON.stringify(anno),
      });
      if (!d || !d.ok) { apiFail(d, "保存批注"); return null; }
      c.annotations = d.annotations;
      return d.annotation;
    } catch (e) { apiFail(null, "保存批注"); return null; }
  };
  // 批注线程：作者回应/审核员追问都追加到同一条批注下；追问会重开已解决的批注
  S.replyAnnotation = async (c, annoId, text, reopen) => {
    try {
      const d = await apiJSON("/api/annotations/" + encodeURIComponent(annoId), {
        method: "PATCH", body: JSON.stringify({ reply: { text: text, reopen: !!reopen } }),
      });
      if (!d || !d.ok) { apiFail(d, "回复批注"); return false; }
      const a = c.annotations.find((x) => x.id === annoId);
      if (a) Object.assign(a, d.annotation);
      return true;
    } catch (e) { apiFail(null, "回复批注"); return false; }
  };

  S.likeCase = async (c) => {
    const liked = (c.likedBy || []).includes(S.userId);
    try {
      const d = await apiJSON("/api/cases/" + encodeURIComponent(c.id) + "/like", {
        method: liked ? "DELETE" : "POST",
      });
      if (!d || !d.ok) { apiFail(d, "点赞"); return false; }
      c.likes = d.likes;
      c.likedBy = d.likedBy;
      return true;
    } catch (e) { apiFail(null, "点赞"); return false; }
  };

  S.updateMaterial = (id, patch) => {
    S.db.materialOverrides[id] = Object.assign(S.db.materialOverrides[id] || {}, patch);
    applyOverrides(S.db);
    persist();
    // 挂了真实文件的素材：密级调整同步到服务端索引，保持下载强制与界面一致
    const m = S.db.materials.find((x) => x.id === id);
    if (m && m.fileId && patch.level != null) S.syncFileLevel(m.fileId, Number(patch.level));
  };
  S.syncFileLevel = async (fileId, level) => {
    try {
      await S.apiFetch("/api/files/" + encodeURIComponent(fileId), {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ level: level }),
      });
    } catch (e) { /* 服务端不可用时仅本地生效 */ }
  };
  S.addMaterial = (m) => {
    S.db.customMaterials.unshift(m);
    S.db.materials.unshift(m);
    persist();
    return m;
  };
  S.savePrefs = (prefs) => { S.me().prefs = prefs; persist(); };
  // 重置演示数据：清本地偏好 + 服务端业务表重灌种子（仅 admin，服务端再校验）
  S.resetAll = async () => {
    Object.keys(caseSyncTimers).forEach((k) => clearTimeout(caseSyncTimers[k]));
    clearTimeout(persistTimer);
    localStorage.removeItem(LS_DB);
    try { await apiJSON("/api/admin/reseed", { method: "POST", body: "{}" }); } catch (e) { /* 忽略 */ }
    load();
  };

  // ------------------------------------------------------------ 收藏
  S.isFav = (c) => (S.db.favorites[S.userId] || []).includes(c.id);
  S.toggleFav = async (c) => {
    const on = !S.isFav(c);
    try {
      const d = await apiJSON("/api/cases/" + encodeURIComponent(c.id) + "/favorite", {
        method: on ? "POST" : "DELETE",
      });
      if (!d || !d.ok) { apiFail(d, "收藏"); return false; }
      S.db.favorites[S.userId] = d.caseIds;
      return true;
    } catch (e) { apiFail(null, "收藏"); return false; }
  };
  S.favCases = () => S.visibleCases().filter((c) => S.isFav(c));

  // ------------------------------------------------------------ 平台公告（管理后台维护，首页展示）
  S.activeAnnouncements = () => S.db.announcements.filter((a) => a.online);
  S.addAnnouncement = (a) => {
    S.db.announcements.unshift(Object.assign({ id: U.uid("nc"), at: U.now(), by: S.userId, online: true }, a));
    persist();
  };
  S.setAnnouncement = (id, patch) => {
    const a = S.db.announcements.find((x) => x.id === id);
    if (a) { Object.assign(a, patch); persist(); }
  };

  // ------------------------------------------------------------ 我的备课材料（案例详情页生成，归生成者个人）
  S.addPrep = (p) => {
    S.db.prepMaterials.unshift(Object.assign({ id: U.uid("pp"), by: S.userId, at: U.now() }, p));
    persist();
  };
  S.myPreps = () => S.db.prepMaterials.filter((p) => p.by === S.userId);
  S.delPrep = (id) => {
    S.db.prepMaterials = S.db.prepMaterials.filter((p) => p.id !== id);
    persist();
  };

  // ------------------------------------------------------------ 案例备课 kit（作者本人可写）
  // kit 现有键：design（教学设计，字符串）、discussion（讨论题，数组）、ppt（PPT 提纲，数组）、reflist（参考文献，数组）
  const KIT_KEYS = { design: "教学设计", discussion: "讨论题", ppt: "PPT 提纲", reflist: "参考文献" };
  const KIT_ALIAS = {
    "教学设计": "design", "讨论题": "discussion", "课堂讨论题": "discussion",
    "ppt": "ppt", "PPT": "ppt", "PPT 提纲": "ppt", "参考文献": "reflist",
  };
  S.saveKitItem = (caseId, kind, content) => {
    const c = S.db.cases.find((x) => x.id === caseId);
    if (!c || c.ownerId !== S.userId) return null;
    const key = KIT_KEYS[kind] ? kind : KIT_ALIAS[kind];
    if (!key) return null;
    c.kit = Object.assign({ design: "", discussion: [], ppt: [], reflist: [] }, c.kit || {});
    let value = content;
    if (key === "design") {
      value = String(content == null ? "" : content);
    } else if (typeof content === "string") {
      // 字符串按行拆成条目，剥掉常见序号/列表符
      value = content.split("\n")
        .map((s) => s.replace(/^\s*(?:\d+\s*[.、)]|[-*•])\s*/, "").trim())
        .filter(Boolean);
    } else if (!Array.isArray(content)) {
      value = content == null ? [] : [String(content)];
    }
    c.kit[key] = value;
    syncCaseSoon(c);
    return { kind: key, kindName: KIT_KEYS[key], content: c.kit[key] };
  };

  // ------------------------------------------------------------ 模板编辑（管理后台）
  S.updateTemplate = (typeId, tplId, patch) => {
    const t = S.typeById(typeId);
    const tp = t && t.templates.find((x) => x.id === tplId);
    if (tp) { Object.assign(tp, patch); persist(); }
  };

  // ------------------------------------------------------------ 引用挂接（集中维护，使用度统计的基础）
  S.cite = (c, targetId) => {
    c.citations = c.citations || [];
    if (!c.citations.some((r) => r.target === targetId)) {
      c.citations.push({ target: targetId, at: U.now() });
      syncCaseSoon(c);
    }
  };
  S.uncite = (c, targetId) => {
    c.citations = (c.citations || []).filter((r) => r.target !== targetId);
    syncCaseSoon(c);
  };
  S.isCited = (c, targetId) => (c.citations || []).some((r) => r.target === targetId);

  // ------------------------------------------------------------ 素材使用度与生命周期
  // 「被用」= 被案例正文引用；浏览不计入
  S.materialUsage = (mid) => {
    let count = 0, lastAt = "";
    S.db.cases.forEach((c) => {
      const sets = [c.citations || []];
      if (c.publishedSnapshot && c.publishedSnapshot.citations) sets.push(c.publishedSnapshot.citations);
      sets.forEach((set) => set.forEach((r) => {
        const t = typeof r === "string" ? r : r.target;
        if (t !== mid) return;
        count++;
        const at = (typeof r === "object" && r.at) || c.updatedAt || "";
        if (at > lastAt) lastAt = at;
      }));
    });
    return { count, lastAt };
  };
  // 待淘汰：从未被引用且入库超过 30 天（被引过的素材视为持续在用）
  S.isDormant = (m) => {
    if (S.materialUsage(m.id).count > 0) return false;
    const born = Date.parse(m.collectedAt || m.publishedAt || "") || 0;
    return !!born && (Date.now() - born) > 30 * 86400000;
  };
  // 时效提示：文档类（政策文件）发布超过 3 年
  S.isPolicyDated = (m) => {
    const y = parseInt(String(m.publishedAt || "").slice(0, 4), 10);
    return m.kind === "文档" && !!y && y <= new Date().getFullYear() - 3;
  };
  // 采集查重双闸：URL 查重 + 相似度查重（top-3，服务端检索）
  S.dupCheck = async (url, titleText) => {
    const urlDup = url ? S.db.materials.find((m) => m.sourceUrl && m.sourceUrl === url) : null;
    let similar = [];
    if (titleText && titleText.trim()) {
      const r = await S.search(titleText, { kind: "materials", limit: 3 });
      similar = r.materials.map((e) => e.item).filter((m) => !urlDup || m.id !== urlDup.id).slice(0, 3);
    }
    return { urlDup, similar };
  };

  // ------------------------------------------------------------ 引用关系
  // 正文统一为 blocks 模型：标题是带格式的文字（h2），段落是 p，均可自由增删
  function sectionsToBlocks(sections) {
    const blocks = [];
    (sections || []).forEach((s) => {
      if (s.title) blocks.push({ kind: "h2", text: s.title });
      (s.paras || []).forEach((p) => blocks.push({ kind: "p", text: p }));
    });
    return blocks;
  }
  S.blocksOf = (c) => (c.blocks ? c.blocks : sectionsToBlocks(c.sections));
  S.setBlocks = (c, blocks) => { c.blocks = blocks; delete c.sections; };

  // ------------------------------------------------------------ 标签
  // 案例与素材共用一套标签；案例的理论知识点自动并入标签
  S.tagsOf = (kind, item) => {
    const own = item.tags || [];
    const derived = kind === "case" ? (item.theoryPoints || []) : [];
    return Array.from(new Set(own.concat(derived)));
  };
  S.allTags = () => {
    const count = {};
    S.visibleCases().forEach((c) => S.tagsOf("case", c).forEach((t) => { count[t] = (count[t] || 0) + 1; }));
    S.visibleMaterials().forEach((m) => S.tagsOf("material", m).forEach((t) => { count[t] = (count[t] || 0) + 1; }));
    return Object.entries(count).sort((a, b) => b[1] - a[1]);
  };
  S.setCaseTags = (c, tags) => {
    // 理论知识点保持不动，自有标签 = 全部标签减去理论知识点
    c.tags = Array.from(new Set(tags.filter((t) => !(c.theoryPoints || []).includes(t))));
    syncCaseSoon(c);
  };
  S.setMaterialTags = (id, tags) => {
    S.db.materialOverrides[id] = Object.assign(S.db.materialOverrides[id] || {}, { tags });
    applyOverrides(S.db);
    persist();
  };
  S.hasTag = (kind, item, tagSet) => {
    if (!tagSet || !tagSet.size) return true;
    return S.tagsOf(kind, item).some((t) => tagSet.has(t));
  };

  // 关键词规则打标（无需 AI 的标签建议）
  const TAG_RULES = [
    [/科学家精神|钱伟长|钱学森|邓稼先|黄大年|南仁东/, "科学家精神"],
    [/大思政课|场馆|实践教学基地|图书馆|博物馆/, "大思政课"],
    [/课程思政|新工科|工程伦理|一流课程/, "课程思政"],
    [/医工|微电子|集成电路|芯片|生物医药|交叉学科/, "交叉创新"],
    [/科教融合|研究院|科研反哺/, "科教融合"],
    [/科技自立自强|卡脖子|供应链|断供|国产替代|自主创新/, "科技自立自强"],
    [/人工智能|AIGC|生成式|大模型|智能控制/, "人工智能"],
    [/二十大|二十届|政策|纲要|意见|决定|讲话/, "政策落实"],
    [/乡村振兴|共同富裕|脱贫/, "乡村振兴"],
    [/文化自信|传统文化|非遗/, "文化自信"],
    [/生态文明|双碳|碳达峰|绿色低碳/, "生态文明"],
    [/青年|大学生|研究生|立德树人/, "青年使命"],
    [/科技报国|报国/, "科技报国"],
  ];
  S.suggestTags = (c) => {
    const text = c.title + "\n" + (c.summary || "") + "\n" + S.blocksOf(c).map((b) => b.text).join("\n");
    return TAG_RULES.filter(([re]) => re.test(text)).map(([, tag]) => tag);
  };

  S.casesCiting = (targetId) => S.visibleCases().filter((c) =>
    (c.citations || []).some((r) => r.target === targetId) ||
    (c.publishedSnapshot && (c.publishedSnapshot.citations || []).some((r) => r.target === targetId)));
  S.knowledgeOfCase = (c) => (c.citations || []).map((r) => S.knowledgeById(r.target)).filter(Boolean);
  S.materialsOfCase = (c) => (c.citations || []).map((r) => S.materialById(r.target)).filter(Boolean);
  // 相关案例：同类型 + 同学段 + 共享引用 加权，至少取 3 条
  S.relatedCases = (c, n) => {
    const score = (x) => {
      if (x.id === c.id) return -1;
      let s = 0;
      if (x.typeId === c.typeId) s += 2;
      if (x.audience === c.audience) s += 1;
      (x.citations || []).forEach((r) => {
        if ((c.citations || []).some((y) => y.target === r.target)) s += 2;
      });
      return s;
    };
    return S.visibleCases().filter((x) => x.id !== c.id)
      .map((x) => ({ x, s: score(x) }))
      .filter((e) => e.s > 0)
      .sort((a, b) => b.s - a.s)
      .slice(0, n || 3).map((e) => e.x);
  };

  // ------------------------------------------------------------ 提交前自检
  // 未过项的「系统自检」批注由服务端在每次写入后同步（所有客户端看到同一份）
  S.selfChecks = (c) => {
    const blocks = S.blocksOf(c);
    const paras = blocks.filter((b) => b.kind === "p" && b.text.trim());
    const chars = paras.reduce((n, b) => n + b.text.length, 0);
    let emptyH2 = false;
    for (let i = 0; i < blocks.length; i++) {
      if (blocks[i].kind === "h2" && blocks[i].text.trim()) {
        const next = blocks.slice(i + 1).find((b) => b.kind === "h2" || (b.kind === "p" && b.text.trim()));
        if (!next || next.kind === "h2") { emptyH2 = true; break; }
      }
    }
    return [
      { id: "ck-title", name: "标题已填写（非默认标题）", ok: !!c.title.trim() && c.title !== "未命名案例" },
      { id: "ck-paras", name: "正文段落不少于 3 段", ok: paras.length >= 3 },
      { id: "ck-emptyh2", name: "没有空标题（每个标题下都有正文）", ok: !emptyH2 },
      { id: "ck-cite", name: "至少 1 处引用（理论或素材有着落）", ok: (c.citations || []).length >= 1 },
      { id: "ck-len", name: "正文不少于 600 字", ok: chars >= 600 },
      { id: "ck-risk", name: "无待处理的风险提示批注", ok: !c.annotations.some((a) => a.kind === "risk" && a.status === "pending") },
    ];
  };

  // ------------------------------------------------------------ 首页推荐与平台动态
  S.recommendFor = () => {
    const me = S.me();
    const year = (d) => parseInt(String(d || "").slice(0, 4), 10) || 0;
    const cases = S.visibleCases().filter((c) => c.status === "published").map((c) => {
      let s = 0;
      if (c.audience === me.audience) s += 2;
      s += Math.min(c.likes || 0, 50) * 0.1;
      s += (c.citations || []).length * 0.3;
      s += Math.max(0, year(c.publishedAt) - 2018) * 0.2;
      return { c, s };
    }).sort((a, b) => b.s - a.s).map((x) => x.c);
    const materials = S.visibleMaterials().map((m) => {
      let s = 0;
      if (m.credibility === "high") s += 2;
      s += Math.min(S.materialUsage(m.id).count, 10) * 0.5;
      s += Math.max(0, year(m.publishedAt || m.collectedAt) - 2018) * 0.2;
      return { m, s };
    }).sort((a, b) => b.s - a.s).map((x) => x.m);
    return { cases, materials };
  };
  S.platformDelta = () => {
    const t7 = Date.now() - 7 * 86400000;
    const in7 = (d) => (Date.parse(d || "") || 0) >= t7;
    return {
      newCases: S.db.cases.filter((c) => in7(c.createdAt)).length,
      newPublished: S.db.cases.filter((c) => in7(c.publishedAt)).length,
      newMaterials: S.db.materials.filter((m) => in7(m.collectedAt)).length,
      totalPublished: S.db.cases.filter((c) => c.status === "published").length,
      totalMaterials: S.db.materials.length,
      totalKnowledge: S.db.knowledge.length,
    };
  };

  // 引用该受限/失效素材的案例（风险处理）
  S.affectedByMaterial = (mid) => S.db.cases.filter((c) =>
    (c.citations || []).some((r) => r.target === mid));

  // ------------------------------------------------------------ 检索（服务端 BM25，统一口径，ADR 0004/0010）
  // 服务端返回 id/snippet/score/深链字段（materialId/sec），这里映射回本地条目：
  // 渲染、权限与深链都基于本地对象
  S.search = async (q, filters, termsOverride) => {
    filters = filters || {};
    const terms = (termsOverride && termsOverride.length ? termsOverride : U.terms(q)).slice(0, 30);
    const out = { cases: [], knowledge: [], materials: [], terms };
    if (!terms.length) return out;
    const kinds = filters.kind === "materials" ? ["material"]
      : filters.kind === "cases" ? ["case"] : ["case", "knowledge", "material"];
    let d = null;
    try {
      d = await apiJSON("/api/search", {
        method: "POST",
        body: JSON.stringify({ q: q, terms: terms, kinds: kinds, limit: filters.limit || 20 }),
      });
    } catch (e) { d = null; }
    if (!d || !d.ok) {
      U.toast("检索服务不可用，请稍后重试", 3200);
      return out;
    }
    (d.cases || []).forEach((h) => {
      const item = S.caseById(h.id);
      if (!item) return;
      if (filters.typeId && item.typeId !== filters.typeId) return;
      if (filters.audience && item.audience !== filters.audience) return;
      out.cases.push({ item: item, reasons: [h.snippet], score: h.score });
    });
    (d.knowledge || []).forEach((h) => {
      const item = S.knowledgeById(h.id) ||
        { id: h.id, title: h.title, chapter: h.chapter, text: h.snippet };
      out.knowledge.push({ item: item, reasons: [h.snippet], score: h.score });
    });
    (d.materials || []).forEach((h) => {
      const item = S.materialById(h.materialId || h.id) || {
        id: h.materialId || h.id, title: h.title, source: h.source,
        level: h.level, credibility: h.credibility, summary: h.snippet,
        kind: "文档", status: "正常", tags: [],
      };
      if (filters.credibility && item.credibility !== filters.credibility) return;
      if (filters.level !== undefined && filters.level !== "" && item.level !== Number(filters.level)) return;
      const e = { item: item, reasons: [h.snippet], score: h.score };
      if (h.sec) e.sec = h.sec;
      out.materials.push(e);
    });
    return out;
  };

  // 与当前案例相关的资料（工作台资料区）
  S.relatedForCase = async (c) => {
    const q = [c.title, (c.theoryPoints || []).join(" "), c.course].join(" ");
    const r = await S.search(q, {});
    return {
      knowledge: r.knowledge.slice(0, 6),
      materials: r.materials.slice(0, 6),
    };
  };

  // 待办（我的案例页 + 导航红点）
  S.todos = () => {
    const me = S.me();
    const mine = S.db.cases.filter((c) => c.ownerId === me.id);
    const pendingAnnos = mine.reduce((n, c) => n + c.annotations.filter((a) => a.status === "pending").length, 0);
    const returned = mine.filter(S.isReturned);
    const reviewing = S.db.cases.filter((c) => c.status === "pending" || c.status === "reviewing");
    return { pendingAnnos, returned, reviewQueue: me.admin ? reviewing : [] };
  };

  // ------------------------------------------------------------ 运行时知识源（服务端在线导入，与构建期教材并列）
  // GET /api/knowledge 无需鉴权；section/chapter id 以 sourceId 为前缀，
  // 合并进 db.knowledge/db.chapters 后与教材节走同一权限、检索与详情路由（#/knowledge/:id 按 id 查表）。
  function mergeRuntimeKnowledge(sources) {
    // 先清掉上一轮合并的运行时内容，再并入最新，保证幂等（同名来源服务端覆盖导入时也干净）
    S.db.knowledge = S.db.knowledge.filter((k) => !k.runtimeSrc);
    S.db.chapters = S.db.chapters.filter((ch) => !ch.runtimeSrc);
    S.db.knowledgeSources = S.db.knowledgeSources.filter((s) => !s.runtime);
    (sources || []).forEach((src) => {
      if (!src || !src.sourceId) return;
      const secs = Array.isArray(src.sections) ? src.sections : [];
      S.db.knowledgeSources.push({
        id: src.sourceId, name: src.name || src.sourceId, version: "",
        updatedAt: src.importedAt || "", entries: secs.length, status: "已导入",
        source: src.source || "", runtime: true,
      });
      (src.chapters || []).forEach((ch) => {
        if (!ch || !ch.id) return;
        S.db.chapters.push({
          id: ch.id, index: ch.index, title: ch.title, intro: ch.intro || "",
          sections: (ch.sections || []).slice(), runtimeSrc: src.sourceId,
        });
      });
      secs.forEach((s) => {
        if (!s || !s.id) return;
        S.db.knowledge.push({
          id: s.id, chapterId: s.chapterId, chapter: s.chapter, index: s.index,
          title: s.title, text: s.text || "", runtimeSrc: src.sourceId,
        });
      });
    });
  }
  S.syncKnowledge = async () => {
    try {
      const resp = await fetch("/api/knowledge");
      const d = await resp.json();
      if (Array.isArray(d)) {
        mergeRuntimeKnowledge(d);
        rerenderIfReading();
        return true;
      }
    } catch (e) { /* 服务端不可用时仅保留构建期教材 */ }
    return false;
  };

  load();
  // 初始化后异步合并服务端运行时知识源：停留在知识/检索相关页时自动重渲染
  S.syncKnowledge();
  window.Store = S;
})();
