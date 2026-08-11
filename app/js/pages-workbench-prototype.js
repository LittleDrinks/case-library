// PROTOTYPE: selected Canvas workbench with floating outline and unified research rail.
window.Pages = window.Pages || {};
(function () {
  const P = window.Pages;
  const E = U.esc;
  const TOOLS = [
    ["ai", "✦", "AI"], ["comments", "▤", "批注"], ["files", "▱", "附件"],
  ];
  const AI_TOOLS = [
    ["find-theory", "⌕", "理论", "查找能支撑当前段落的理论依据"],
    ["find-material", "▦", "平台", "检索平台案例、知识和案例附件"],
    ["web", "↗", "联网", "请使用 web_search 工具查找相关互联网公开资源"],
    ["fetch-url", "↓", "网页", "请使用 fetch_url 工具采集这个网页："],
    ["polish", "¶", "润色", "润色当前段落，保持原意并提升书面表达"],
    ["adapt", "◫", "教学版", "改写为适合当前教学对象的课堂教学版本"],
    ["review", "✓", "审校", "检查当前段落的理论、事实、引用和语言问题"],
  ];
  const ATTACHMENT_LINK = String.raw`\[((?:\\.|[^\]\\\n])*)\]\(attachment:(att-[A-Za-z0-9-]+)\)`;
  const KIND_LABEL = { author: "作者", ai: "AI", admin: "审校", risk: "风险",
    selfcheck: "自检", quote: "引用", fact: "事实", typo: "文字" };
  const STATUS_LABEL = { pending: "待处理", accepted: "已采纳", rejected: "已拒绝",
    resolved: "已解决", outdated: "已失效" };
  const AF_STATUS = [["open", "待处理"], ["accepted", "已采纳"], ["rejected", "已拒绝"],
    ["resolved", "已解决"], ["outdated", "已失效"], ["all", "全部"]];
  const AF_KIND = [["all", "全部"], ["author", "作者"], ["ai", "AI"], ["admin", "审校"],
    ["risk", "风险"], ["selfcheck", "自检"]];

  function blockTag(kind) {
    return kind === "h2" ? "h2" : kind === "ul" ? "ul" : kind === "ol" ? "ol" : "p";
  }

  function aiOff() {
    return !!(Store.flags && Store.flags.aiConfigured === false);
  }

  function commentItems(c, state) {
    const f = (state && state.annoFilter) || { status: "open", kind: "all" };
    return (c.annotations || []).filter((a) =>
      (f.status === "all" || (f.status === "open" ? a.status === "pending" : a.status === f.status))
      && (f.kind === "all" || a.kind === f.kind));
  }

  function anchorItems(c) {
    return (c.annotations || []).filter((a) => !["resolved", "rejected"].includes(a.status));
  }

  function displayStatus(c, a) {
    if (a.status !== "pending" || !a.quote) return a.status;
    const block = Store.blocksOf(c)[Number(a.section)] || {};
    return String(block.text || "").includes(a.quote) ? "pending" : "outdated";
  }

  function commentRanges(c, index, text) {
    return anchorItems(c).filter((a) => Number(a.section) === index)
      .map((a) => ({ a, start: text.indexOf(a.quote || "") }))
      .filter((x) => x.a.quote && x.start >= 0)
      .map((x) => ({ id: x.a.id, start: x.start, end: x.start + x.a.quote.length }));
  }

  function markerParts(text) {
    const rows = [], re = new RegExp(ATTACHMENT_LINK, "g");
    let match;
    while ((match = re.exec(text))) rows.push({ start: match.index, end: re.lastIndex,
      source: match[0], label: unescapeLinkLabel(match[1]), id: match[2] });
    return rows;
  }

  function unescapeLinkLabel(label) {
    return String(label || "").replace(/\\([\\\[\]])/g, "$1");
  }

  function markerAt(source) {
    const match = new RegExp(`^${ATTACHMENT_LINK}$`).exec(source);
    return match && { source: match[0], label: unescapeLinkLabel(match[1]), id: match[2] };
  }

  function attachmentLinkHTML(c, marker) {
    const a = (c.attachments || []).find((x) => x.id === marker.id);
    const data = `data-attachment-id="${E(marker.id)}" data-attachment-source="${E(marker.source)}"`;
    if (!a || a.contentAvailable === false) {
      const title = a ? `${accessName(a.level)}内容` : "附件已移除";
      return `<span class="proto-attachment-link locked" ${data} contenteditable="false" title="${E(title)}">${E(marker.label)}</span>`;
    }
    return `<a class="proto-attachment-link" ${data} contenteditable="false" href="${attachmentHref(c, a)}" target="_blank" rel="noopener noreferrer" title="${E(a.title)}">${E(marker.label)}</a>`;
  }

  function expandCommentRange(range, markers) {
    const hit = markers.filter((m) => range.start < m.end && range.end > m.start);
    if (!hit.length) return range;
    return { ...range, start: Math.min(range.start, ...hit.map((m) => m.start)),
      end: Math.max(range.end, ...hit.map((m) => m.end)) };
  }

  function segmentHTML(c, source, ids, activeId) {
    const marker = markerAt(source);
    const body = marker ? attachmentLinkHTML(c, marker) : E(source);
    if (!ids.length) return body;
    const active = ids.includes(activeId) ? " active" : "";
    return `<span class="proto-anno-anchor${active}" data-anno-ids="${ids.map(E).join(" ")}">${body}</span>`;
  }

  function inlineHTML(text, c, index, state, offset) {
    const block = Store.blocksOf(c)[index] || {};
    const base = offset || 0;
    const markers = markerParts(text).map((m) => ({ ...m, start: m.start + base, end: m.end + base }));
    const ranges = commentRanges(c, index, String(block.text || ""))
      .map((r) => expandCommentRange(r, markers));
    const points = new Set([base, base + text.length]);
    ranges.forEach((r) => { points.add(r.start); points.add(r.end); });
    markers.forEach((m) => { points.add(m.start); points.add(m.end); });
    const sorted = Array.from(points).filter((x) => x >= base && x <= base + text.length).sort((a, b) => a - b);
    return sorted.slice(0, -1).map((start, i) => {
      const end = sorted[i + 1], source = text.slice(start - base, end - base);
      const ids = ranges.filter((r) => r.start <= start && r.end >= end).map((r) => r.id);
      return segmentHTML(c, source, ids, state.annoId);
    }).join("");
  }

  function listHTML(tag, block, c, index, state) {
    let offset = 0;
    const rows = String(block.text || "").split("\n").filter(Boolean).map((text) => {
      const html = `<li>${inlineHTML(text, c, index, state, offset)}</li>`;
      offset += text.length + 1;
      return html;
    });
    return `<${tag} data-block-index="${index}">${rows.join("")}</${tag}>`;
  }

  function blockHTML(block, c, index, state) {
    const tag = blockTag(block.kind);
    if (tag === "ul" || tag === "ol") return listHTML(tag, block, c, index, state);
    return `<${tag} data-block-index="${index}">${inlineHTML(block.text || "", c, index, state, 0)}</${tag}>`;
  }

  function docBlocks(c, state) {
    return Store.blocksOf(c).map((block, index) => blockHTML(block, c, index, state)).join("");
  }

  function publicVersion(c) {
    return (c.versions || []).slice().reverse().find((v) => /^公开版/.test(v.label));
  }

  function refTarget(ref) {
    return Store.db.cases.find((x) => x.id === ref.caseId);
  }

  function humanSize(n) {
    if (!n) return "";
    return n > 1048576 ? (n / 1048576).toFixed(1) + " MB" : Math.ceil(n / 1024) + " KB";
  }

  function fileToBase64(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result || "").split(",")[1] || "");
      reader.onerror = reject;
      reader.readAsDataURL(file);
    });
  }

  function statusLabel(status) {
    return ({ draft: "草稿", pending: "待审", reviewing: "审核中",
      published: "已发布", hidden: "已下线" })[status] || status;
  }

  P.workbenchPrototype = function (id, params) {
    const c = Store.caseById(id);
    if (!c) return P.notFound();
    return createController(c, createState(params));
  };

  P.caseAttachment = function (caseId, attachmentId) {
    const c = Store.caseById(caseId);
    const a = c && (c.attachments || []).find((x) => x.id === attachmentId);
    if (!c || !a) return P.notFound();
    return attachmentViewer(c, a);
  };

  function attachmentViewer(c, a) {
    const state = { blob: null, url: "" };
    return { html: attachmentViewerHTML(c, a),
      mount: (root) => mountAttachmentViewer(root, c, a, state),
      unmount: () => { if (state.url) URL.revokeObjectURL(state.url); } };
  }

  function attachmentViewerHTML(c, a) {
    const back = c.ownerId === Store.userId ? `#/workbench/${E(c.id)}?prototype=canvas&tool=files`
      : `#/case/${E(c.id)}`;
    return `<section class="proto-attachment-view"><header><a href="${back}" title="返回">←</a>
      <div><b>${E(a.title)}</b><span>${E(a.fileName || a.kind || "附件")} · ${accessName(a.level)}</span></div>
      <button data-attachment-download title="下载" disabled>⇩</button></header>
      <main data-attachment-stage><span class="proto-pulse"></span></main></section>`;
  }

  function attachmentFileAPI(c, a) {
    return `/api/cases/${encodeURIComponent(c.id)}/attachments/${encodeURIComponent(a.id)}/file`;
  }

  async function mountAttachmentViewer(root, c, a, state) {
    const stage = U.$("[data-attachment-stage]", root);
    const button = U.$("[data-attachment-download]", root);
    if (a.contentAvailable === false) return renderViewerError(stage, `${accessName(a.level)}内容`);
    const resp = await Store.apiFetch(attachmentFileAPI(c, a));
    if (!resp.ok) return renderViewerError(stage, await viewerError(resp));
    state.blob = await resp.blob();
    button.disabled = false;
    button.addEventListener("click", () => U.download(a.fileName || a.title, state.blob));
    await renderAttachmentBlob(stage, a, state);
  }

  async function viewerError(resp) {
    try { return (await resp.json()).error || "附件打开失败"; }
    catch (e) { return "附件打开失败"; }
  }

  function renderViewerError(stage, message) {
    stage.innerHTML = `<div class="proto-viewer-state"><span>⊘</span><b>${E(message)}</b></div>`;
  }

  async function renderAttachmentBlob(stage, a, state) {
    const mime = state.blob.type || a.mime || "application/octet-stream";
    if (/^text\//.test(mime) || /(?:json|xml|markdown)/.test(mime)) {
      stage.innerHTML = '<pre class="proto-viewer-text"></pre>';
      U.$("pre", stage).textContent = await state.blob.text();
      return;
    }
    state.url = URL.createObjectURL(state.blob);
    stage.innerHTML = viewerMediaHTML(mime, state.url, a.title);
  }

  function viewerMediaHTML(mime, url, title) {
    if (mime === "application/pdf") return `<iframe src="${url}" title="${E(title)}"></iframe>`;
    if (/^image\//.test(mime)) return `<img src="${url}" alt="${E(title)}">`;
    if (/^audio\//.test(mime)) return `<audio src="${url}" controls></audio>`;
    if (/^video\//.test(mime)) return `<video src="${url}" controls></video>`;
    return `<div class="proto-viewer-state"><span>▱</span><b>${E(title)}</b></div>`;
  }

  function createController(c, state) {
    const ctl = { c, state, root: null, agentHandle: null, onScroll: null };
    ctl.editable = () => c.ownerId === Store.userId && c.status === "draft";
    ctl.canComment = () => c.ownerId === Store.userId || Store.me().admin;
    ctl.draw = (capture) => drawController(ctl, capture);
    ctl.saveSoon = () => saveController(ctl);
    ctl.mount = (el) => mountController(ctl, el);
    ctl.unmount = () => {
      if (ctl.agentHandle) ctl.agentHandle.abort();
      if (ctl.onScroll) window.removeEventListener("scroll", ctl.onScroll);
      hideSelFloat(state);
    };
    return { html: '<section class="proto-host"></section>',
      mount: ctl.mount, unmount: ctl.unmount };
  }

  function ensureHistory(c, state) {
    if (state.historyLoaded || state.messages.length) return;
    state.historyLoaded = true;
    Copilot.getHistory("prototype:" + c.id).forEach((h) => {
      state.messages.push(h.role === "user" ? { role: "user", text: h.content }
        : { role: "ai", id: ++state.messageSeq, text: h.content, agents: [],
            result: null, candidate: "main", chunks: [], editable: false, canComment: false });
    });
  }

  function drawController(ctl, capture) {
    if (capture) captureDoc(ctl.root, ctl.c);
    if (ctl.state.tool === "ai") ensureHistory(ctl.c, ctl.state);
    ctl.state.messages.filter((x) => x.role === "ai").forEach((x) => {
      x.editable = ctl.editable();
      x.canComment = ctl.canComment();
    });
    ctl.root.innerHTML = layout(ctl.c, ctl.state, ctl.editable(), ctl.canComment());
  }

  function saveController(ctl) {
    captureDoc(ctl.root, ctl.c);
    ctl.state.save = "saving";
    paintSave(ctl.root, ctl.state);
    ctl.state.persist(ctl.c, ctl.root);
  }

  function mountController(ctl, el) {
    ctl.root = U.$(".proto-host", el) || el;
    ctl.root.classList.toggle("outline-collapsed", !!ctl.state.outlineCollapsed);
    const setHandle = (handle) => { ctl.agentHandle = handle; };
    bindRoot(ctl.root, ctl.c, ctl.state, ctl.editable, ctl.canComment,
      ctl.draw, ctl.saveSoon, setHandle);
    mountSpy(ctl);
    ctl.draw(false);
  }

  function createState(params) {
    const initialTool = params.tool === "research" ? "ai" : params.tool;
    const state = { tool: initialTool || "ai", folderTab: "attachments",
      selection: "", cursor: null, save: "saved", messages: [], annoId: "", checks: null,
      aiCheck: "", query: "", results: [], resultLimit: 5, searching: false,
      searchStatus: "", searchError: "", outlineIndex: -1, messageSeq: 0, sending: false,
      annoFilter: { status: "open", kind: "all" }, historyLoaded: false,
      flashAtt: "", selFloat: null, spyHoldUntil: 0,
      outlineCollapsed: localStorage.getItem("proto-outline-collapsed") === "1" };
    state.persist = U.debounce(async (c, root) => {
      const ok = await Store.saveCaseNow(c, { title: c.title, blocks: c.blocks,
        attachments: c.attachments || [], caseRefs: c.caseRefs || [] });
      state.save = ok ? "saved" : "error";
      paintSave(root, state);
    }, 550);
    return state;
  }

  function captureDoc(root, c) {
    const editor = root && U.$("[data-proto-editor]", root);
    if (!editor) return;
    c.blocks = Array.from(editor.children).map((node) => {
      const tag = node.tagName.toLowerCase();
      const kind = tag === "h2" ? "h2" : tag === "ul" ? "ul" : tag === "ol" ? "ol" : "p";
      const text = (tag === "ul" || tag === "ol")
        ? Array.from(node.children).map((x) => sourceText(x, c).trim()).filter(Boolean).join("\n")
        : sourceText(node, c).trim();
      return { kind, text };
    }).filter((x) => x.text);
  }

  function sourceText(node, c) {
    if (node.nodeType === Node.TEXT_NODE) return node.nodeValue || "";
    if (![Node.ELEMENT_NODE, Node.DOCUMENT_FRAGMENT_NODE].includes(node.nodeType)) return "";
    if (node.dataset && node.dataset.attachmentId) {
      return node.dataset.attachmentSource || attachmentMarker(
        { id: node.dataset.attachmentId }, node.textContent || "附件");
    }
    if (node.tagName === "BR") return "\n";
    return Array.from(node.childNodes).map((x) => sourceText(x, c)).join("");
  }

  function paintSave(root, state) {
    const el = root && U.$("[data-save-state]", root);
    if (!el) return;
    el.dataset.state = state.save;
    el.textContent = state.save === "saving" ? "保存中" : state.save === "error" ? "保存失败" : "已保存";
  }

  function toolbarHTML(editable) {
    if (!editable) return "";
    return `<div class="proto-format" role="toolbar">
      <button data-format="bold" title="加粗"><b>B</b></button>
      <button data-format="h2" title="标题">H2</button>
      <button data-format="p" title="正文">¶</button>
      <button data-format="insertUnorderedList" title="项目列表">•</button>
      <button data-format="insertOrderedList" title="编号列表">1.</button>
    </div>`;
  }

  function docHTML(c, state, editable) {
    return `<article class="proto-paper">
      ${toolbarHTML(editable)}
      <textarea class="proto-title" data-title rows="1" ${editable ? "" : "readonly"}>${E(c.title)}</textarea>
      <div class="proto-byline"><span>${E(c.course || "课程未定")}</span><span>${E(Store.typeName(c.typeId))}</span></div>
      <div class="proto-editor" data-proto-editor ${editable ? "contenteditable=true" : ""} spellcheck="false">${docBlocks(c, state)}</div>
      ${referenceSection(c)}
    </article>`;
  }

  function referenceSection(c) {
    const refs = c.caseRefs || [];
    if (!refs.length) return "";
    return `<footer class="proto-references"><h3>参考案例</h3>${refs.map((r, i) => {
      const target = refTarget(r);
      return `<a href="#/case/${E(r.caseId)}">〔${i + 1}〕${E(target ? target.title : r.title)} · ${E(r.versionLabel || "已发布版本")}</a>`;
    }).join("")}</footer>`;
  }

  function headerHTML(c, state, editable) {
    return `<header class="proto-head">
      <div class="proto-crumb"><a href="#/mine">我的案例</a><span>/</span><b>${E(c.title)}</b></div>
      <div class="proto-state"><span class="proto-status">${E(statusLabel(c.status))}</span><span data-save-state data-state="${state.save}">${state.save === "saving" ? "保存中" : "已保存"}</span></div>
      <div class="proto-actions">
        <button data-tool="ai" title="AI">✦</button>
        <button data-tool="versions" title="版本历史">◷</button>
        <button data-tool="files" title="附件">▱</button>
        <button data-tool="check" title="提交前自检">✓</button>
        <button data-export title="导出">⇩</button>
        ${editable ? `<button class="proto-primary" data-submit>提交</button>` : ""}
      </div>
    </header>`;
  }

  function toolRail(state, c) {
    const pending = (c.annotations || []).filter((a) => a.status === "pending").length;
    return `<nav class="proto-tools">${TOOLS.map((t) => `<button data-tool="${t[0]}" class="${state.tool === t[0] ? "active" : ""}" title="${t[2]}"><span>${t[1]}</span><b>${t[2]}</b>${t[0] === "comments" && pending ? `<i class="proto-badge">${pending}</i>` : ""}</button>`).join("")}</nav>`;
  }

  function outlineHTML(c, state, editable) {
    const rows = Store.blocksOf(c).map((b, i) => b.kind === "h2" ? [i, b.text] : null).filter(Boolean);
    const body = rows.length ? rows.map((x) => `<div class="proto-outline-row"><button data-outline="${x[0]}" class="${state.outlineIndex === x[0] ? "active" : ""}">${E(x[1])}</button>${editable ? `<button class="proto-sec-gen" data-sec-gen="${x[0]}" title="AI 生成本节">✦</button>` : ""}</div>`).join("")
      : '<div class="proto-outline-empty">正文还没有小标题</div>';
    return `<nav class="proto-outline" aria-label="正文目录">${body}<button class="proto-outline-collapse" data-outline-collapse title="收起目录">≪</button></nav>`;
  }

  function layout(c, state, editable, canComment) {
    return `<div class="proto-shell">${headerHTML(c, state, editable)}
      <div class="proto-workspace"><aside class="proto-outline-wrap">${outlineHTML(c, state, editable)}</aside>
      <main class="proto-canvas">${docHTML(c, state, editable)}</main>
      <aside class="proto-side">${toolRail(state, c)}${panelHTML(c, state, editable, canComment)}</aside></div></div>`;
  }

  function selectionHTML(state) {
    return state.selection ? `<button class="proto-selection" data-clear-selection title="清除选区">“${E(state.selection.slice(0, 70))}” ×</button>` : "";
  }

  function panelHTML(c, state, editable, canComment) {
    const body = state.tool === "comments" ? commentsHTML(c, state, canComment)
      : state.tool === "files" ? filesHTML(c, state, editable)
        : state.tool === "versions" ? versionsHTML(c, editable)
          : state.tool === "check" ? checkHTML(c, state, editable) : researchHTML(c, state, editable);
    const found = TOOLS.find((x) => x[0] === state.tool);
    const label = found ? found[2] : state.tool === "versions" ? "版本" : "自检";
    const clearBtn = state.tool === "ai" && state.messages.length
      ? '<button class="proto-panel-btn" data-ai-clear title="清空本会话的对话历史">清空</button>' : "";
    const head = !found || state.selection || clearBtn
      ? `<div class="proto-panel-head"><b>${label}</b><span class="proto-panel-side">${selectionHTML(state)}${clearBtn}</span></div>` : "";
    return `<section class="proto-panel">${head}${body}</section>`;
  }

  function researchHTML(c, state, editable) {
    const off = aiOff();
    return `<div class="proto-research">${off ? `<div class="proto-ai-off">${E(Copilot.AI_NOT_CONFIGURED)}</div>` : ""}<div class="proto-research-scroll">
      ${messagesHTML(state)}${researchStatusHTML(state)}${researchResultsHTML(c, state, editable)}
      </div><div class="proto-ai-tools">${AI_TOOLS.map((t) => aiToolHTML(t, off)).join("")}</div>
      <div class="proto-composer"><textarea data-agent-input placeholder="向 AI 提问" ${off ? "disabled" : ""}></textarea>
      <button class="proto-send" data-agent-send title="发送" ${state.sending || off ? "disabled" : ""}>↑</button></div></div>`;
  }

  function aiToolHTML(tool, off) {
    return `<button data-ai-tool="${tool[0]}" title="${E(tool[3])}" ${off ? "disabled" : ""}><span>${tool[1]}</span>${tool[2]}</button>`;
  }

  function messagesHTML(state) {
    return state.messages.map((m) => m.role === "user"
      ? `<div class="proto-msg user">${E(m.text)}</div>` : aiMessageHTML(m, state)).join("");
  }

  function chunkSources(msg) {
    return (msg.chunks || []).map((ch) => ({ n: ch.n, type: ch.kind,
      id: ch.materialId || ch.id, title: ch.title || "" }));
  }

  function agentTextHTML(msg) {
    const html = U.linkifyCitations(U.md(msg.text || ""), chunkSources(msg), { escaped: true });
    return html.replace(/\b(?:m|kn)-[a-z0-9][a-z0-9-]*\b/gi, (s) => {
      const id = s.toLowerCase(), kn = id.indexOf("kn-") === 0;
      const t = kn ? Store.knowledgeById(id) : Store.materialById(id);
      if (!t) return s;
      const title = kn ? (t.chapter || "") + " " + (t.title || "") : t.title;
      return `<a class="ai-cite" href="${kn ? "#/knowledge/" : "#/material/"}${E(id)}" title="${E(title)}">${s}</a>`;
    });
  }

  function toolLabel(tool) {
    return ({ search_corpus: "平台检索", web_search: "联网检索", fetch_url: "网页采集" })[tool] || tool;
  }

  function toolArgument(tool) {
    const args = tool.args || {};
    return args.q || args.query || args.url || "";
  }

  function agentToolHTML(tool) {
    const detail = [toolArgument(tool), tool.summary].filter(Boolean).join(" · ");
    return `<div class="proto-agent-tool"><span>⌁</span><b>${E(toolLabel(tool.tool))}</b><small>${E(detail)}</small></div>`;
  }

  function agentProcessHTML(msg) {
    if (!(msg.agents || []).length) return "";
    return `<div class="proto-agent-steps">${msg.agents.map((a) => `<div class="proto-agent-step"><span class="proto-agent-dot"></span><b>${E(a.label || a.agent)}</b>${(a.tools || []).map(agentToolHTML).join("")}</div>`).join("")}</div>`;
  }

  function candidateHTML(msg, state) {
    const result = msg.result, key = msg.candidate || "main", row = result[key] || result.main;
    const alt = (result.alt && result.alt.text) || msg.altText;
    const tabs = alt ? `<div class="proto-candidate-tabs"><button data-ai-candidate="${msg.id}:main" class="${key === "main" ? "active" : ""}">主方案</button><button data-ai-candidate="${msg.id}:alt" class="${key === "alt" ? "active" : ""}">备选</button></div>` : "";
    const diffBtn = msg.baseText != null
      ? `<div class="proto-candidate-tools"><button data-ai-diff="${msg.id}" class="${msg.diff ? "active" : ""}">对比</button></div>` : "";
    const body = msg.diff && msg.baseText != null
      ? diffBodyHTML(msg, row.text || "")
      : `<div class="proto-candidate-text">${E(row.text || "")}</div>`;
    const sel = state && state.selection
      ? `<button data-ai-apply="${msg.id}:replacesel">替换选区</button>` : "";
    const actions = msg.editable ? `<div class="proto-ai-actions">${sel}<button data-ai-apply="${msg.id}:replace">替换本节</button><button data-ai-apply="${msg.id}:append">追加</button><button data-ai-apply="${msg.id}:newsec">新节</button></div>` : "";
    return `${tabs}${diffBtn}${body}${actions}`;
  }

  function diffBodyHTML(msg, text) {
    const lines = U.diffLines(msg.baseText || "", text || "");
    const row = (l) => l.t === "+" ? `<p class="diff-add">+ ${E(l.s)}</p>`
      : l.t === "-" ? `<p class="diff-del">- ${E(l.s)}</p>`
        : `<p class="diff-same">${E(l.s)}</p>`;
    const out = [];
    let k = 0;
    while (k < lines.length) {
      if (lines[k].t !== " ") { out.push(row(lines[k])); k += 1; continue; }
      let j = k;
      while (j < lines.length && lines[j].t === " ") j += 1;
      out.push(diffSameRows(msg, lines, k, j, row));
      k = j;
    }
    return `<div class="proto-diff">${out.join("")}</div>`;
  }

  function diffSameRows(msg, lines, from, to, row) {
    if (to - from <= 6 || (msg.diffOpen && msg.diffOpen[from])) {
      return lines.slice(from, to).map(row).join("");
    }
    const fold = `<button class="proto-diff-fold" data-diff-fold="${msg.id}:${from}">… ${to - from - 6} 行未变，点击展开 …</button>`;
    return lines.slice(from, from + 3).map(row).join("") + fold
      + lines.slice(to - 3, to).map(row).join("");
  }

  function reviewHTML(msg) {
    const done = msg.transferred || new Set();
    const rows = (msg.result.items || []).map((item, i) => {
      const off = done.has(i);
      return `<label class="proto-review-row${off ? " transferred" : ""}"><input type="checkbox" data-review-item="${msg.id}:${i}" ${item.status === "pass" || off ? "" : "checked"} ${off ? "disabled" : ""}><span class="${item.status}">${item.status === "pass" ? "✓" : item.status === "risk" ? "!" : "?"}</span><div><b>${E(item.standard)}</b><p>${E(item.note)}</p></div></label>`;
    }).join("");
    const action = msg.canComment ? `<div class="proto-ai-actions"><button data-review-add="${msg.id}">加入批注</button></div>` : "";
    return `<div class="proto-review-list">${rows}</div>${action}`;
  }

  function aiResultHTML(msg, state) {
    if (msg.error) return `<div class="proto-ai-text proto-ai-error">${E(msg.error)}</div>
      <div class="proto-ai-actions"><button data-ai-retry="${msg.id}">重试</button></div>`;
    if (!msg.result) return `<div class="proto-ai-text">${msg.pending ? '<span class="proto-pulse"></span>' : ""}${agentTextHTML(msg)}</div>`;
    if (msg.result.kind === "candidates") return candidateHTML(msg, state);
    if (msg.result.kind === "review") return reviewHTML(msg);
    return `<div class="proto-ai-text">${agentTextHTML(msg)}</div>`;
  }

  function processChainHTML(msg) {
    const agents = msg.agents || [];
    if (!agents.length) return "";
    if (msg.pending) return agentProcessHTML(msg);
    const names = agents.map((a) => a.label || a.agent).join(" → ");
    const tools = agents.reduce((n, a) => n + (a.tools || []).length, 0);
    return `<div class="proto-agents-done"><button data-agents-toggle="${msg.id}"><span>过程：${E(names)}${tools ? " · " + tools + " 次工具调用" : ""}</span><span>${msg.agentsOpen ? "▴" : "▾"}</span></button>${msg.agentsOpen ? agentProcessHTML(msg) : ""}</div>`;
  }

  function aiMessageHTML(msg, state) {
    return `<article class="proto-msg ai" data-message-id="${msg.id}">${processChainHTML(msg)}<div class="proto-ai-result">${aiResultHTML(msg, state)}</div></article>`;
  }

  function researchStatusHTML(state) {
    if (!state.searchStatus && !state.searchError) return "";
    return `<div class="proto-research-status ${state.searchError ? "error" : ""}">${state.searching ? `<span class="proto-pulse"></span>` : ""}${E(state.searchError || state.searchStatus)}</div>`;
  }

  function researchResultsHTML(c, state, editable) {
    const rows = state.results.slice(0, state.resultLimit).map((r, i) => researchResultHTML(c, r, i, editable)).join("");
    const more = state.resultLimit < state.results.length ? `<button class="proto-more" data-results-more>更多结果</button>` : "";
    return `<div class="proto-research-results" data-ai-results ${rows ? "" : "hidden"}>${rows}${more}</div>`;
  }

  function researchResultHTML(c, r, index, editable) {
    const href = resultHref(r);
    const exists = resultExists(c, r);
    const control = resultControl(r, index, exists);
    return `<article class="proto-research-result"><div class="proto-result-source ${r.kind}">${E(r.label)}</div>
      <div class="proto-result-body"><a href="${href}" target="_blank" rel="noopener"><b>${E(r.title)}</b></a><p>${E(r.excerpt)}</p><small>${E(r.source || "")}</small></div>
      ${editable ? control : ""}</article>`;
  }

  function resultHref(r) {
    if (r.kind === "case") return `#/case/${encodeURIComponent(r.id)}`;
    if (r.kind === "material") return `#/material/${encodeURIComponent(r.id)}`;
    if (r.kind === "knowledge") return `#/knowledge/${encodeURIComponent(r.id)}`;
    return safeHref(r.url);
  }

  function resultControl(r, index, exists) {
    if (r.kind === "knowledge") return "";
    if (r.locked) return `<span class="proto-result-locked" title="${accessName(r.level)}内容">⊘</span>`;
    const action = r.kind === "case" ? "引用案例" : "加入附件";
    return `<button data-research-add="${index}" ${exists ? "disabled" : ""}>${exists ? "已加入" : action}</button>`;
  }

  function resultExists(c, r) {
    if (r.kind === "case") return (c.caseRefs || []).some((x) => x.caseId === r.id);
    if (r.kind === "material") return (c.attachments || []).some((x) => x.originMaterialId === r.id);
    return (c.attachments || []).some((x) => x.sourceUrl === r.url);
  }

  function annoChipsHTML(state) {
    const f = state.annoFilter;
    const chips = (attr, defs, cur) => defs.map((x) =>
      `<button data-${attr}="${x[0]}" class="${cur === x[0] ? "active" : ""}">${x[1]}</button>`).join("");
    return `<div class="proto-anno-filter"><div>${chips("afs", AF_STATUS, f.status)}</div><div>${chips("afk", AF_KIND, f.kind)}</div></div>`;
  }

  function commentsHTML(c, state, canComment) {
    const items = commentItems(c, state);
    const chips = annoChipsHTML(state);
    const active = items.find((x) => x.id === state.annoId) || items.find((x) => x.status === "pending") || items[0];
    if (!active) return `${chips}<div class="proto-empty">无批注</div>${canComment ? newCommentHTML() : ""}`;
    const index = items.findIndex((x) => x.id === active.id);
    return `${chips}<div class="proto-anno-nav"><button data-anno-nav="-1" title="上一条">↑</button><span>${index + 1} / ${items.length}</span><button data-anno-nav="1" title="下一条">↓</button></div>
      ${threadHTML(active, c, canComment)}
      ${canComment ? `<div class="proto-new-anno"><textarea data-anno-text placeholder="批注"></textarea><button data-anno-add>添加</button></div>` : ""}`;
  }

  function newCommentHTML() {
    return `<div class="proto-new-anno"><textarea data-anno-text placeholder="批注"></textarea><button data-anno-add>添加</button></div>`;
  }

  function threadFooter(a, st, c, canComment) {
    if (!canComment) return "";
    const owner = c.ownerId === Store.userId, reviewer = Store.me().admin && !owner;
    if (st === "outdated") return `<button data-anno-remount="${a.id}">重新定位</button>`;
    if (a.status !== "pending") return "";
    if (reviewer) return `<button data-anno-accept="${a.id}">采纳</button><button data-anno-reject="${a.id}">拒绝</button>`;
    return owner ? `<button data-anno-resolve="${a.id}">解决</button>` : "";
  }

  function threadHTML(a, c, canComment) {
    const st = displayStatus(c, a);
    const replies = (a.replies || []).map((r) => `<div class="proto-reply"><b>${E(r.byName || r.by || "")}</b><p>${E(r.text)}</p></div>`).join("");
    const reopen = canComment && ["resolved", "accepted", "rejected"].includes(a.status)
      ? `<label class="proto-reopen" title="回复并重开这条批注"><input type="checkbox" data-anno-reopen="${a.id}">重开</label>` : "";
    const replyBox = canComment ? `<div class="proto-reply-box"><textarea data-anno-reply="${a.id}" placeholder="回复"></textarea><button data-anno-reply-send="${a.id}">↑</button>${reopen}</div>` : "";
    return `<article class="proto-thread"><header><span class="anno-dot ${st}"></span><b>${E(a.author || KIND_LABEL[a.kind] || "批注")}</b><span class="proto-anno-kind">${E(KIND_LABEL[a.kind] || a.kind || "批注")}</span><small>${E(a.createdAt || a.at || "")} · ${E(STATUS_LABEL[st] || st)}</small></header>
      <button class="proto-anno-quote" data-anno-locate="${a.id}" title="定位到正文">${E(a.quote || "正文")}</button>
      <div class="proto-thread-text">${E(a.text || "")}</div>${replies}${replyBox}
      <footer>${threadFooter(a, st, c, canComment)}</footer></article>`;
  }

  function filesHTML(c, state, editable) {
    const tabs = `<div class="proto-folder-tabs"><button data-folder-tab="attachments" class="${state.folderTab === "attachments" ? "active" : ""}">附件 ${(c.attachments || []).length}</button><button data-folder-tab="refs" class="${state.folderTab === "refs" ? "active" : ""}">引用案例 ${(c.caseRefs || []).length}</button></div>`;
    return tabs + (state.folderTab === "refs" ? refsHTML(c, editable) : attachmentsHTML(c, state, editable));
  }

  function attachmentsHTML(c, state, editable) {
    const rows = (c.attachments || []).map((a) => `<article class="proto-file-row${state.flashAtt === a.id ? " flash" : ""}">
      <span class="file-kind">${a.kind === "网页" ? "↗" : "▱"}</span><div><a data-attachment-id="${E(a.id)}" href="${attachmentHref(c, a)}" target="_blank" rel="noopener noreferrer"><b>${E(a.title)}</b></a><span>${E(a.source || a.fileName || "")}${a.size ? " · " + humanSize(a.size) : ""}</span></div>
      ${editable ? `<select data-att-level data-aid="${a.id}" title="内容访问级别">${accessOptions(a.level)}</select><button data-att-insert="${a.id}" title="插入正文">↳</button><button data-att-delete="${a.id}" title="移除">×</button>` : `<span class="proto-file-level">${accessName(a.level)}</span>`}</article>`).join("");
    return `<div class="proto-file-list">${rows || '<div class="proto-empty">无附件</div>'}</div>${editable ? `<div class="proto-file-actions"><button data-file-pick>＋ 上传</button><button data-tool="ai">✦ 查找</button><input type="file" data-file-input hidden></div>` : ""}`;
  }

  function accessName(level) {
    return ["公开", "校内", "私密"][Number(level)] || "私密";
  }

  function accessOptions(level) {
    const active = [0, 1, 2].includes(Number(level)) ? Number(level) : 2;
    return ["公开", "校内", "私密"].map((name, i) =>
      `<option value="${i}" ${active === i ? "selected" : ""}>${name}</option>`).join("");
  }

  function attachmentHref(c, a) {
    if (/^https?:\/\//i.test(a.sourceUrl || "")) return safeHref(a.sourceUrl);
    return `#/attachment/${encodeURIComponent(c.id)}/${encodeURIComponent(a.id)}`;
  }

  function safeHref(url) {
    return /^https?:\/\//i.test(url || "") ? E(url) : "#";
  }

  function openAttachmentLink(event, c, id) {
    const a = (c.attachments || []).find((x) => x.id === id);
    if (!a || a.contentAvailable === false) { event.preventDefault(); return true; }
    return true;
  }

  function refsHTML(c, editable) {
    const rows = (c.caseRefs || []).map((r) => {
      const target = refTarget(r);
      return `<article class="proto-ref-row"><div><b>${E(target ? target.title : r.title)}</b><span>${E(r.versionLabel || "已发布版本")}</span></div><a href="#/case/${r.caseId}" title="打开案例">↗</a>${editable ? `<button data-ref-delete="${r.caseId}" title="移除">×</button>` : ""}</article>`;
    }).join("");
    return `<div class="proto-file-list">${rows || '<div class="proto-empty">无引用案例</div>'}</div>`;
  }

  function versionsHTML(c, editable) {
    const rows = (c.versions || []).slice().reverse().map((v) => `<article class="proto-version"><span>◷</span><div><b>${E(v.label)}</b><small>${E(v.at || "")}</small></div>${editable && v.snapshot ? `<button data-version-rollback="${v.id}">回滚</button>` : ""}</article>`).join("");
    return `${editable ? `<div class="proto-version-new"><input data-version-label placeholder="版本名称"><button data-version-save>保存</button></div>` : ""}<div>${rows || '<div class="proto-empty">无版本</div>'}</div>`;
  }

  function checkHTML(c, state, editable) {
    const checks = state.checks || [];
    const rows = checks.map((x) => `<div class="proto-check-row ${x.ok ? "pass" : "fail"}"><span>${x.ok ? "✓" : "!"}</span><b>${E(x.name)}</b></div>`).join("");
    return `<div class="proto-checks">${rows}${state.aiCheck ? `<div class="proto-ai-check">${E(state.aiCheck)}</div>` : ""}</div>
      <div class="proto-check-actions"><button data-check-run>运行自检</button>${editable && state.checks ? `<button class="proto-primary" data-submit-confirm>提交审核</button>` : ""}</div>`;
  }

  function bindRoot(root, c, state, editable, canComment, draw, saveSoon, setAgentHandle) {
    root.addEventListener("click", (e) => handleClick(e, root, c, state, editable, draw, saveSoon, setAgentHandle));
    root.addEventListener("input", (e) => handleInput(e, c, saveSoon));
    root.addEventListener("change", (e) => handleChange(e, root, c, state, draw, saveSoon));
    const onSel = () => { captureSelection(root, state, c);
      refreshSelFloat(root, c, state, editable, canComment, draw); };
    root.addEventListener("mouseup", onSel);
    root.addEventListener("keyup", onSel);
    root.addEventListener("keydown", handleKey);
  }

  function hideSelFloat(state) {
    if (state.selFloat) { state.selFloat.remove(); state.selFloat = null; }
  }

  function selFloatBtn(label, fn) {
    const b = document.createElement("button");
    b.textContent = label;
    b.addEventListener("mousedown", (e) => { e.preventDefault(); fn(); });
    return b;
  }

  function refreshSelFloat(root, c, state, editable, canComment, draw) {
    hideSelFloat(state);
    const sel = window.getSelection(), editor = U.$("[data-proto-editor]", root);
    if (!state.selection || !sel || sel.isCollapsed || !sel.rangeCount
      || !editor || !editor.contains(sel.anchorNode)) return;
    if (!editable() && !canComment()) return;
    const rect = sel.getRangeAt(0).getBoundingClientRect();
    const bar = document.createElement("div");
    bar.className = "proto-sel-float";
    bar.style.top = (window.scrollY + rect.top - 42) + "px";
    bar.style.left = (window.scrollX + Math.max(8, rect.left)) + "px";
    if (canComment()) bar.appendChild(selFloatBtn("▤ 加批注",
      () => annotateSelection(c, state, draw)));
    if (editable()) bar.appendChild(selFloatBtn("✦ AI 修改",
      () => aiEditSelection(root, state, draw)));
    document.body.appendChild(bar);
    state.selFloat = bar;
  }

  function aiEditSelection(root, state, draw) {
    hideSelFloat(state);
    state.tool = "ai";
    draw(true);
    const input = U.$("[data-agent-input]", root);
    if (input) { input.value = "修改这段文字：" + state.selection; input.focus(); }
  }

  function annotateSelection(c, state, draw) {
    hideSelFloat(state);
    const blocks = Store.blocksOf(c);
    const section = Math.max(0, Math.min((state.cursor || {}).block || 0, blocks.length - 1));
    const reviewer = Store.me().admin && c.ownerId !== Store.userId;
    const close = U.modal(`<div class="modal-head"><b>添加批注</b><button class="modal-close" data-close>×</button></div>
      <div class="modal-body"><textarea class="text" id="sa-quote" style="height:64px;margin-bottom:10px" placeholder="锚定文本">${E(state.selection)}</textarea>
      <textarea class="text" id="sa-text" style="height:110px" placeholder="批注内容"></textarea></div>
      <div class="modal-foot"><button class="btn plain" data-close>取消</button><button class="btn" id="sa-go">保存批注</button></div>`,
      { sticky: true });
    U.$("#sa-text").focus();
    U.$("#sa-go").addEventListener("click", async () => {
      const text = U.$("#sa-text").value.trim();
      if (!text) { U.toast("请填写批注内容"); return; }
      const a = await Store.addAnnotation(c, { kind: reviewer ? "admin" : "author",
        text, quote: U.$("#sa-quote").value.trim().slice(0, 160),
        author: Store.me().name, section });
      if (!a) return;
      close();
      window.getSelection().removeAllRanges();
      state.annoId = a.id; state.selection = ""; state.tool = "comments";
      draw(false);
    });
  }

  function handleInput(e, c, saveSoon) {
    if (e.target.matches("[data-title]")) c.title = e.target.value;
    if (e.target.matches("[data-agent-input]") && e.target.dataset.seed
        && !e.target.value.startsWith(e.target.dataset.seed)) {
      delete e.target.dataset.seed;
      delete e.target.dataset.intentHint;
    }
    if (e.target.matches("[data-title],[data-proto-editor]")) saveSoon();
  }

  function handleKey(e) {
    if (e.target.matches("[data-agent-input]") && e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      e.target.closest(".proto-composer").querySelector("[data-agent-send]").click();
    }
  }

  function captureSelection(root, state, c) {
    const sel = window.getSelection();
    const editor = U.$("[data-proto-editor]", root);
    if (!sel || !editor || !sel.rangeCount || !editor.contains(sel.anchorNode)) return;
    state.cursor = selectionCursor(editor, sel.getRangeAt(0), c);
    const text = sel.toString().trim();
    if (!text) { state.selection = ""; return; }
    state.selection = text.slice(0, 300);
    const chip = U.$(".proto-selection", root);
    if (chip) chip.textContent = `“${state.selection.slice(0, 70)}” ×`;
  }

  function selectionCursor(editor, range, c) {
    const startBlock = directBlock(editor, range.startContainer);
    const endBlock = directBlock(editor, range.endContainer);
    if (!startBlock) return null;
    const start = textOffset(startBlock, range.startContainer, range.startOffset, c);
    const end = startBlock === endBlock
      ? textOffset(startBlock, range.endContainer, range.endOffset, c) : start;
    return { block: Array.from(editor.children).indexOf(startBlock), start, end };
  }

  function directBlock(editor, node) {
    let el = node.nodeType === Node.ELEMENT_NODE ? node : node.parentElement;
    while (el && el.parentElement !== editor) el = el.parentElement;
    return el && el.parentElement === editor ? el : null;
  }

  function textOffset(block, node, offset, c) {
    const range = document.createRange();
    range.selectNodeContents(block);
    range.setEnd(node, offset);
    return sourceText(range.cloneContents(), c).length;
  }

  function handleFormat(btn) {
    const cmd = btn.dataset.format;
    if (cmd === "h2" || cmd === "p") document.execCommand("formatBlock", false, cmd);
    else document.execCommand(cmd, false, null);
  }

  async function handleChange(e, root, c, state, draw, saveSoon) {
    if (e.target.matches("[data-att-level]")) {
      const a = (c.attachments || []).find((x) => x.id === e.target.dataset.aid);
      if (a) { a.level = Number(e.target.value); saveSoon(); }
    }
    if (e.target.matches("[data-file-input]") && e.target.files[0]) {
      const a = await uploadFile(c, e.target.files[0]);
      if (a && a.duplicate) {
        state.tool = "files"; state.flashAtt = a.id;
        U.toast("附件已存在（查重命中）");
      }
      draw(false);
      state.flashAtt = "";
    }
  }

  async function uploadFile(c, file) {
    const data = await fileToBase64(file);
    const a = await Store.addCaseAttachment(c, { title: file.name, fileName: file.name,
      mime: file.type, kind: "文件", data });
    if (a && !a.duplicate) U.toast("附件已添加");
    if (!a) U.toast("附件添加失败");
    return a;
  }

  function handlePanelAction(t, root, c, state, draw, setAgentHandle) {
    if (t.dataset.outline) return scrollToBlock(root, state, Number(t.dataset.outline));
    if (t.dataset.secGen) return sectionGenerate(root, c, state, draw, setAgentHandle, Number(t.dataset.secGen));
    if (t.hasAttribute("data-outline-collapse")) return toggleOutline(root, state);
    if (t.dataset.afs) { state.annoFilter.status = t.dataset.afs; draw(true); return true; }
    if (t.dataset.afk) { state.annoFilter.kind = t.dataset.afk; draw(true); return true; }
    if (t.hasAttribute("data-ai-clear")) { clearAgentHistory(c, state, draw); return true; }
    if (t.hasAttribute("data-results-more")) { state.resultLimit += 5; draw(true); return true; }
    if (t.hasAttribute("data-file-pick")) return U.$("[data-file-input]", root).click();
    if (t.dataset.annoIds) return openAnnotation(root, c, state, t.dataset.annoIds.split(" ")[0], draw);
    if (t.dataset.annoLocate) return locateAnnotation(root, state, t.dataset.annoLocate);
    if (t.dataset.annoNav) return navigateAnnotation(root, c, state, Number(t.dataset.annoNav), draw);
    if (t.hasAttribute("data-anno-add")) return addAnnotation(root, c, state, draw);
    if (t.dataset.annoResolve) return resolveAnnotation(c, t.dataset.annoResolve, draw);
    if (t.dataset.annoAccept) return setAnnoStatus(c, t.dataset.annoAccept, "accepted", draw);
    if (t.dataset.annoReject) return setAnnoStatus(c, t.dataset.annoReject, "rejected", draw);
    if (t.dataset.annoRemount) return remountAnnotation(root, c, t.dataset.annoRemount, draw);
    if (t.dataset.annoReplySend) return replyAnnotation(root, c, t.dataset.annoReplySend, draw);
    if (t.dataset.aiTool) return prepareAITool(root, t.dataset.aiTool);
    if (t.dataset.aiCandidate) return switchCandidate(root, state, t.dataset.aiCandidate, c);
    if (t.dataset.aiDiff) return toggleDiff(root, state, t.dataset.aiDiff);
    if (t.dataset.diffFold) return openDiffFold(root, state, t.dataset.diffFold);
    if (t.dataset.agentsToggle) return toggleAgents(root, state, t.dataset.agentsToggle);
    if (t.dataset.aiRetry) return retryAgent(root, c, state, draw, setAgentHandle, t.dataset.aiRetry);
    if (t.dataset.aiApply) return applyAIResult(root, c, state, t.dataset.aiApply, draw);
    if (t.dataset.reviewAdd) return addReviewComments(root, c, state, t.dataset.reviewAdd, draw);
    if (t.dataset.attInsert) return insertAttachment(c, state, t.dataset.attInsert, draw);
    if (t.dataset.attDelete) return deleteAttachment(c, t.dataset.attDelete, draw);
    if (t.dataset.refDelete) return deleteReference(c, t.dataset.refDelete, draw);
    return null;
  }

  function handleCaseAction(t, root, c, state, draw) {
    if (t.hasAttribute("data-version-save")) return saveVersion(root, c, draw);
    if (t.dataset.versionRollback) return rollbackVersion(c, t.dataset.versionRollback, draw);
    if (t.hasAttribute("data-check-run") || t.hasAttribute("data-submit")) return runCheck(c, state, draw);
    if (t.hasAttribute("data-submit-confirm")) return submitCase(c, draw);
    if (t.hasAttribute("data-export")) return exportCase(c);
    if (t.dataset.researchAdd) return addResearchResult(c, state, Number(t.dataset.researchAdd), draw);
    return null;
  }

  function handleClick(e, root, c, state, editable, draw, saveSoon, setAgentHandle) {
    const t = e.target.closest("button,[data-format],[data-tool],[data-outline],[data-anno-ids],a");
    if (!t) return;
    captureSelection(root, state, c);
    if (t.dataset.attachmentId) return openAttachmentLink(e, c, t.dataset.attachmentId);
    if (t.dataset.format) return handleFormat(t);
    if (t.dataset.tool) { state.tool = t.dataset.tool; draw(true); return; }
    if (t.dataset.folderTab) { state.folderTab = t.dataset.folderTab; draw(true); return; }
    if (t.hasAttribute("data-clear-selection")) { state.selection = ""; draw(true); return; }
    if (t.hasAttribute("data-agent-send")) return sendAgent(root, c, state, draw, setAgentHandle);
    const handled = handlePanelAction(t, root, c, state, draw, setAgentHandle)
      || handleCaseAction(t, root, c, state, draw);
    if (!handled && editable()) saveSoon();
  }

  function scrollToBlock(root, state, index) {
    const editor = U.$("[data-proto-editor]", root);
    const node = editor && editor.children[index];
    if (!node) return;
    state.outlineIndex = index;
    state.spyHoldUntil = Date.now() + 1200;
    U.$$("[data-outline]", root).forEach((x) => x.classList.toggle("active", Number(x.dataset.outline) === index));
    node.scrollIntoView({ behavior: "smooth", block: "center" });
  }

  function toggleOutline(root, state) {
    state.outlineCollapsed = !state.outlineCollapsed;
    root.classList.toggle("outline-collapsed", state.outlineCollapsed);
    localStorage.setItem("proto-outline-collapsed", state.outlineCollapsed ? "1" : "0");
    return true;
  }

  function mountSpy(ctl) {
    let last = 0;
    ctl.onScroll = () => {
      hideSelFloat(ctl.state);
      const now = Date.now();
      if (now - last < 100) return;
      last = now;
      spyOutline(ctl);
    };
    window.addEventListener("scroll", ctl.onScroll, { passive: true });
  }

  function spyOutline(ctl) {
    if ((ctl.state.spyHoldUntil || 0) > Date.now()) return;
    const editor = U.$("[data-proto-editor]", ctl.root);
    if (!editor) return;
    const line = window.innerHeight * 0.4;
    let active = -1;
    Array.from(editor.children).forEach((el, i) => {
      if (el.tagName === "H2" && el.getBoundingClientRect().top <= line) active = i;
    });
    if (active === ctl.state.outlineIndex) return;
    ctl.state.outlineIndex = active;
    U.$$("[data-outline]", ctl.root).forEach((x) =>
      x.classList.toggle("active", Number(x.dataset.outline) === active));
  }

  function sectionGenerate(root, c, state, draw, setAgentHandle, index) {
    captureDoc(root, c);
    const title = (Store.blocksOf(c)[index] || {}).text || "";
    state.cursor = { block: index, start: 0, end: 0 };
    state.tool = "ai";
    startAgent(root, c, state, draw, setAgentHandle,
      { text: `请围绕「${title}」生成/完善本节内容`, intentHint: "draft" });
    return true;
  }

  function clearAgentHistory(c, state, draw) {
    Copilot.clearHistory("prototype:" + c.id);
    state.messages = [];
    draw(true);
  }

  function sectionAt(c, state) {
    const blocks = Store.blocksOf(c), focus = Math.max(0, Math.min((state.cursor || {}).block || 0, blocks.length - 1));
    let from = 0;
    for (let i = 0; i <= focus; i += 1) if (blocks[i].kind === "h2") from = i;
    let to = blocks.length;
    for (let i = from + 1; i < blocks.length; i += 1) if (blocks[i].kind === "h2") { to = i; break; }
    return { from, to, bodyFrom: blocks[from] && blocks[from].kind === "h2" ? from + 1 : from,
      title: blocks[from] && blocks[from].kind === "h2" ? blocks[from].text : "正文开头" };
  }

  function citationContext(row, index) {
    const target = Store.citeTarget(row.target) || {}, evidence = row.evidence || {};
    return { n: index + 1, target: row.target, title: target.title || target.chapter || row.target,
      source: target.source || "", sec: evidence.sec || "", snippet: evidence.snippet || "" };
  }

  function agentCaseContext(c, state) {
    const blocks = Store.blocksOf(c), sec = sectionAt(c, state);
    return { caseId: c.id, title: c.title, sectionTitle: sec.title,
      sectionText: blocks.slice(sec.from, sec.to).map((b) => b.text).join("\n").slice(0, 4000),
      bodyExcerpt: blocks.map((b) => b.text).join("\n").slice(0, 1500),
      citations: (c.citations || []).map(citationContext) };
  }

  function prepareAITool(root, id) {
    const tool = AI_TOOLS.find((x) => x[0] === id), input = U.$("[data-agent-input]", root);
    if (!tool || !input) return true;
    input.value = tool[3];
    input.dataset.seed = tool[3];
    input.dataset.intentHint = ["web", "fetch-url"].includes(id) ? "find-material" : id;
    input.focus();
    input.setSelectionRange(input.value.length, input.value.length);
    return true;
  }

  function agentRole(msg, frame) {
    let row = msg.agents.find((x) => x.agent === frame.agent);
    if (!row) { row = { agent: frame.agent, label: frame.agent, model: "", skill: "", tools: [] }; msg.agents.push(row); }
    row.label = frame.label || row.label;
    row.model = frame.model || row.model;
    row.skill = frame.skill || row.skill;
    return row;
  }

  function addAgentTool(msg, frame) {
    const row = agentRole(msg, frame);
    row.tools.push({ tool: frame.tool, args: frame.args || {}, summary: frame.summary || "" });
  }

  function normalizeToolResult(row) {
    const labels = { case: "案例", material: "案例附件", knowledge: "知识", web: "互联网" };
    const raw = row.kind === "case" ? Store.db.cases.find((x) => x.id === row.id)
      : row.kind === "material" ? Store.materialById(row.id) : row;
    return { ...row, label: labels[row.kind] || "来源", raw: raw || row,
      locked: row.locked || (raw && raw.contentAvailable === false) };
  }

  function resultKey(row) {
    return row.kind + ":" + (row.id || row.url || row.title);
  }

  function ingestToolItems(state, items, c) {
    const seen = new Set(state.results.map(resultKey));
    (items || []).map(normalizeToolResult).forEach((row) => {
      if ((row.kind === "case" && row.id === c.id) || seen.has(resultKey(row))) return;
      state.results.push(row);
      seen.add(resultKey(row));
    });
  }

  function paintAgentTurn(root, msg, state) {
    const row = U.$(`[data-message-id="${Number(msg.id)}"]`, root);
    if (row) row.innerHTML = processChainHTML(msg) + `<div class="proto-ai-result">${aiResultHTML(msg, state)}</div>`;
  }

  function toggleDiff(root, state, id) {
    const msg = messageById(state, id);
    if (!msg) return true;
    msg.diff = !msg.diff;
    paintAgentTurn(root, msg, state);
    return true;
  }

  function openDiffFold(root, state, spec) {
    const [id, k] = spec.split(":"), msg = messageById(state, id);
    if (!msg) return true;
    msg.diffOpen = msg.diffOpen || {};
    msg.diffOpen[Number(k)] = true;
    paintAgentTurn(root, msg, state);
    return true;
  }

  function toggleAgents(root, state, id) {
    const msg = messageById(state, id);
    if (!msg) return true;
    msg.agentsOpen = !msg.agentsOpen;
    paintAgentTurn(root, msg, state);
    return true;
  }

  function paintToolResults(root, c, state, editable) {
    const row = U.$("[data-ai-results]", root);
    if (!row) return;
    const rows = state.results.slice(0, state.resultLimit)
      .map((x, i) => researchResultHTML(c, x, i, editable)).join("");
    const more = state.resultLimit < state.results.length
      ? '<button class="proto-more" data-results-more>更多结果</button>' : "";
    row.innerHTML = rows + more;
    row.hidden = !state.results.length;
  }

  function paintResearchStatus(root, state) {
    const row = U.$(".proto-research-status", root);
    if (!row) return;
    row.hidden = !state.searchStatus && !state.searchError;
    row.textContent = state.searchError || state.searchStatus;
    row.classList.toggle("error", !!state.searchError);
  }

  function finishAgent(root, msg, state, result, error, setAgentHandle) {
    msg.pending = false;
    msg.result = result || null;
    msg.error = error || "";
    msg.chunks = (result && result.chunks) || [];
    msg.text = error || Copilot.agentResultText(result) || msg.text;
    state.sending = false;
    state.searching = false;
    state.searchStatus = "";
    state.searchError = error || "";
    setAgentHandle(null);
    paintAgentTurn(root, msg, state);
    paintResearchStatus(root, state);
    const send = U.$("[data-agent-send]", root);
    if (send) send.disabled = false;
  }

  function agentCallbacks(root, c, state, msg, editable, setAgentHandle) {
    let paintTimer = null;
    const schedulePaint = () => {
      if (paintTimer) return;
      paintTimer = setTimeout(() => { paintTimer = null; paintAgentTurn(root, msg, state); }, 80);
    };
    const settle = (fn) => { if (paintTimer) { clearTimeout(paintTimer); paintTimer = null; } fn(); };
    return {
      onRole(j) { agentRole(msg, j); schedulePaint(); },
      onTool(j) { addAgentTool(msg, j); ingestToolItems(state, j.items, c);
        state.searchStatus = j.summary || ""; schedulePaint();
        paintToolResults(root, c, state, editable); paintResearchStatus(root, state); },
      onToken(j) { if (j.which === "alt") { msg.altText += j.text || ""; return; }
        msg.text += j.text || ""; schedulePaint(); },
      onResult(j) { msg.result = j; },
      onDone(r) { settle(() => finishAgent(root, msg, state, r, "", setAgentHandle)); },
      onError(err) { settle(() => finishAgent(root, msg, state, null,
        err.message || String(err), setAgentHandle)); },
    };
  }

  function sectionBody(c, state) {
    const blocks = Store.blocksOf(c), sec = sectionAt(c, state);
    return blocks.slice(sec.bodyFrom, sec.to).map((b) => b.text).join("\n");
  }

  function sendAgent(root, c, state, draw, setAgentHandle) {
    const input = U.$("[data-agent-input]", root), text = (input.value || "").trim();
    if (!text || state.sending) return true;
    startAgent(root, c, state, draw, setAgentHandle,
      { text, intentHint: input.dataset.intentHint || undefined });
    return true;
  }

  function retryAgent(root, c, state, draw, setAgentHandle, id) {
    const msg = messageById(state, id);
    if (!msg || !msg.retryPayload || state.sending) return true;
    startAgent(root, c, state, draw, setAgentHandle, msg.retryPayload);
    return true;
  }

  function startAgent(root, c, state, draw, setAgentHandle, payload) {
    if (state.sending) return;
    captureDoc(root, c);
    const selection = payload.selection || state.selection || "";
    const sec = sectionAt(c, state);
    const msg = { id: ++state.messageSeq, role: "ai", text: "", altText: "", pending: true,
      agents: [], result: null, candidate: "main", chunks: [],
      baseText: selection || sectionBody(c, state), baseSection: sec.from,
      editable: c.ownerId === Store.userId && c.status === "draft",
      canComment: c.ownerId === Store.userId || Store.me().admin,
      retryPayload: { text: payload.text, intentHint: payload.intentHint, selection } };
    state.messages.push({ role: "user", text: payload.text }, msg);
    state.results = []; state.resultLimit = 5; state.sending = true; state.searching = true;
    state.searchError = ""; state.searchStatus = "处理中";
    draw(true);
    const opts = { text: payload.text, intentHint: payload.intentHint,
      selection: selection || undefined,
      caseContext: agentCaseContext(c, state), conversationKey: "prototype:" + c.id,
      ...agentCallbacks(root, c, state, msg, msg.editable, setAgentHandle) };
    setAgentHandle(Copilot.agent(opts));
  }

  function messageById(state, id) {
    return state.messages.find((x) => x.role === "ai" && Number(x.id) === Number(id));
  }

  function switchCandidate(root, state, spec) {
    const [id, key] = spec.split(":"), msg = messageById(state, id);
    if (!msg || !msg.result || !msg.result[key]) return true;
    msg.candidate = key;
    paintAgentTurn(root, msg, state);
    return true;
  }

  function candidateText(msg) {
    const row = msg.result[msg.candidate || "main"] || msg.result.main;
    return row && row.text ? row.text.trim() : "";
  }

  function textBlocks(text) {
    return String(text || "").split(/\n{2,}/).map((x) => x.trim()).filter(Boolean)
      .map((text) => text.startsWith("## ")
        ? { kind: "h2", text: text.slice(3).trim() } : { kind: "p", text });
  }

  function applyBlocks(c, state, mode, rows) {
    const blocks = Store.blocksOf(c).map((x) => ({ kind: x.kind, text: x.text }));
    const sec = sectionAt(c, state);
    if (mode === "replace") blocks.splice(sec.bodyFrom, sec.to - sec.bodyFrom, ...rows);
    if (mode === "append") blocks.splice(sec.to, 0, ...rows);
    if (mode === "newsec") blocks.splice(sec.to, 0, { kind: "h2", text: "补充" }, ...rows);
    c.blocks = blocks;
  }

  function docPlain(c) {
    return Store.blocksOf(c).map((b) => b.text).join("\n");
  }

  function matchNormalized(hay, needle) {
    const nn = String(needle || "").replace(/\s+/g, "");
    if (!nn) return null;
    const map = [];
    let nh = "";
    for (let i = 0; i < hay.length; i += 1) {
      if (!/\s/.test(hay[i])) { nh += hay[i]; map.push(i); }
    }
    const first = nh.indexOf(nn);
    if (first < 0) return null;
    return { start: map[first], end: map[first + nn.length - 1] + 1,
      unique: nh.indexOf(nn, first + 1) < 0 };
  }

  function candidateModel(msg) {
    const row = msg.result[msg.candidate || "main"] || msg.result.main || {};
    return row.model || msg.result.model || "";
  }

  async function adoptRisks(c, state, msg) {
    const row = msg.result[msg.candidate || "main"] || msg.result.main || {};
    const section = Math.max(0, Math.min((state.cursor || {}).block || 0,
      Store.blocksOf(c).length - 1));
    for (const rk of row.risks || msg.result.risks || []) {
      await Store.addAnnotation(c, { kind: "risk", author: "AI",
        text: rk.note || rk.standard || "AI 生成内容风险",
        quote: String(rk.quote || "").replace(/〔\d+[^〕]*〕/g, "").slice(0, 60), section });
    }
  }

  async function afterAdopt(c, state, msg, text) {
    Copilot.materializeCitations(c, { text, chunks: msg.result.chunks || [] });
    Store.markAiAssist(c, candidateModel(msg));
    const ok = await Store.saveCaseNow(c, { blocks: c.blocks,
      citations: c.citations || [], meta: c.meta });
    await adoptRisks(c, state, msg);
    U.toast(ok ? "已写入正文" : "写入失败");
  }

  async function applyAIResult(root, c, state, spec, draw) {
    const [id, mode] = spec.split(":"), msg = messageById(state, id);
    if (c.ownerId !== Store.userId || c.status !== "draft") return true;
    if (!msg || !msg.result || msg.result.kind !== "candidates") return true;
    captureDoc(root, c);
    const text = candidateText(msg), rows = textBlocks(text);
    if (!rows.length) return true;
    if (mode === "replacesel") return applyReplaceSel(c, state, msg, text, draw);
    if (msg.baseText != null && sectionBody(c, state) !== msg.baseText
      && !(await U.confirmModal("正文已变化，仍要写入？"))) return true;
    applyBlocks(c, state, mode, rows);
    await afterAdopt(c, state, msg, text);
    draw(false);
    return true;
  }

  async function applyReplaceSel(c, state, msg, text, draw) {
    const blocks = Store.blocksOf(c).map((x) => ({ kind: x.kind, text: x.text }));
    const offs = [];
    let acc = 0;
    blocks.forEach((b) => { offs.push(acc); acc += b.text.length + 1; });
    const m = matchNormalized(docPlain(c), state.selection || msg.baseText || "");
    if (!m || !m.unique) { U.toast("选区原文在正文中不是唯一匹配，无法替换"); return true; }
    const locate = (pos) => {
      for (let i = blocks.length - 1; i >= 0; i -= 1) if (pos >= offs[i]) return i;
      return 0;
    };
    const sB = locate(m.start), eB = locate(Math.max(m.start, m.end - 1));
    const merged = blocks[sB].text.slice(0, m.start - offs[sB]) + text
      + blocks[eB].text.slice(Math.min(blocks[eB].text.length, m.end - offs[eB]));
    const parts = merged.split(/\n+/).map((s) => s.trim()).filter(Boolean);
    if (!parts.length) parts.push("");
    blocks.splice(sB, eB - sB + 1,
      ...parts.map((t, k) => ({ kind: k === 0 ? blocks[sB].kind : "p", text: t })));
    c.blocks = blocks;
    state.selection = "";
    await afterAdopt(c, state, msg, text);
    draw(false);
    return true;
  }

  function reviewAnchor(c, item, state) {
    const blocks = Store.blocksOf(c), ref = String(item.ref || "").trim();
    let section = ref && !/^〔\d+〕$/.test(ref) ? blocks.findIndex((b) => b.text.includes(ref)) : -1;
    if (section < 0) section = Math.max(0, Math.min((state.cursor || {}).block || 0, blocks.length - 1));
    const block = blocks[section] || { text: "" };
    const quote = (ref && block.text.includes(ref) ? ref : state.selection || block.text.slice(0, 80)).slice(0, 160);
    return { section, quote };
  }

  function reviewAnnoKind(item) {
    const s = String((item && item.standard) || "");
    if (/引用|出处|来源/.test(s)) return "quote";
    if (/事实|数据|真实/.test(s)) return "fact";
    if (/文字|错别|标点|语病|格式|排版/.test(s)) return "typo";
    if (/风险|蕴含/.test(s)) return "risk";
    return "ai";
  }

  async function addReviewComments(root, c, state, id, draw) {
    const msg = messageById(state, id), checks = U.$$(`[data-review-item^="${Number(id)}:"]:checked`, root);
    if (!(c.ownerId === Store.userId || Store.me().admin) || !msg || !msg.result) return true;
    msg.transferred = msg.transferred || new Set();
    let last = null;
    for (const box of checks) {
      const index = Number(box.dataset.reviewItem.split(":")[1]);
      const item = msg.result.items[index];
      if (!item || item.status === "pass" || msg.transferred.has(index)) continue;
      const anchor = reviewAnchor(c, item, state);
      last = await Store.addAnnotation(c, { kind: reviewAnnoKind(item),
        author: "AI 审校", text: `${item.standard}：${item.note}`, ...anchor });
      if (last) msg.transferred.add(index);
    }
    if (last) { state.annoId = last.id; state.tool = "comments"; state.selection = ""; draw(false); }
    return true;
  }

  function annotationAnchor(root, id) {
    return U.$$("[data-anno-ids]", root)
      .find((x) => x.dataset.annoIds.split(" ").includes(id));
  }

  function locateAnnotation(root, state, id) {
    const node = annotationAnchor(root, id);
    if (!node) { U.toast("正文已变化，批注锚点失效"); return true; }
    node.scrollIntoView({ behavior: "smooth", block: "center" });
    node.classList.add("flash");
    window.setTimeout(() => node.classList.remove("flash"), 1200);
    return true;
  }

  function openAnnotation(root, c, state, id, draw) {
    state.tool = "comments";
    state.annoId = id;
    draw(true);
    window.requestAnimationFrame(() => locateAnnotation(root, state, id));
    return true;
  }

  function navigateAnnotation(root, c, state, delta, draw) {
    const items = commentItems(c, state);
    if (!items.length) return true;
    const at = Math.max(0, items.findIndex((x) => x.id === state.annoId));
    const next = items[(at + delta + items.length) % items.length];
    return openAnnotation(root, c, state, next.id, draw);
  }

  async function replyAnnotation(root, c, id, draw) {
    const input = U.$(`[data-anno-reply="${id}"]`, root), text = (input && input.value || "").trim();
    if (!text) return true;
    const reopen = U.$(`[data-anno-reopen="${id}"]`, root);
    if (await Store.replyAnnotation(c, id, text, !!(reopen && reopen.checked))) draw(false);
    return true;
  }

  async function addAnnotation(root, c, state, draw) {
    const input = U.$("[data-anno-text]", root);
    const text = (input.value || "").trim();
    if (!text) return;
    const blocks = Store.blocksOf(c), section = Math.max(0,
      Math.min((state.cursor || {}).block || 0, blocks.length - 1));
    const quote = state.selection || ((blocks[section] || {}).text || "").slice(0, 80);
    const a = await Store.addAnnotation(c, { kind: "author", text, quote,
      author: Store.me().name, section });
    if (a) { state.annoId = a.id; state.selection = ""; state.tool = "comments"; draw(false); }
    return true;
  }

  async function resolveAnnotation(c, id, draw) {
    if (await Store.setAnnoStatus(c, id, "resolved")) draw(false);
  }

  async function setAnnoStatus(c, id, status, draw) {
    if (await Store.setAnnoStatus(c, id, status)) draw(false);
  }

  async function remountAnnotation(root, c, id, draw) {
    const a = (c.annotations || []).find((x) => x.id === id);
    if (!a || !a.quote) return true;
    captureDoc(root, c);
    const blocks = Store.blocksOf(c), hay = blocks.map((b) => b.text).join("\n");
    for (let len = Math.min(12, a.quote.length); len >= 4; len -= 2) {
      const probe = a.quote.slice(0, len), first = hay.indexOf(probe);
      if (first < 0 || hay.indexOf(probe, first + 1) >= 0) continue;
      let acc = 0, section = 0;
      for (let i = 0; i < blocks.length; i += 1) {
        if (first < acc + blocks[i].text.length + 1) { section = i; break; }
        acc += blocks[i].text.length + 1;
      }
      if (await Store.setAnnoStatus(c, id, "pending", { section })) {
        U.toast("批注已重新定位");
        draw(false);
      }
      return true;
    }
    U.toast("无法在正文中重新定位该批注");
    return true;
  }

  async function deleteAttachment(c, id, draw) {
    if (!(await U.confirmModal("移除此附件？"))) return;
    if (await Store.deleteCaseAttachment(c, id)) draw(false);
  }

  function escapeLinkLabel(label) {
    return String(label || "附件").replace(/\\/g, "\\\\")
      .replace(/\[/g, "\\[").replace(/\]/g, "\\]").replace(/\s*\n\s*/g, " ");
  }

  function attachmentMarker(a, label) {
    return `[${escapeLinkLabel(label || a.title || "附件")}](attachment:${a.id})`;
  }

  function attachmentLabel(c, state, a) {
    const point = state.cursor || {};
    if (state.selection && point.end > point.start) return state.selection;
    const index = (c.attachments || []).findIndex((x) => x.id === a.id);
    return `附件 ${Math.max(0, index) + 1}`;
  }

  function markedBlocks(c, state, marker) {
    const blocks = Store.blocksOf(c).map((b) => ({ kind: b.kind, text: b.text }));
    const point = state.cursor, block = point && blocks[point.block];
    if (!block) return blocks.concat({ kind: "p", text: marker });
    const start = Math.min(point.start, block.text.length);
    const end = Math.min(Math.max(point.end, start), block.text.length);
    block.text = block.text.slice(0, start) + marker + block.text.slice(end);
    state.cursor = { block: point.block, start: start + marker.length, end: start + marker.length };
    return blocks;
  }

  async function insertAttachment(c, state, id, draw) {
    const a = (c.attachments || []).find((x) => x.id === id);
    if (!a) return;
    c.blocks = markedBlocks(c, state, attachmentMarker(a, attachmentLabel(c, state, a)));
    state.selection = "";
    if (await Store.saveCaseNow(c, { blocks: c.blocks })) U.toast("已插入正文");
    draw(false);
  }

  async function deleteReference(c, id, draw) {
    c.caseRefs = (c.caseRefs || []).filter((x) => x.caseId !== id);
    await Store.saveCaseNow(c, { caseRefs: c.caseRefs });
    draw(false);
  }

  async function saveVersion(root, c, draw) {
    const input = U.$("[data-version-label]", root);
    if (await Store.saveVersion(c.id, input.value || "")) { U.toast("版本已保存"); draw(false); }
  }

  async function rollbackVersion(c, id, draw) {
    if (!(await U.confirmModal("回滚到此版本？"))) return;
    if (await Store.rollbackVersion(c.id, id)) draw(false);
  }

  function runCheck(c, state, draw) {
    state.tool = "check";
    state.checks = Store.selfChecks(c);
    state.aiCheck = "";
    draw(true);
    if (aiOff()) { state.aiCheck = Copilot.AI_NOT_CONFIGURED; draw(false); return; }
    Copilot.agent({ text: "提交前自检", intentHint: "review",
      caseContext: { id: c.id, title: c.title, blocks: Store.blocksOf(c), caseRefs: c.caseRefs || [] },
      onDone(r) { state.aiCheck = Copilot.agentResultText(r); draw(false); },
      onError(err) { state.aiCheck = err.message || String(err); draw(false); } });
  }

  async function submitCase(c, draw) {
    if (!(await U.confirmModal("提交当前版本审核？"))) return;
    if (await Store.submitCase(c)) { U.toast("已提交审核"); draw(false); }
  }

  async function exportCase(c) {
    const markdown = Store.blocksOf(c).map((b) => b.kind === "h2" ? "## " + b.text : b.text).join("\n\n");
    const resp = await fetch("/api/export-docx", { method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title: c.title, meta: { author: c.author || Store.me().name },
        parts: [{ heading: "案例正文", markdown }], refs: (c.caseRefs || []).map((r) => ({ title: r.title, source: r.versionLabel })) }) });
    if (!resp.ok) return U.toast("导出失败");
    U.download(c.title + ".docx", await resp.blob());
  }

  async function addCaseRef(c, id, draw) {
    if ((c.caseRefs || []).some((x) => x.caseId === id)) return;
    const target = Store.db.cases.find((x) => x.id === id), version = target && publicVersion(target);
    if (!target || !version) return U.toast("该案例没有可引用的公开版本");
    c.caseRefs = (c.caseRefs || []).concat({ caseId: id, versionId: version.id,
      title: target.title, versionLabel: version.label, at: U.now() });
    await Store.saveCaseNow(c, { caseRefs: c.caseRefs });
    U.toast("已引用案例");
    draw(false);
  }

  async function addResearchResult(c, state, index, draw) {
    const row = state.results[index];
    if (!row || row.locked) return;
    if (row.kind === "case") return addCaseRef(c, row.id, draw);
    const payload = row.kind === "web" ? await webAttachmentPayload(row.raw)
      : materialAttachmentPayload(row.raw);
    if (!payload) return;
    const a = await Store.addCaseAttachment(c, payload);
    if (!a) return;
    if (a.duplicate) {
      state.tool = "files"; state.flashAtt = a.id;
      U.toast("附件已存在（查重命中）");
      draw(false);
      state.flashAtt = "";
      return;
    }
    U.toast("已加入附件");
    draw(false);
  }

  async function webAttachmentPayload(row) {
    const fetched = await Copilot.fetchUrl(row.url);
    if (!fetched || !fetched.ok) { U.toast((fetched && fetched.error) || "网页采集失败"); return null; }
    return { title: fetched.title || row.title, kind: "网页", source: sourceHost(row.url),
      sourceUrl: row.url, text: fetched.text || "", data: fetched.data || "",
      fileName: fetched.fileName || "网页原文.txt",
      excerpt: (fetched.text || row.content || "").slice(0, 1200),
      mime: fetched.contentType || "text/plain" };
  }

  function sourceHost(url) {
    try { return new URL(url).hostname; } catch (e) { return url; }
  }

  function materialAttachmentPayload(m) {
    return { title: m.title, kind: m.kind || "文档", source: m.source,
      sourceUrl: m.sourceUrl, excerpt: m.excerpt || m.summary || "",
      originMaterialId: m.id, level: m.level, mime: "text/plain" };
  }
})();
