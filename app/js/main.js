// 入口：导航、路由
(function () {
  const P = window.Pages;
  let current = null;

  function parseHash() {
    const h = location.hash.replace(/^#\/?/, "");
    const [pathPart, queryPart] = h.split("?");
    const parts = pathPart.split("/").filter(Boolean);
    const params = {};
    if (queryPart) queryPart.split("&").forEach((kv) => {
      const [k, v] = kv.split("=");
      params[decodeURIComponent(k)] = decodeURIComponent(v || "");
    });
    return { parts, params };
  }

  function route() {
    const { parts, params } = parseHash();
    const page = parts[0] || "home";
    let view;
    if (page === "home") view = P.home();
    else if (page === "mine") view = P.myCases();
    else if (page === "new") view = P.newCase(params);
    else if (page === "workbench" && parts[1]) view = P.workbench(parts[1]);
    else if (page === "search") view = P.search(params);
    else if (page === "graph") { location.hash = "#/search?view=graph"; return; }
    else if (page === "case" && parts[1]) view = P.caseDetail(parts[1]);
    else if (page === "material" && parts[1]) view = P.materialDetail(parts[1], params);
    else if (page === "book") view = P.bookPage(params);
    else if (page === "knowledge" && parts[1]) view = P.knowledgeDetail(parts[1]);
    else if (page === "admin" && parts[1] === "review" && parts[2]) view = P.reviewDetail(parts[2]);
    else if (page === "admin") view = P.admin(parts[1], params);
    else view = P.notFound();

    if (current && current.unmount) current.unmount();
    current = view;
    // 每次路由更换 #view 节点，清除上一轮挂载的事件监听
    const old = U.$("#view");
    const el = old.cloneNode(false);
    old.parentNode.replaceChild(el, old);
    el.innerHTML = view.html;
    if (view.mount) view.mount(el);
    window.scrollTo(0, 0);

    U.$$("#mainnav a").forEach((a) => {
      a.classList.toggle("active", a.dataset.nav === page ||
        (page === "admin" && a.dataset.nav === "admin"));
    });
  }

  P.rerender = route;

  function initAccount() {
    const sel = U.$("#user-switch");
    const draw = () => {
      sel.innerHTML = Store.db.users.map((u) =>
        `<option value="${u.id}" ${u.id === Store.userId ? "selected" : ""}>${U.esc(u.name)} · ${U.esc(u.role)}</option>`).join("");
      U.$("#nav-admin").hidden = !Store.me().admin;
      // 待办红点（ADR 0002）
      const badge = U.$("#mine-badge");
      if (badge) {
        const t = Store.todos();
        const n = t.returned.length + t.pendingAnnos + (t.reviewQueue || []).length;
        badge.hidden = n === 0;
        badge.textContent = n > 99 ? "99+" : String(n);
      }
    };
    draw();
    sel.addEventListener("change", async () => {
      Store.setUser(sel.value);
      await Store.login(sel.value);
      await Store.syncServerMaterials();
      await Store.syncCases();
      draw();
      route();
      U.toast("已切换到 " + Store.me().name);
    });
    U.$("#prefs-btn").addEventListener("click", P.prefsModal);
    P.refreshBadge = draw;
  }

  window.addEventListener("hashchange", route);
  fetch("/api/constants")
    .then((r) => r.json())
    .then((d) => { Store.flags = d; })
    .catch(() => { Store.flags = {}; })
    .then(() => Store.login(Store.userId))
    .then(() => Store.syncServerMaterials())
    .then(() => Store.syncCases())
    .finally(() => {
      initAccount();
      if (!location.hash) location.hash = "#/home";
      route();
    });
})();
