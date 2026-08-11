// 数据层：组装静态数据、权限、服务端业务数据缓存、检索
(function () {
  const LS_DB = "sizheng-db-v4";
  const LS_USER = "sizheng-user";
  const LS_TOKEN = "sizheng-token";

  const S = { db: null, userId: null, flags: {}, token: localStorage.getItem(LS_TOKEN) || "" };

  // ------------------------------------------------------------ 组装
  // 案例/批注/版本/审核留痕/收藏/点赞的权威在服务端 SQLite（db.py），
  // db.cases/db.reviews/db.favorites 只是登录后从服务端拉取的本地缓存；
  // 素材登记同样在服务端（materials 表，/api/materials），db.materials 是其本地缓存；
  // localStorage 只保留纯前端偏好（模板改动、公告、备课材料等）
  function buildBase() {
    const R = window.RAWDATA, D = window.SEED;
    const db = {
      users: JSON.parse(JSON.stringify(D.users)),
      caseTypes: JSON.parse(JSON.stringify(D.caseTypes)),
      knowledgeSources: JSON.parse(JSON.stringify(D.knowledgeSources)),
      whitelist: D.whitelist.slice(),
      reviews: [],
      favorites: {},
      matFavorites: [],
      announcements: [],
      prepMaterials: [],
      knowledge: R.knowledge,
      chapters: R.chapters,
      book: R.book,
      materials: [],
      cases: [],
      fileIndex: {},
    };

    // 教材是知识不是素材（见 db.bookFile，ADR 0011）
    db.bookFile = R.bookFile || null;
    return db;
  }

  function load() {
    const base = buildBase();
    try {
      const raw = localStorage.getItem(LS_DB);
      if (raw) {
        const saved = JSON.parse(raw);
        ["users", "caseTypes", "knowledgeSources", "whitelist", "announcements", "prepMaterials"].forEach((k) => {
          if (saved[k] != null) base[k] = saved[k];
        });
      }
    } catch (e) { console.warn("本地数据读取失败，使用初始数据", e); }
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

  // 服务端素材（/api/materials，权威在 SQLite）并入 db.materials；
  // 上传素材的全文缓存在 uploadTexts，用于补内容副本摘录
  function mergeMaterialExcerpts() {
    S.db.materials.forEach((m) => {
      if (m.excerpt || m.contentAvailable === false) return;
      const up = uploadTexts[m.id];
      if (up) m.excerpt = up.text.slice(0, 2000);
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
    const jobs = (S.db.materials || []).map(async (m) => {
      if (!m.uploaded || !m.fileId || m.contentAvailable === false) return;
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

  // 素材与文件索引同步：/api/materials（SQLite 权威，按身份过滤）+ /api/files（文件元信息）
  S.syncMaterials = async () => {
    try {
      const [fresp, mresp] = await Promise.all([
        S.apiFetch("/api/files"),
        S.apiFetch("/api/materials"),
      ]);
      const fd = await fresp.json();
      const md = await mresp.json();
      if (fd && fd.ok) S.db.fileIndex = fd.files || {};
      if (md && md.ok) {
        S.db.materials = md.materials || [];
        const got = await fetchUploadTexts();
        mergeMaterialExcerpts();
        if (got) rerenderIfReading();
      }
      return true;
    } catch (e) { /* 服务端不可用时保持本地数据 */ }
    return false;
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
      if (d && d.ok) await S.syncMaterials();
      return d;
    } catch (e) {
      return { ok: false, error: "上传请求失败（服务不可用）" };
    }
  };
  S.deleteMaterialFile = async (fileId) => {
    try {
      const resp = await S.apiFetch("/api/files/" + encodeURIComponent(fileId), { method: "DELETE" });
      const d = await resp.json();
      if (d && d.ok) await S.syncMaterials();
      return d;
    } catch (e) {
      return { ok: false, error: "删除请求失败（服务不可用）" };
    }
  };

  S.canSeeMaterial = (m) => S.me().admin ||
    (m.status !== "停用" && m.status !== "候选");
  S.canReadMaterial = (m) => !!m && m.contentAvailable !== false;
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
  S.citeTarget = (id) => {
    const knowledge = S.knowledgeById(id), material = S.materialById(id);
    return knowledge || (S.canReadMaterial(material) ? material : null);
  };

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
      if (f && f.ok) {
        S.db.favorites[S.userId] = f.caseIds || [];
        S.db.matFavorites = f.materialIds || [];
      }
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
        // OnlyOffice 管理正文时（_ooManaged）docx 为编辑真源，前端 blocks 可能滞后，
        // 不回写以免覆盖保存回调同步来的内容（服务端 update_case 对缺失键保持原值）
        const body = Object.assign({}, c);
        delete body._ooManaged;
        if (c._ooManaged) delete body.blocks;
        const d = await apiJSON("/api/cases/" + encodeURIComponent(c.id), {
          method: "PATCH", body: JSON.stringify(body),
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

  S.saveCaseNow = async (c, patch) => {
    try {
      const d = await apiJSON("/api/cases/" + encodeURIComponent(c.id), {
        method: "PATCH", body: JSON.stringify(patch || c),
      });
      if (!d || !d.ok) return apiFail(d, "保存");
      return replaceCase(d.case);
    } catch (e) { return apiFail(null, "保存"); }
  };

  S.addCaseAttachment = async (c, payload) => {
    try {
      const d = await apiJSON("/api/cases/" + encodeURIComponent(c.id) + "/attachments", {
        method: "POST", body: JSON.stringify(payload || {}),
      });
      if (!d || !d.ok) return apiFail(d, "添加附件");
      replaceCase(d.case);
      if (d.duplicate) d.attachment.duplicate = true;
      return d.attachment;
    } catch (e) { return apiFail(null, "添加附件"); }
  };

  S.deleteCaseAttachment = async (c, aid) => {
    try {
      const d = await apiJSON("/api/cases/" + encodeURIComponent(c.id) +
        "/attachments/" + encodeURIComponent(aid), { method: "DELETE" });
      if (!d || !d.ok) { apiFail(d, "删除附件"); return false; }
      replaceCase(d.case);
      return true;
    } catch (e) { apiFail(null, "删除附件"); return false; }
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
  S.reviewCase = (c, action, opinion, offlineFrom, reasonType) =>
    caseAction(c, "review", {
      action: action === "return" ? "reject" : action,
      reason: opinion || "", offlineFrom: offlineFrom || "", reasonType: reasonType || "",
    }, "审核操作");
  S.unhideCase = (c) => caseAction(c, "review", { action: "unhide" }, "恢复公开");

  // 结构化退回理由（与服务端 db.py REASON_TYPES 一致；reject/supplement 必选）
  S.reasonTypeNames = {
    fact_error: "事实错误", citation_unsupported: "引用不支持", forced_mapping: "牵强映射",
    over_praise: "过度拔高", wording: "表述不规范", other: "其他",
  };

  // AI 生成标识（WP4）：采纳 AI 内容后打标 origin=ai_assisted 并记录所用模型；
  // 随后的 Store.touch 会把 meta 同步到服务端
  S.markAiAssist = (c, model) => {
    const meta = c.meta = c.meta || {};
    if (meta.origin !== "ai") meta.origin = "ai_assisted";
    meta.modelVersions = meta.modelVersions || [];
    if (model && !meta.modelVersions.includes(model)) meta.modelVersions.push(model);
  };

  // 组织资产·被退回表达台账（admin）：reviews 留痕按 reasonType 聚合
  S.fetchReviewLedger = async () => {
    try {
      const d = await apiJSON("/api/admin/review-ledger");
      return d && d.ok ? d : null;
    } catch (e) { return null; }
  };

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
      if (d.docxVer) c.docxVer = d.docxVer; // 「解决」会移除 docx 批注并 bump：工作台据此重建 OO 编辑器
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
      if (d.docxVer) c.docxVer = d.docxVer; // 批注已注入 docx：工作台据此重建 OO 编辑器
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
      if (d.docxVer) c.docxVer = d.docxVer;
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

  // ------------------------------------------------------------ 素材治理（API-backed，权威在服务端）
  // 单条治理：admin 可改密级/状态/信源等级等；非 admin 仅「重新采集」刷新副本（服务端再校验）
  S.updateMaterial = async (id, patch) => {
    try {
      const d = await apiJSON("/api/materials/" + encodeURIComponent(id), {
        method: "PATCH", body: JSON.stringify(patch),
      });
      if (!d || !d.ok) { apiFail(d, "保存素材"); return false; }
      const m = S.db.materials.find((x) => x.id === id);
      if (m) Object.assign(m, d.material);
      else S.db.materials.unshift(d.material);
      return true;
    } catch (e) { apiFail(null, "保存素材"); return false; }
  };
  S.setMaterialTags = (id, tags) => S.updateMaterial(id, { tags });
  // 批量治理（admin）：调密级/停用恢复/豁免淘汰/确认候选入库
  S.batchUpdateMaterials = async (ids, patch) => {
    try {
      const d = await apiJSON("/api/materials", {
        method: "PATCH", body: JSON.stringify({ ids, patch }),
      });
      if (!d || !d.ok) { apiFail(d, "批量操作"); return false; }
      (d.materials || []).forEach((fresh) => {
        const m = S.db.materials.find((x) => x.id === fresh.id);
        if (m) Object.assign(m, fresh);
      });
      return true;
    } catch (e) { apiFail(null, "批量操作"); return false; }
  };
  // 来源健康检查（admin）：失败的素材服务端标「来源失效」，返回汇总
  S.materialHealthCheck = async (ids) => {
    try {
      const d = await apiJSON("/api/admin/materials/healthcheck", {
        method: "POST", body: JSON.stringify(ids && ids.length ? { ids } : {}),
      });
      if (!d || !d.ok) { apiFail(d, "健康检查"); return null; }
      await S.syncMaterials();
      return d;
    } catch (e) { apiFail(null, "健康检查"); return null; }
  };
  // 采集入库（入库闸）：服务端做必填校验 + URL 查重 + 相似度查重；
  // 新素材一律先落「候选」，admin 确认后才进检索语料。force=true 跳过相似度闸。
  S.addMaterial = async (m, force) => {
    try {
      const d = await apiJSON("/api/materials", {
        method: "POST", body: JSON.stringify(Object.assign({}, m, force ? { force: true } : {})),
      });
      if (d && d.ok) {
        S.db.materials.unshift(d.material);
        return { ok: true, material: d.material };
      }
      return { ok: false, error: (d && d.error) || "采集失败", code: d && d.code, similar: d && d.similar };
    } catch (e) {
      return { ok: false, error: "采集请求失败（服务不可用）" };
    }
  };
  // 上下文推荐（工作台资料页签无输入默认）与最近引用（个人层）
  S.recommendedMaterials = async (caseId) => {
    try {
      const d = await apiJSON("/api/materials?recommendFor=" + encodeURIComponent(caseId));
      return d && d.ok ? d.materials || [] : [];
    } catch (e) { return []; }
  };
  S.recentCitedMaterials = async () => {
    try {
      const d = await apiJSON("/api/materials?recentCitedBy=" + encodeURIComponent(S.userId));
      return d && d.ok ? d.materials || [] : [];
    } catch (e) { return []; }
  };
  // 管理台统计看板（admin 视角全量）
  S.materialStats = () => {
    const ms = S.db.materials;
    const gradeN = {};
    ms.forEach((m) => { const g = m.grade || "未定级"; gradeN[g] = (gradeN[g] || 0) + 1; });
    return {
      total: ms.length,
      candidate: ms.filter((m) => m.status === "候选").length,
      uncited: ms.filter((m) => !m.citedCount).length,
      dormant: ms.filter((m) => m.dormant).length,
      failed: ms.filter((m) => m.status === "来源失效").length,
      grades: gradeN,
    };
  };
  S.savePrefs = (prefs) => { S.me().prefs = prefs; persist(); };

  // 我的生成偏好（WP4b，服务端 user_prefs 表为权威；本地仅按账号缓存一份）
  let genPrefsCache = null; // {uid, prefs}
  S.fetchMyPrefs = async () => {
    if (genPrefsCache && genPrefsCache.uid === S.userId) return genPrefsCache.prefs;
    let prefs = {};
    try {
      const d = await apiJSON("/api/my/prefs");
      if (d && d.ok && d.prefs) prefs = d.prefs;
    } catch (e) { /* 服务不可用时按无偏好处理 */ }
    genPrefsCache = { uid: S.userId, prefs };
    return prefs;
  };
  S.saveMyPrefs = async (prefs) => {
    try {
      const d = await apiJSON("/api/my/prefs", { method: "PUT", body: JSON.stringify(prefs || {}) });
      if (!d || !d.ok) { apiFail(d, "保存偏好"); return null; }
      genPrefsCache = { uid: S.userId, prefs: d.prefs };
      return d.prefs;
    } catch (e) { apiFail(null, "保存偏好"); return null; }
  };

  // ------------------------------------------------------------ 盯源与众筹（WP5，权威在服务端）
  // 盯源（admin）：返回 {sources, items}；items 含各状态候选卡，页面前端按标题相似度分组
  S.fetchWatchItems = async () => {
    try {
      const d = await apiJSON("/api/admin/watch/items");
      return d && d.ok ? { sources: d.sources || [], items: d.items || [] } : null;
    } catch (e) { return null; }
  };
  S.addWatchSource = async (src) => {
    const d = await apiJSON("/api/admin/watch/sources", {
      method: "POST", body: JSON.stringify(src),
    }).catch(() => null);
    if (!d || !d.ok) { apiFail(d, "添加盯源"); return false; }
    return true;
  };
  S.updateWatchSource = async (id, patch) => {
    const d = await apiJSON("/api/admin/watch/sources/" + encodeURIComponent(id), {
      method: "PATCH", body: JSON.stringify(patch),
    }).catch(() => null);
    if (!d || !d.ok) { apiFail(d, "保存盯源"); return false; }
    return true;
  };
  S.delWatchSource = async (id) => {
    const d = await apiJSON("/api/admin/watch/sources/" + encodeURIComponent(id), {
      method: "DELETE",
    }).catch(() => null);
    if (!d || !d.ok) { apiFail(d, "删除盯源"); return false; }
    return true;
  };
  // 手动触发扫描：同步执行，返回 {added, results:[{name, ok, added, note}]}
  S.runWatch = async (sourceId) => {
    try {
      const d = await apiJSON("/api/admin/watch/run", {
        method: "POST", body: JSON.stringify(sourceId ? { sourceId } : {}),
      });
      if (!d || !d.ok) { apiFail(d, "扫描"); return null; }
      return d;
    } catch (e) { apiFail(null, "扫描"); return null; }
  };
  // 候选卡入库（走服务端同一入库闸，落素材「候选」）；忽略后不再出现在待审列表
  S.importWatchItem = async (id, grade) => {
    try {
      const d = await apiJSON("/api/admin/watch/items/" + encodeURIComponent(id) + "/import", {
        method: "POST", body: JSON.stringify({ grade }),
      });
      if (!d || !d.ok) { apiFail(d, "入库"); return false; }
      if (d.material) {
        const m = S.db.materials.find((x) => x.id === d.material.id);
        if (m) Object.assign(m, d.material);
        else S.db.materials.unshift(d.material);
      }
      return true;
    } catch (e) { apiFail(null, "入库"); return false; }
  };
  S.ignoreWatchItem = async (id) => {
    const d = await apiJSON("/api/admin/watch/items/" + encodeURIComponent(id), {
      method: "PATCH", body: JSON.stringify({ status: "已忽略" }),
    }).catch(() => null);
    if (!d || !d.ok) { apiFail(d, "忽略"); return false; }
    return true;
  };
  // 众筹贡献（先审后发）：link=素材链接、kn_link=知识点-素材关联；完整案例走「提交审核」
  S.addContribution = async (kind, payload) => {
    try {
      const d = await apiJSON("/api/contributions", {
        method: "POST", body: JSON.stringify({ kind, payload }),
      });
      if (d && d.ok) return { ok: true, contribution: d.contribution };
      return { ok: false, error: (d && d.error) || "提交失败" };
    } catch (e) {
      return { ok: false, error: "提交请求失败（服务不可用）" };
    }
  };
  S.fetchContributions = async () => {
    try {
      const d = await apiJSON("/api/contributions");
      return d && d.ok ? d.contributions || [] : [];
    } catch (e) { return []; }
  };
  S.reviewContribution = async (id, action) => {
    const d = await apiJSON("/api/contributions/" + encodeURIComponent(id) + "/review", {
      method: "POST", body: JSON.stringify({ action }),
    }).catch(() => null);
    if (!d || !d.ok) { apiFail(d, "审核贡献"); return null; }
    return d;
  };
  // 我的影响力：素材贡献被引次数 + 案例被收藏/被点赞聚合
  S.fetchMyImpact = async () => {
    try {
      const d = await apiJSON("/api/my/impact");
      return d && d.ok ? d : null;
    } catch (e) { return null; }
  };

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

  // 素材收藏（个人层）
  S.isFavMat = (m) => (S.db.matFavorites || []).includes(m.id);
  S.toggleFavMat = async (m) => {
    const on = !S.isFavMat(m);
    try {
      const d = await apiJSON("/api/materials/" + encodeURIComponent(m.id) + "/favorite", {
        method: on ? "POST" : "DELETE",
      });
      if (!d || !d.ok) { apiFail(d, "收藏"); return false; }
      S.db.matFavorites = d.materialIds;
      return true;
    } catch (e) { apiFail(null, "收藏"); return false; }
  };

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
  // 服务端在案例写入后统一重算素材 citedCount/lastCitedAt，本地防抖刷新素材缓存
  let matSyncTimer = null;
  function syncMaterialsSoon() {
    clearTimeout(matSyncTimer);
    matSyncTimer = setTimeout(() => { S.syncMaterials(); }, 800);
  }

  // 证据片段：quote（被引用句）在来源文本中命中时截取命中句前后文，否则取开头一段
  function pickSnippet(text, quote, width) {
    const flat = String(text || "").replace(/\s+/g, " ").trim();
    if (!flat) return "";
    const w = width || 160;
    const probe = String(quote || "").trim().slice(0, 20);
    if (probe) {
      const p = flat.indexOf(probe);
      if (p >= 0) return flat.slice(Math.max(0, p - 40), p + w).trim();
    }
    return flat.slice(0, w + 40).trim();
  }

  // 手工挂接时自动捕获 evidence（WP3）：kn 节用 fileSec 作切片锚点；素材优先用上传全文
  // （按 ADR 0010 切片定位 sec），没有全文时退化为内容副本 excerpt。best-effort，失败返回 null。
  S.buildEvidence = (target, quote) => {
    const kn = S.knowledgeById(target);
    if (kn) {
      return { materialId: kn.id, sec: kn.fileSec || "",
               snippet: pickSnippet(kn.text, quote), capturedAt: U.now() };
    }
    const m = S.db.materials.find((x) => x.id === target);
    if (!m) return null;
    const up = uploadTexts[m.id];
    if (up && up.text) {
      const probe = String(quote || "").trim().slice(0, 20);
      const chunks = U.chunkMd(up.text);
      const hit = probe && chunks.find((ck) => ck.text.includes(probe));
      if (hit) {
        return { materialId: m.id, sec: hit.path,
                 snippet: pickSnippet(hit.text, quote), capturedAt: U.now() };
      }
      return { materialId: m.id, sec: "",
               snippet: pickSnippet(up.text, quote), capturedAt: U.now() };
    }
    const snippet = pickSnippet(m.excerpt || m.summary, quote);
    return snippet ? { materialId: m.id, sec: "", snippet, capturedAt: U.now() } : null;
  };

  // citations[] 元素：{target, at, note, blockId?, quote?, evidence?}
  // quote = 被引用句原文片段（句内锚点/文本指纹）；evidence = {materialId, sec, snippet, capturedAt}
  S.cite = (c, targetId, opts) => {
    c.citations = c.citations || [];
    if (c.citations.some((r) => r.target === targetId)) return;
    if (!targetId.startsWith("kn-") && !S.citeTarget(targetId)) return false;
    opts = opts || {};
    const ref = { target: targetId, at: U.now() };
    if (opts.note) ref.note = opts.note;
    if (opts.blockId) ref.blockId = opts.blockId;
    if (opts.quote) ref.quote = String(opts.quote).slice(0, 120);
    const ev = opts.evidence || S.buildEvidence(targetId, ref.quote);
    if (ev) ref.evidence = ev;
    c.citations.push(ref);
    syncCaseSoon(c);
    if (!targetId.startsWith("kn-")) syncMaterialsSoon();
    return true;
  };
  S.uncite = (c, targetId) => {
    c.citations = (c.citations || []).filter((r) => r.target !== targetId);
    syncCaseSoon(c);
    if (!targetId.startsWith("kn-")) syncMaterialsSoon();
  };
  S.isCited = (c, targetId) => (c.citations || []).some((r) => r.target === targetId);

  // 来源健康（WP3）：引用目标是素材且已删除/停用/来源失效 → true（角标判定，按本地素材缓存实时判定）
  S.citeFailed = (ref) => {
    const target = typeof ref === "string" ? ref : (ref && ref.target);
    if (!target || target.indexOf("kn-") === 0) return false;
    if (!S.db.materials.length) return false; // 缓存未加载不误判
    const m = S.db.materials.find((x) => x.id === target);
    return !m || m.status === "停用" || m.status === "来源失效";
  };

  // ------------------------------------------------------------ 素材使用度与生命周期
  // 「被用」= 被案例正文引用；浏览不计入。citedCount/lastCitedAt/dormant 均由服务端维护（ADR 0003）
  S.materialUsage = (mid) => {
    const m = S.db.materials.find((x) => x.id === mid);
    return { count: (m && m.citedCount) || 0, lastAt: (m && m.lastCitedAt) || "" };
  };
  S.isDormant = (m) => !!m.dormant;
  // 时效提示：文档类（政策文件）发布超过 3 年
  S.isPolicyDated = (m) => {
    const y = parseInt(String(m.publishedAt || "").slice(0, 4), 10);
    return m.kind === "文档" && !!y && y <= new Date().getFullYear() - 3;
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
  // 教师提交前主动运行；未过项只显示在自检面板，不自动写入批注。
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
      { id: "ck-cite", name: "至少 1 个引用案例或附件标记",
        ok: !!(c.caseRefs || []).length || (c.attachments || []).some((a) =>
          blocks.some((b) => b.text.includes(`](attachment:${a.id})`))) },
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

  // 引用该私密/失效素材的案例（风险处理）
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
        kind: h.kind || "文档", status: "正常", tags: [],
        contentAvailable: h.contentAvailable !== false,
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
