// 页面：管理后台（审核、发布、素材、类型模板、账号权限、公告）
// 审核详情页 = 工作台只读模式（见 pages-workbench.js P.workbenchView）
window.Pages = window.Pages || {};
(function () {
  const P = window.Pages;
  const H = P.H;

  const TABS = [
    ["audit", "案例审核"], ["publish", "发布管理"], ["materials", "素材管理"],
    ["knowledge", "知识管理"], ["types", "类型与模板"], ["accounts", "账号权限"], ["ann", "公告管理"],
  ];

  P.admin = (tab, params) => {
    if (!Store.me().admin) return P.notFound("管理后台仅案例管理员可用");
    tab = tab || "audit";
    // 深链 ?q=标题：一次性灌入对应页签的筛选（手动改筛选不被 URL 回灌）
    if (params && params.q) {
      if (tab === "materials" && params.q !== matQApplied) { matFilter = params.q; matPage = 1; matQApplied = params.q; }
      if (tab === "publish" && params.q !== pubQApplied) { pubQ = params.q; pubQApplied = params.q; }
      if (tab === "audit" && params.q !== auditQApplied) { auditQ = params.q; auditQApplied = params.q; }
    }

    const bodies = {
      audit: auditTab, publish: publishTab, materials: materialsTab,
      knowledge: knowledgeTab, types: typesTab, accounts: accountsTab, ann: annTab,
    };
    return {
      html: `
      <div class="admin-tabs">
        ${TABS.map(([k, n]) => `<a href="#/admin/${k}" class="${tab === k ? "active" : ""}">${n}</a>`).join("")}
      </div>
      <div id="admin-body">${bodies[tab]()}</div>`,
      mount(el) {
        (mounts[tab] || (() => {}))(el);
      },
    };
  };

  // 表格搜索框（各页签复用；val 用于 ?q= 深链灌入后回显）
  const searchRow = (id, ph, val) => `
    <input class="text" id="${id}" placeholder="${U.esc(ph)}" style="max-width:240px" value="${U.esc(val || "")}">`;

  // ---------------------------------------------------------- 审核队列
  let auditQ = "", auditAuthor = "", auditSort = "newest", auditQApplied = null;
  function auditTab() {
    let queue = Store.db.cases.filter((c) => c.status === "pending" || c.status === "reviewing");
    const authors = Array.from(new Set(queue.map((c) => c.ownerId)));
    if (auditQ) queue = queue.filter((c) =>
      c.title.includes(auditQ) || (Store.userById(c.ownerId) || {}).name.includes(auditQ));
    if (auditAuthor) queue = queue.filter((c) => c.ownerId === auditAuthor);
    queue = queue.slice().sort((a, b) => auditSort === "newest"
      ? String(b.submittedAt || b.updatedAt).localeCompare(String(a.submittedAt || a.updatedAt))
      : String(a.submittedAt || a.updatedAt).localeCompare(String(b.submittedAt || b.updatedAt)));
    const done = Store.db.reviews.slice(0, 10);
    return `
    <div class="card">
      <div class="card-pad section-title" style="border-bottom:1px solid var(--line)">
        <span>待审队列（${queue.length}）</span>
        <span class="row" style="gap:8px">
          ${searchRow("audit-q", "搜索案例标题 / 作者", auditQ)}
          <select id="audit-author" class="text" style="max-width:140px">
            <option value="">全部作者</option>
            ${authors.map((u) => `<option value="${u}" ${auditAuthor === u ? "selected" : ""}>${U.esc(Store.userById(u).name)}</option>`).join("")}
          </select>
          <select id="audit-sort" class="text" style="max-width:130px">
            <option value="newest" ${auditSort === "newest" ? "selected" : ""}>最新提交优先</option>
            <option value="oldest" ${auditSort === "oldest" ? "selected" : ""}>最早提交优先</option>
          </select>
        </span>
      </div>
      ${queue.length ? `<table class="data">
        <tr><th>案例</th><th>作者</th><th>类型</th><th>轮次</th><th>完整度</th><th>提交时间</th><th>状态</th><th></th></tr>
        ${queue.map((c) => {
          const checks = Store.selfChecks(c);
          const passed = checks.filter((x) => x.ok).length;
          return `<tr>
          <td>${U.esc(c.title)}</td>
          <td>${U.esc(Store.userById(c.ownerId).name)}</td>
          <td>${U.esc(Store.typeName(c.typeId))}</td>
          <td>第 ${Math.max(1, Store.submitRound(c))} 轮</td>
          <td><span class="tag ${passed === checks.length ? "green" : passed >= checks.length - 2 ? "amber" : "red"}">${passed}/${checks.length}</span></td>
          <td>${U.esc(c.submittedAt || c.updatedAt)}</td>
          <td>${H.statusTag(c.status)}</td>
          <td><a class="btn sm" href="#/admin/review/${c.id}">审核</a></td>
        </tr>`;
        }).join("")}
      </table>` : H.empty(auditQ || auditAuthor ? "没有匹配的待审案例" : "队列已清空")}
    </div>
    ${done.length ? `<div class="card" style="margin-top:14px">
      <div class="card-pad section-title" style="border-bottom:1px solid var(--line)"><span>最近审核记录</span></div>
      <table class="data">
        <tr><th>时间</th><th>案例</th><th>结论</th><th>总评</th><th>线下意见来源</th></tr>
        ${done.map((r) => {
          const c = Store.db.cases.find((x) => x.id === r.caseId);
          return `<tr><td>${U.esc(r.at)}</td><td>${U.esc(c ? c.title : "（已删除）")}</td>
            <td>${{ approve: "通过", return: "退回", supplement: "要求补充", hide: "隐藏" }[r.action] || r.action}</td>
            <td>${U.esc(r.opinion || "—")}</td><td>${U.esc(r.offlineFrom || "—")}</td></tr>`;
        }).join("")}
      </table>
    </div>` : ""}`;
  }

  // ---------------------------------------------------------- 发布管理
  let pubQ = "", pubQApplied = null;
  function publishTab() {
    let list = Store.db.cases.filter((c) => c.status === "published" || c.status === "hidden");
    if (pubQ) list = list.filter((c) => c.title.includes(pubQ));
    const risky = Store.db.materials.filter((m) => m.status !== "正常" && m.status !== "停用");
    return `
    <div class="card">
      <div class="card-pad section-title" style="border-bottom:1px solid var(--line)">
        <span>已发布与已隐藏</span>${searchRow("pub-q", "搜索案例标题", pubQ)}
      </div>
      <table class="data">
        <tr><th>案例</th><th>类型</th><th>发布时间</th><th>点赞</th><th>状态</th><th></th></tr>
        ${list.map((c) => `<tr>
          <td><a href="#/case/${c.id}">${U.esc(c.title)}</a></td>
          <td>${U.esc(Store.typeName(c.typeId))}</td>
          <td>${U.esc(U.plainDate(c.publishedAt))}</td>
          <td>${c.likes || 0}</td>
          <td>${H.statusTag(c.status)}</td>
          <td>${c.status === "published"
            ? `<button class="btn sm plain" data-hide="${c.id}">暂时隐藏</button>`
            : `<button class="btn sm secondary" data-unhide="${c.id}">恢复发布</button>`}</td>
        </tr>`).join("") || `<tr><td colspan="6" class="muted">没有匹配的案例</td></tr>`}
      </table>
    </div>
    <div class="card" style="margin-top:14px">
      <div class="card-pad section-title" style="border-bottom:1px solid var(--line)"><span>风险处理（来源变更 / 失效）</span></div>
      ${risky.length ? `<table class="data">
        <tr><th>素材</th><th>状态</th><th>受影响案例</th><th></th></tr>
        ${risky.map((m) => {
          const affected = Store.affectedByMaterial(m.id);
          return `<tr>
            <td><a href="#/material/${m.id}">${U.esc(m.title)}</a></td>
            <td><span class="tag red">${U.esc(m.status)}</span></td>
            <td>${affected.length ? affected.map((c) => U.esc(c.title)).join("；") : "无"}</td>
            <td class="row">
              ${affected.map((c) => `<button class="btn sm plain" data-recheck="${c.id}:${m.id}">要求复核</button>`).join("")}
              <button class="btn sm secondary" data-normal="${m.id}">标记恢复正常</button>
            </td>
          </tr>`;
        }).join("")}
      </table>` : `<div class="card-pad muted small">当前没有状态异常的素材来源。</div>`}
    </div>`;
  }

  // ---------------------------------------------------------- 素材管理
  let matPage = 1, matFilter = "", matDormantOnly = false, matQApplied = null;
  const MAT_PAGE_SIZE = 15;

  function materialsTab() {
    let all = Store.db.materials.filter((m) =>
      !matFilter || m.title.includes(matFilter) || m.source.includes(matFilter));
    if (matDormantOnly) all = all.filter((m) => Store.isDormant(m));
    const pages = Math.max(1, Math.ceil(all.length / MAT_PAGE_SIZE));
    matPage = Math.min(matPage, pages);
    const ms = all.slice((matPage - 1) * MAT_PAGE_SIZE, matPage * MAT_PAGE_SIZE);
    return `
    <div class="card" style="margin-bottom:14px">
      <div class="card-pad section-title" style="border-bottom:1px solid var(--line)"><span>上传资料文件</span></div>
      <div class="card-pad">
        <div class="row wrap" style="margin-bottom:8px">
          <input class="text" id="up-title" placeholder="素材标题" style="max-width:260px">
          <select class="text" id="up-level" style="max-width:110px">
            <option value="0">公开</option>
            <option value="1" selected>校内</option>
            <option value="2">受限</option>
          </select>
          <input class="text" type="file" id="up-file" style="max-width:300px">
        </div>
        <label class="field"><span>简介（可选）</span><textarea class="text" id="up-summary" style="height:56px" placeholder="一句话说明资料内容与用途"></textarea></label>
        <div class="row" style="margin-top:8px">
          <button class="btn" id="up-submit">上传并入库</button>
          <span class="small muted">文件在服务端落盘、全员可见；限 20MB，md/txt 可在线预览。上传素材可删除，种子素材只能停用。</span>
        </div>
      </div>
    </div>
    <div class="card" style="margin-bottom:14px">
      <div class="card-pad section-title" style="border-bottom:1px solid var(--line)"><span>权威来源白名单</span></div>
      <div class="card-pad">
        <div class="row wrap" id="wl-box">
          ${Store.db.whitelist.map((d) => `<span class="tag green">${U.esc(d)} <a href="javascript:void 0" data-wl-del="${U.esc(d)}" style="color:inherit">×</a></span>`).join("")}
        </div>
        <div class="row" style="margin-top:8px">
          <input class="text" id="wl-add" placeholder="添加域名，如 people.com.cn" style="max-width:260px">
          <button class="btn sm" id="wl-add-btn">添加</button>
        </div>
      </div>
    </div>
    <div class="card">
      <div class="card-pad section-title" style="border-bottom:1px solid var(--line)">
        <span>素材分级与可信度（共 ${all.length} 条）</span>
        <span class="row" style="gap:8px">
          <label class="row small" style="gap:4px"><input type="checkbox" id="mat-dormant" ${matDormantOnly ? "checked" : ""} style="width:auto"> 只看待淘汰</label>
          <input class="text" id="mat-filter" placeholder="按标题或来源筛选" style="max-width:220px" value="${U.esc(matFilter)}">
        </span>
      </div>
      <table class="data">
        <tr><th>素材</th><th>来源</th><th>密级</th><th>可信度</th><th>被引</th><th>状态</th><th></th></tr>
        ${ms.map((m) => {
          const usage = Store.materialUsage(m.id);
          const dormant = Store.isDormant(m);
          return `<tr class="${dormant ? "row-dormant" : ""}">
          <td style="max-width:260px"><a href="#/material/${m.id}">${U.esc(m.title)}</a>
            ${m.fileId ? `<span class="tag green" title="已挂真实文件，可在线预览/下载">文件</span>` : ""}
            ${m.uploaded ? `<span class="tag blue" title="演示期间上传，记录存于服务端">上传</span>` : ""}
            ${dormant ? `<span class="tag amber" title="入库超过 30 天且从未被引用">待淘汰</span>` : ""}</td>
          <td>${U.esc(m.source)}</td>
          <td><select data-m-level="${m.id}">
            ${["公开", "校内", "受限"].map((n, i) => `<option value="${i}" ${m.level === i ? "selected" : ""}>${n}</option>`).join("")}
          </select></td>
          <td><select data-m-cred="${m.id}">
            <option value="high" ${m.credibility === "high" ? "selected" : ""}>权威来源</option>
            <option value="normal" ${m.credibility === "normal" ? "selected" : ""}>一般来源</option>
            <option value="low" ${m.credibility === "low" ? "selected" : ""}>待核实</option>
          </select></td>
          <td title="${usage.lastAt ? "最近被引 " + U.esc(usage.lastAt) : "从未被引用"}">${usage.count}</td>
          <td><select data-m-status="${m.id}">
            ${["正常", "来源失效", "停用"].map((s) => `<option ${m.status === s ? "selected" : ""}>${s}</option>`).join("")}
          </select></td>
          <td class="row">
            <button class="btn sm" data-m-save="${m.id}" title="保存本行的密级/可信度/状态修改">保存</button>
            ${dormant ? `<button class="btn sm plain" data-m-retire="${m.id}" title="确认淘汰：状态置为停用">淘汰</button>` : ""}
            ${m.uploaded ? `<button class="btn sm danger" data-m-del="${U.esc(m.fileId)}" title="删除该上传素材：文件从服务器移除，所有人不可再访问">删除</button>` : ""}
          </td>
        </tr>`;
        }).join("")}
      </table>
      ${pages > 1 ? `<div class="pager">
        <button data-mat-page="${matPage - 1}" ${matPage <= 1 ? "disabled" : ""}>上一页</button>
        <span class="pager-dots">${matPage} / ${pages}</span>
        <button data-mat-page="${matPage + 1}" ${matPage >= pages ? "disabled" : ""}>下一页</button>
      </div>` : ""}
    </div>`;
  }

  // ---------------------------------------------------------- 知识管理（ADR 0011）
  function knowledgeTab() {
    const srcs = Store.db.knowledgeSources;
    const bf = Store.db.bookFile;
    return `
    ${bf ? `<div class="card" style="margin-bottom:14px">
      <div class="card-pad section-title" style="border-bottom:1px solid var(--line)"><span>教材文件</span></div>
      <div class="card-pad">
        <div class="row spread">
          <span class="small">${U.esc(bf.title)} · ${U.esc((Store.fileInfo(bf.fileId) || {}).name || "教材原始文件")} · 已导入 ${Store.db.book.chapters} 章 ${Store.db.knowledge.length} 节</span>
          <span class="row">
            <a class="btn sm plain" href="#/book">查看教材主页</a>
            <button class="btn sm" id="kb-download">下载文件</button>
          </span>
        </div>
        <div class="small muted" style="margin-top:8px">更换教材（构建期知识源）仍走原流程：替换 assets/ 中的教材文件后运行 tools/build_data.py 并重新部署（ADR 0010）。新增专题知识源无需重新部署，用下方「导入新知识源」在线导入即可。</div>
      </div>
    </div>` : ""}
    <div class="card" style="margin-bottom:14px">
      <div class="card-pad section-title" style="border-bottom:1px solid var(--line)"><span>导入新知识源</span></div>
      <div class="card-pad">
        <div class="row wrap" style="margin-bottom:8px">
          <input class="text" id="ki-name" placeholder="来源名称，如：科学家精神专题" style="max-width:220px">
          <input class="text" id="ki-source" placeholder="来源说明或链接（可选）" style="max-width:280px">
          <input class="text" type="file" id="ki-file" accept=".md,.markdown,.txt" style="max-width:280px">
          <button class="btn" id="ki-submit">导入</button>
        </div>
        <div class="small muted">markdown 按 # 章 / ### 节解析为知识节，导入后全员可检索、可在案例正文引用；同名来源再次导入会整体覆盖。</div>
      </div>
    </div>
    <div class="card">
      <div class="card-pad section-title" style="border-bottom:1px solid var(--line)"><span>知识来源登记（共 ${srcs.length} 个）</span></div>
      <table class="data">
        <tr><th>名称</th><th>版本</th><th>更新</th><th>条目数</th><th>状态</th><th></th></tr>
        ${srcs.map((s) => {
          const firstKn = s.runtime && Store.db.knowledge.find((k) => k.runtimeSrc === s.id);
          return `<tr>
          <td>${U.esc(s.name)}${s.runtime ? ` <span class="tag blue" title="演示期间在线导入，记录存于服务端">运行时导入</span>` : ""}</td>
          <td>${U.esc(s.version)}</td>
          <td>${U.esc(s.updatedAt)}</td>
          <td>${s.id === "ks-zr" ? Store.db.knowledge.filter((k) => !k.runtimeSrc).length : s.entries}</td>
          <td>${s.status === "已导入" ? `<span class="tag green">已导入</span>` : `<span class="tag">${U.esc(s.status)}</span>`}</td>
          <td>${s.id === "ks-zr" ? `<a class="btn sm plain" href="#/book">查看</a>`
            : firstKn ? `<a class="btn sm plain" href="#/knowledge/${firstKn.id}">查看</a>`
            : `<span class="small muted">待导入</span>`}</td>
        </tr>`;
        }).join("")}
      </table>
    </div>`;
  }

  // ---------------------------------------------------------- 类型与模板
  function typesTab() {
    return `
    ${Store.db.caseTypes.map((t) => `
    <div class="card" style="margin-bottom:14px">
      <div class="card-pad section-title" style="border-bottom:1px solid var(--line)">
        <span>${U.esc(t.name)}</span>
        ${t.id !== "ct-general" ? `<button class="btn sm plain" data-type-del="${t.id}">删除类型</button>` : ""}
      </div>
      <table class="data">
        <tr><th>模板</th><th>用途</th><th>适用学段</th><th>章节结构</th><th></th></tr>
        ${t.templates.map((tp) => `<tr>
          <td>${U.esc(tp.name)}</td>
          <td><span class="tag primary">${U.esc(tp.purpose || "日常授课")}</span></td>
          <td>${tp.stages.map((s) => Store.audienceName(s)).join("、")}</td>
          <td class="small">${tp.sections.map(U.esc).join(" / ")}</td>
          <td class="row">
            <button class="btn sm plain" data-tp-edit="${t.id}:${tp.id}">编辑</button>
            <button class="btn sm plain" data-tp-del="${t.id}:${tp.id}">删除</button>
          </td>
        </tr>`).join("")}
      </table>
      <div class="card-pad row wrap" style="border-top:1px solid var(--line)">
        <input class="text" data-tp-name="${t.id}" placeholder="新模板名称" style="max-width:140px">
        <select data-tp-purpose="${t.id}">
          ${window.SEED.purposes.map((p) => `<option>${p}</option>`).join("")}
        </select>
        ${["grad", "ug", "embed"].map((s) => `<label class="row small" style="gap:4px"><input type="checkbox" data-tp-stage="${t.id}:${s}" style="width:auto"> ${Store.audienceName(s)}</label>`).join("")}
        <input class="text" data-tp-secs="${t.id}" placeholder="章节结构，用 / 分隔" style="max-width:300px">
        <button class="btn sm" data-tp-add="${t.id}">添加模板</button>
      </div>
    </div>`).join("")}
    <div class="card card-pad row">
      <input class="text" id="type-name" placeholder="新案例类型名称" style="max-width:220px">
      <button class="btn" id="type-add">添加类型</button>
    </div>`;
  }

  function tplEditModal(tid, tpid) {
    const t = Store.typeById(tid);
    const tp = t && t.templates.find((x) => x.id === tpid);
    if (!tp) return;
    const close = U.modal(`
    <div class="modal-head"><b>编辑模板</b><button class="modal-close" data-close>×</button></div>
    <div class="modal-body">
      <label class="field"><span>模板名称</span><input class="text" id="te-name" value="${U.esc(tp.name)}"></label>
      <label class="field"><span>用途</span>
        <select class="text" id="te-purpose">
          ${window.SEED.purposes.map((p) => `<option ${tp.purpose === p ? "selected" : ""}>${p}</option>`).join("")}
        </select></label>
      <label class="field"><span>适用学段</span>
        <div class="row wrap">
          ${["grad", "ug", "embed"].map((s) => `<label class="row small" style="gap:4px"><input type="checkbox" data-te-stage="${s}" ${tp.stages.includes(s) ? "checked" : ""} style="width:auto"> ${Store.audienceName(s)}</label>`).join("")}
        </div></label>
      <label class="field"><span>章节结构（用 / 分隔）</span>
        <input class="text" id="te-secs" value="${U.esc(tp.sections.join(" / "))}"></label>
    </div>
    <div class="modal-foot">
      <button class="btn plain" data-close>取消</button>
      <button class="btn" id="te-save">保存</button>
    </div>`, { sticky: true });
    U.$("#te-save").addEventListener("click", () => {
      const name = U.$("#te-name").value.trim();
      const secs = U.$("#te-secs").value.split("/").map((s) => s.trim()).filter(Boolean);
      const stages = ["grad", "ug", "embed"].filter((s) => U.$(`[data-te-stage="${s}"]`).checked);
      if (!name || !secs.length || !stages.length) { U.toast("名称、学段、章节结构都不能为空"); return; }
      Store.updateTemplate(tid, tpid, { name, purpose: U.$("#te-purpose").value, stages, sections: secs });
      close();
      U.toast("模板已保存");
      P.rerender();
    });
  }

  // ---------------------------------------------------------- 账号权限
  function accountsTab() {
    return `
    <div class="card">
      <div class="card-pad section-title" style="border-bottom:1px solid var(--line)"><span>账号与素材使用范围</span></div>
      <table class="data">
        <tr><th>姓名</th><th>角色</th><th>单位</th><th>任课课程</th><th>素材范围上限</th><th></th></tr>
        ${Store.db.users.map((u) => `<tr>
          <td>${U.esc(u.name)}${u.admin ? " <span class='tag amber'>管理员</span>" : ""}</td>
          <td>${U.esc(u.role)}</td>
          <td>${U.esc(u.org)}</td>
          <td class="small">${(u.courses || []).map(U.esc).join("、") || "—"}</td>
          <td><select data-u-level="${u.id}">
            ${["公开", "校内", "受限"].map((n, i) => `<option value="${i}" ${u.maxLevel === i ? "selected" : ""}>${n}</option>`).join("")}
          </select></td>
          <td><button class="btn sm" data-u-save="${u.id}">保存</button></td>
        </tr>`).join("")}
      </table>
    </div>
    <div class="card card-pad" style="margin-top:14px">
      <div class="row spread">
        <span class="small muted">演示期间产生的新案例、批注、审核记录保存在本机浏览器中。</span>
        <button class="btn danger sm" id="reset-all">重置全部数据</button>
      </div>
    </div>`;
  }

  // ---------------------------------------------------------- 公告管理
  function annTab() {
    const list = Store.db.announcements;
    return `
    <div class="card" style="margin-bottom:14px">
      <div class="card-pad section-title" style="border-bottom:1px solid var(--line)"><span>发布公告</span></div>
      <div class="card-pad">
        <label class="field"><span>标题</span><input class="text" id="ann-title" placeholder="如：期末案例集中审核安排"></label>
        <label class="field"><span>内容</span><textarea class="text" id="ann-text" style="height:80px" placeholder="公告正文，教师在首页可见"></textarea></label>
        <button class="btn" id="ann-add">发布</button>
      </div>
    </div>
    <div class="card">
      <div class="card-pad section-title" style="border-bottom:1px solid var(--line)"><span>公告列表（${list.length}）</span></div>
      ${list.length ? `<table class="data">
        <tr><th>标题</th><th>内容</th><th>发布时间</th><th>状态</th><th></th></tr>
        ${list.map((a) => `<tr>
          <td>${U.esc(a.title)}</td>
          <td class="small" style="max-width:320px">${U.esc(a.text)}</td>
          <td>${U.esc(a.at)}</td>
          <td>${a.online ? `<span class="tag green">展示中</span>` : `<span class="tag">已下线</span>`}</td>
          <td><button class="btn sm ${a.online ? "plain" : "secondary"}" data-ann-toggle="${a.id}">${a.online ? "下线" : "重新上线"}</button></td>
        </tr>`).join("")}
      </table>` : H.empty("还没有公告")}
    </div>`;
  }

  // ---------------------------------------------------------- 各页签事件
  const mounts = {
    audit(el) {
      U.$("#audit-q", el).addEventListener("input", U.debounce((e) => {
        auditQ = e.target.value.trim();
        P.rerender();
      }, 300));
      U.$("#audit-author", el).addEventListener("change", (e) => { auditAuthor = e.target.value; P.rerender(); });
      U.$("#audit-sort", el).addEventListener("change", (e) => { auditSort = e.target.value; P.rerender(); });
    },
    publish(el) {
      U.$("#pub-q", el).addEventListener("input", U.debounce((e) => {
        pubQ = e.target.value.trim();
        P.rerender();
      }, 300));
      U.$$("[data-hide]", el).forEach((b) => b.addEventListener("click", async () => {
        const c = Store.db.cases.find((x) => x.id === b.dataset.hide);
        if (c && await U.confirmModal("隐藏后公共检索与详情页将不再展示该案例，确认？")) {
          Store.reviewCase(c, "hide", "管理员暂时隐藏", "");
          P.rerender();
        }
      }));
      U.$$("[data-unhide]", el).forEach((b) => b.addEventListener("click", () => {
        const c = Store.db.cases.find((x) => x.id === b.dataset.unhide);
        if (c) { Store.unhideCase(c); P.rerender(); }
      }));
      U.$$("[data-recheck]", el).forEach((b) => b.addEventListener("click", () => {
        const [cid, mid] = b.dataset.recheck.split(":");
        const c = Store.db.cases.find((x) => x.id === cid);
        const m = Store.db.materials.find((x) => x.id === mid);
        if (c && m) {
          Store.addAnnotation(c, {
            kind: "admin", status: "pending", section: 0, quote: "",
            text: `引用来源「${m.title}」状态为${m.status}，请复核相关引用，必要时替换素材或暂时撤回。`,
            author: Store.me().name, lowRisk: false,
          });
          U.toast("已向案例作者发出复核要求");
        }
      }));
      U.$$("[data-normal]", el).forEach((b) => b.addEventListener("click", () => {
        Store.updateMaterial(b.dataset.normal, { status: "正常" });
        P.rerender();
      }));
    },
    materials(el) {
      U.$("#mat-filter", el).addEventListener("input", U.debounce((e) => {
        matFilter = e.target.value.trim();
        matPage = 1;
        P.rerender();
      }, 300));
      U.$("#mat-dormant", el).addEventListener("change", (e) => {
        matDormantOnly = e.target.checked;
        matPage = 1;
        P.rerender();
      });
      U.$$("[data-mat-page]", el).forEach((b) => b.addEventListener("click", () => {
        matPage = Number(b.dataset.matPage);
        P.rerender();
      }));
      // 上传资料文件：服务端落盘、全员可见（仅 admin 页面可达，服务端再校验一次）
      const upBtn = U.$("#up-submit", el);
      if (upBtn) upBtn.addEventListener("click", async () => {
        const title = U.$("#up-title", el).value.trim();
        const file = U.$("#up-file", el).files[0];
        if (!title) { U.toast("请填写素材标题"); return; }
        if (!file) { U.toast("请选择要上传的文件"); return; }
        if (file.size > 20 * 1024 * 1024) { U.toast("文件超过 20MB 上限"); return; }
        upBtn.disabled = true;
        upBtn.textContent = "上传中…";
        try {
          const dataBase64 = await new Promise((resolve, reject) => {
            const r = new FileReader();
            r.onload = () => resolve(String(r.result).split(",")[1] || "");
            r.onerror = () => reject(new Error("read failed"));
            r.readAsDataURL(file);
          });
          const res = await Store.uploadMaterialFile({
            title: title,
            level: Number(U.$("#up-level", el).value),
            summary: U.$("#up-summary", el).value.trim(),
            filename: file.name,
            dataBase64: dataBase64,
          });
          if (res && res.ok) { U.toast("已上传入库，全员可见"); P.rerender(); }
          else U.toast((res && res.error) || "上传失败", 3000);
        } catch (err) {
          U.toast("文件读取失败", 3000);
        } finally {
          upBtn.disabled = false;
          upBtn.textContent = "上传并入库";
        }
      });
      U.$$("[data-m-del]", el).forEach((b) => b.addEventListener("click", async () => {
        if (await U.confirmModal("确认删除该上传素材？文件将从服务器移除，所有人不可再访问。", { danger: true })) {
          const res = await Store.deleteMaterialFile(b.dataset.mDel);
          if (res && res.ok) { U.toast("已删除"); P.rerender(); }
          else U.toast((res && res.error) || "删除失败", 3000);
        }
      }));
      U.$$("[data-m-save]", el).forEach((b) => b.addEventListener("click", () => {
        const id = b.dataset.mSave;
        Store.updateMaterial(id, {
          level: Number(U.$(`[data-m-level="${id}"]`, el).value),
          credibility: U.$(`[data-m-cred="${id}"]`, el).value,
          status: U.$(`[data-m-status="${id}"]`, el).value,
        });
        U.toast("已保存");
      }));
      U.$$("[data-m-retire]", el).forEach((b) => b.addEventListener("click", async () => {
        const m = Store.db.materials.find((x) => x.id === b.dataset.mRetire);
        if (m && await U.confirmModal(`确认淘汰「${m.title}」？状态将置为停用，检索与详情页不再展示。`)) {
          Store.updateMaterial(m.id, { status: "停用" });
          U.toast("已淘汰（停用）");
          P.rerender();
        }
      }));
      U.$$("[data-wl-del]", el).forEach((b) => b.addEventListener("click", () => {
        Store.db.whitelist = Store.db.whitelist.filter((d) => d !== b.dataset.wlDel);
        Store.saveCase(); P.rerender();
      }));
      U.$("#wl-add-btn", el).addEventListener("click", () => {
        const v = U.$("#wl-add", el).value.trim();
        if (v && !Store.db.whitelist.includes(v)) {
          Store.db.whitelist.push(v);
          Store.saveCase(); P.rerender();
        }
      });
    },
    knowledge(el) {
      const dl = U.$("#kb-download", el);
      if (dl) dl.addEventListener("click", async () => {
        const bf = Store.db.bookFile;
        if (!bf) return;
        dl.disabled = true;
        try {
          const resp = await Store.apiFetch("/api/files/" + encodeURIComponent(bf.fileId));
          if (!resp.ok) { U.toast("下载失败", 3000); return; }
          const blob = await resp.blob();
          U.download((Store.fileInfo(bf.fileId) || {}).name || (bf.title + ".md"), blob);
        } finally { dl.disabled = false; }
      });
      // 导入新知识源：FileReader 读 markdown 文本 → POST /api/knowledge/import（admin token 由 apiFetch 带）
      const kiBtn = U.$("#ki-submit", el);
      if (kiBtn) kiBtn.addEventListener("click", async () => {
        const name = U.$("#ki-name", el).value.trim();
        const file = U.$("#ki-file", el).files[0];
        if (!name) { U.toast("请填写来源名称"); return; }
        if (!file) { U.toast("请选择 markdown 文件"); return; }
        if (!/\.(md|markdown|txt)$/i.test(file.name)) { U.toast("仅支持 .md / .markdown / .txt 文件"); return; }
        kiBtn.disabled = true;
        kiBtn.textContent = "导入中…";
        try {
          const markdown = await new Promise((resolve, reject) => {
            const r = new FileReader();
            r.onload = () => resolve(String(r.result || ""));
            r.onerror = () => reject(new Error("read failed"));
            r.readAsText(file);
          });
          const resp = await Store.apiFetch("/api/knowledge/import", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ name, source: U.$("#ki-source", el).value.trim(), markdown }),
          });
          const d = await resp.json();
          if (d && d.ok) {
            await Store.syncKnowledge(); // 合并新来源并重建检索语料
            U.toast(`已导入「${name}」：${d.chapters} 章 ${d.sections} 节`);
            P.rerender();
          } else U.toast((d && d.error) || "导入失败", 3000);
        } catch (err) {
          U.toast("文件读取或导入请求失败", 3000);
        } finally {
          kiBtn.disabled = false;
          kiBtn.textContent = "导入";
        }
      });
    },
    types(el) {
      U.$$("[data-tp-edit]", el).forEach((b) => b.addEventListener("click", () => {
        const [tid, tpid] = b.dataset.tpEdit.split(":");
        tplEditModal(tid, tpid);
      }));
      U.$$("[data-tp-add]", el).forEach((b) => b.addEventListener("click", () => {
        const t = Store.typeById(b.dataset.tpAdd);
        const name = U.$(`[data-tp-name="${t.id}"]`, el).value.trim();
        const purpose = U.$(`[data-tp-purpose="${t.id}"]`, el).value;
        const secs = U.$(`[data-tp-secs="${t.id}"]`, el).value.split("/").map((s) => s.trim()).filter(Boolean);
        const stages = ["grad", "ug", "embed"].filter((s) => U.$(`[data-tp-stage="${t.id}:${s}"]`, el).checked);
        if (!name || !secs.length || !stages.length) { U.toast("请填写模板名称、适用学段和章节结构"); return; }
        t.templates.push({ id: U.uid("tp"), name, purpose, stages, sections: secs });
        Store.saveCase(); P.rerender();
      }));
      U.$$("[data-tp-del]", el).forEach((b) => b.addEventListener("click", async () => {
        const [tid, tpid] = b.dataset.tpDel.split(":");
        const t = Store.typeById(tid);
        if (t && await U.confirmModal("删除该模板？", { danger: true })) {
          t.templates = t.templates.filter((x) => x.id !== tpid);
          Store.saveCase(); P.rerender();
        }
      }));
      U.$$("[data-type-del]", el).forEach((b) => b.addEventListener("click", async () => {
        if (await U.confirmModal("删除该类型？已有案例将归入通用案例。", { danger: true })) {
          Store.db.cases.forEach((c) => { if (c.typeId === b.dataset.typeDel) c.typeId = "ct-general"; });
          Store.db.caseTypes = Store.db.caseTypes.filter((t) => t.id !== b.dataset.typeDel);
          Store.saveCase(); P.rerender();
        }
      }));
      U.$("#type-add", el).addEventListener("click", () => {
        const name = U.$("#type-name", el).value.trim();
        if (!name) return;
        Store.db.caseTypes.push({
          id: U.uid("ct"), name,
          templates: [{ id: U.uid("tp"), name: "标准模板", purpose: "日常授课", stages: ["ug", "grad"], sections: ["案例背景", "案例正文", "分析讨论", "总结启示"] }],
        });
        Store.saveCase(); P.rerender();
      });
    },
    accounts(el) {
      U.$$("[data-u-save]", el).forEach((b) => b.addEventListener("click", () => {
        const u = Store.userById(b.dataset.uSave);
        if (u) {
          u.maxLevel = Number(U.$(`[data-u-level="${u.id}"]`, el).value);
          Store.saveCase(); U.toast("已保存");
        }
      }));
      U.$("#reset-all", el).addEventListener("click", async () => {
        if (await U.confirmModal("重置后将清空本机浏览器中的全部改动，恢复初始数据。确认？", { danger: true })) {
          Store.resetAll();
          location.hash = "#/home";
          location.reload();
        }
      });
    },
    ann(el) {
      U.$("#ann-add", el).addEventListener("click", () => {
        const title = U.$("#ann-title", el).value.trim();
        const text = U.$("#ann-text", el).value.trim();
        if (!title || !text) { U.toast("请填写标题和内容"); return; }
        Store.addAnnouncement({ title, text });
        U.toast("公告已发布，首页可见");
        P.rerender();
      });
      U.$$("[data-ann-toggle]", el).forEach((b) => b.addEventListener("click", () => {
        const a = Store.db.announcements.find((x) => x.id === b.dataset.annToggle);
        if (a) {
          Store.setAnnouncement(a.id, { online: !a.online });
          P.rerender();
        }
      }));
    },
  };

  // ---------------------------------------------------------- 审核详情 = 工作台只读模式（ADR 0001）
  P.reviewDetail = (id) => {
    if (!Store.me().admin) return P.notFound("管理后台仅案例管理员可用");
    return P.workbenchView(id, { mode: "review" });
  };
})();
