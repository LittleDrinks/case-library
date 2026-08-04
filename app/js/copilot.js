// Copilot：AI 对话、上下文组装、任务进度、内容采用
(function () {
  const C = {};

  const SYS_PROMPT = [
    "你是高校思政教学案例智能平台的备课助手，服务对象是高校思政课教师。",
    "你的能力（工具）范围：1. 检索平台知识库（《自然辩证法概论（2025版）》教材原文）；2. 检索素材库（按教师权限过滤后的登记素材）；3. 联网检索公开资源；4. 采集网页（保存内容副本）；5. 在教师确认后写入案例正文与教学材料；6. 审校正文并生成批注。除此之外你没有其他数据来源。",
    "写作方法：分析案例时运用四层价值坐标（个人成长、社会责任、国家战略、人类共同价值）和三层深挖法（事实是什么、为什么发生、意味着什么），使研讨既有事实厚度又有价值高度。",
    "要求：1. 一律使用中文，表达简练、书面化；2. 引用理论时注明出处（教材名与章节）；3. 只能使用对话上下文中提供的知识库摘录与素材列表，不得声称参考了上下文之外的文献库或来源；4. 信息缺失时以【待定】标注并说明缺什么，不得编造填补；5. 上下文标注「未命中」时，直接说明当前库中没有匹配内容，可建议教师改用联网检索补充公开来源；6. 需要输出成稿文字时直接给正文，不要解释你要做什么；7. 涉及敏感表述时提示更稳妥的表达方式。",
  ].join("\n");

  // 每个案例的会话内检索缓存，避免同一会话反复检索
  const sessionCache = {};

  // 案例内容变化后调用：删除该案例的上下文缓存条目（只清缓存，不动会话历史）
  C.invalidateContext = (caseId) => {
    Object.keys(sessionCache).forEach((k) => {
      if (k.indexOf(caseId + "|") === 0) delete sessionCache[k];
    });
  };

  // ---------------------------------------------------------- 基础调用
  C.ask = async (messages, opts) => {
    const res = await U.postJSON("/api/ai/chat", {
      messages,
      temperature: (opts && opts.temperature) != null ? opts.temperature : 0.7,
      max_tokens: opts && opts.max_tokens,
    });
    return res; // {ok, content, model, usage, elapsed_ms, error}
  };

  // AI 未配置（/api/constants 已存入 Store.flags）时前置拦截，不发请求
  const AI_NOT_CONFIGURED = "AI 服务未配置，请联系管理员在服务端 .env 配置 AI_BASE_URL / AI_API_KEY";
  C.AI_NOT_CONFIGURED = AI_NOT_CONFIGURED;
  const aiConfigured = () => !(typeof Store !== "undefined" && Store.flags && Store.flags.aiConfigured === false);

  // ---------------------------------------------------------- 多轮会话历史（仅内存，不落盘）
  const histories = new Map(); // conversationKey -> [{role, content, at}]
  const HISTORY_TURNS = 6;   // 最多带最近 6 轮（user+assistant 计一轮）
  const HISTORY_CHARS = 6000; // 历史总长硬上限，超出从最早丢弃

  // 截断：保留最近 maxTurns 轮且总长不超 maxChars；保证从 user 开始成对（导出以便单测）
  C._trimHistory = (list, maxTurns, maxChars) => {
    const out = (list || []).slice(-(maxTurns || HISTORY_TURNS) * 2);
    let total = 0;
    for (let i = out.length - 1; i >= 0; i--) {
      total += String(out[i].content || "").length;
      if (total > (maxChars || HISTORY_CHARS)) { out.splice(0, i + 1); break; }
    }
    while (out.length && out[0].role !== "user") out.shift();
    return out;
  };

  C.getHistory = (key) => (histories.get(key) || []).slice();
  C.clearHistory = (key) => { histories.delete(key); };
  // 一轮成功后记录（chat/chatStream 内部已调用，页面亦可手动补记）
  C.appendTurn = (key, userText, assistantText) => {
    if (!key) return;
    const list = histories.get(key) || [];
    const at = U.now();
    list.push({ role: "user", content: String(userText || ""), at });
    list.push({ role: "assistant", content: String(assistantText || ""), at });
    histories.set(key, C._trimHistory(list, HISTORY_TURNS, HISTORY_CHARS));
  };

  const lastUserText = (messages) => {
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i].role === "user") return String(messages[i].content || "");
    }
    return "";
  };

  // 单轮对话（非流式兼容路径）：传 opts.messages 直接发，或传 c/focusIdx/text/intent 由 buildMessages 组装；
  // 有 conversationKey 时自动携带并记录历史。返回 {ok, content, model, usage, sources, error?}
  C.chat = async (opts) => {
    opts = opts || {};
    if (!aiConfigured()) return { ok: false, error: AI_NOT_CONFIGURED };
    let messages = opts.messages;
    let sources = opts.sources || [];
    if (!messages) {
      messages = await C.buildMessages(opts.c, opts.focusIdx, opts.text || "", opts.intent || "chat", opts.skipDirective, opts.conversationKey);
      sources = C.lastSources || [];
    }
    const res = await C.ask(messages, opts);
    if (res.ok && opts.conversationKey) {
      C.appendTurn(opts.conversationKey, opts.text != null ? opts.text : lastUserText(messages), res.content);
    }
    res.sources = sources;
    return res;
  };

  // ---------------------------------------------------------- 流式对话（SSE）
  // 解析 SSE 缓冲：按空行切帧，收集 data: 负载；返回 {frames, rest}，rest 为未完成残帧（导出以便单测）
  C._parseSSE = (buffer) => {
    const frames = [];
    const parts = String(buffer || "").split(/\r?\n\r?\n/);
    const rest = parts.pop();
    parts.forEach((block) => {
      const data = block.split(/\r?\n/)
        .filter((l) => l.startsWith("data:"))
        .map((l) => l.slice(5).replace(/^ /, ""))
        .join("\n");
      if (data) frames.push(data);
    });
    return { frames, rest };
  };

  // 流式单轮：opts 同 chat，另加 onToken(累计全文) / onDone(fullText, meta) / onError(err)。
  // 流式建立失败（网络错误/非 200/非 SSE）且尚未产出 token 时自动回退非流式 chat 链路。
  // 返回 { abort(), done } 句柄，页面切换时可 abort() 取消（取消不触发 onError）。
  C.chatStream = (opts) => {
    opts = opts || {};
    const controller = new AbortController();
    const onToken = opts.onToken || function () {};
    const onDone = opts.onDone || function () {};
    const onError = opts.onError || function () {};
    let settled = false;
    const fail = (err) => {
      if (settled) return;
      settled = true;
      onError(err instanceof Error ? err : new Error(String(err || "模型调用失败")));
    };
    const succeed = (text, meta) => {
      if (settled) return;
      settled = true;
      onDone(text, meta || {});
    };

    const done = (async () => {
      if (!aiConfigured()) { fail(AI_NOT_CONFIGURED); return; }
      let messages = opts.messages;
      let sources = opts.sources || [];
      if (!messages) {
        messages = await C.buildMessages(opts.c, opts.focusIdx, opts.text || "", opts.intent || "chat", opts.skipDirective, opts.conversationKey);
        sources = C.lastSources || [];
      }
      const finish = (text, meta) => {
        if (opts.conversationKey) {
          C.appendTurn(opts.conversationKey, opts.text != null ? opts.text : lastUserText(messages), text);
        }
        succeed(text, Object.assign({ sources }, meta));
      };
      // 非流式回退，保证可用性
      const fallback = async () => {
        try {
          const res = await C.ask(messages, opts);
          if (res.ok) {
            onToken(res.content);
            finish(res.content, { model: res.model, usage: res.usage, fallback: true });
          } else fail(res.error);
        } catch (e) { fail(e && e.message ? e.message : e); }
      };

      let resp;
      try {
        resp = await fetch("/api/ai/chat", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            messages,
            stream: true,
            temperature: opts.temperature != null ? opts.temperature : 0.7,
            max_tokens: opts.max_tokens,
          }),
          signal: controller.signal,
        });
      } catch (e) {
        if (controller.signal.aborted) return;
        await fallback();
        return;
      }
      const ctype = (resp && resp.headers && resp.headers.get("Content-Type")) || "";
      if (!resp.ok || !resp.body || !ctype.includes("text/event-stream")) { await fallback(); return; }

      let acc = "";
      const meta = {};
      let ended = false; // 收到 [DONE] 或 error 帧
      const handleFrame = (frame) => {
        if (frame === "[DONE]") { ended = true; return; }
        let j;
        try { j = JSON.parse(frame); } catch (e) { return; } // 忽略坏帧
        if (j && j.error) { ended = true; fail(j.error); return; }
        const delta = j && j.choices && j.choices[0] && j.choices[0].delta && j.choices[0].delta.content;
        if (delta) { acc += delta; onToken(acc); }
        if (j && j.model) meta.model = j.model;
        if (j && j.usage) meta.usage = j.usage;
      };
      try {
        const reader = resp.body.getReader();
        const decoder = new TextDecoder("utf-8");
        let buf = "";
        for (;;) {
          const r = await reader.read();
          if (r.done) break;
          buf += decoder.decode(r.value, { stream: true });
          const parsed = C._parseSSE(buf);
          buf = parsed.rest;
          for (const frame of parsed.frames) {
            handleFrame(frame);
            if (settled || ended) break;
          }
          if (settled || ended) break;
        }
      } catch (e) {
        if (controller.signal.aborted) return;
        if (!acc && !settled) { await fallback(); return; } // 未产出任何 token，回退保底
        fail(e && e.message ? e.message : e);
        return;
      }
      if (settled) return; // error 帧已走 onError
      if (acc) finish(acc, meta);
      else await fallback(); // 流空结束（未产出 token），回退保底
    })();

    return { abort: () => controller.abort(), done };
  };

  // ---------------------------------------------------------- 统一 Agent 端点（SSE）
  // 服务端多智能体编排的单入口：主Agent 路由 → 资料管理员/写作手/审校员。
  // 帧类型：role / tool / token / result(candidates|text|review) / done / error，未知类型忽略。
  // opts：{text, intentHint?, caseContext?, selection?, history?, conversationKey?,
  //        onRole, onTool, onToken, onResult, onDone(result), onError}，返回 { abort(), done }。
  C.agent = (opts) => {
    opts = opts || {};
    const controller = new AbortController();
    const onRole = opts.onRole || function () {};
    const onTool = opts.onTool || function () {};
    const onToken = opts.onToken || function () {};
    const onResult = opts.onResult || function () {};
    const onDone = opts.onDone || function () {};
    const onError = opts.onError || function () {};
    let settled = false, ended = false;
    const fail = (err) => {
      if (settled) return;
      settled = true;
      onError(err instanceof Error ? err : new Error(String(err || "Agent 调用失败")));
    };

    const done = (async () => {
      if (!aiConfigured()) { fail(AI_NOT_CONFIGURED); return; }
      const history = opts.history ||
        (opts.conversationKey ? C.getHistory(opts.conversationKey).map((h) => ({ role: h.role, content: h.content })) : []);
      let resp;
      try {
        resp = await fetch("/api/ai/agent", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            text: opts.text || "",
            intentHint: opts.intentHint || undefined,
            caseContext: opts.caseContext || null,
            selection: opts.selection,
            history,
          }),
          signal: controller.signal,
        });
      } catch (e) {
        if (controller.signal.aborted) return;
        fail(e && e.message ? e.message : e);
        return;
      }
      const ctype = (resp && resp.headers && resp.headers.get("Content-Type")) || "";
      if (!resp.ok || !resp.body || !ctype.includes("text/event-stream")) {
        let msg = "Agent 服务异常（HTTP " + (resp ? resp.status : "?") + "）";
        try { const j = await resp.json(); if (j && j.error) msg = j.error; } catch (e) { /* ignore */ }
        fail(msg);
        return;
      }

      let result = null;
      let mainAcc = ""; // main 流累计，兜底用于历史记录与隐式结果
      const handleFrame = (frame) => {
        let j;
        try { j = JSON.parse(frame); } catch (e) { return; } // 忽略坏帧
        if (!j || !j.type) return;
        if (j.type === "role") onRole(j);
        else if (j.type === "tool") onTool(j);
        else if (j.type === "token") { if (j.which !== "alt") mainAcc += j.text || ""; onToken(j); }
        else if (j.type === "result") { result = j; onResult(j); }
        else if (j.type === "done") ended = true;
        else if (j.type === "error") { ended = true; fail(j.message || "Agent 调用失败"); }
        // 未知帧类型忽略，不报错
      };
      try {
        const reader = resp.body.getReader();
        const decoder = new TextDecoder("utf-8");
        let buf = "";
        for (;;) {
          const r = await reader.read();
          if (r.done) break;
          buf += decoder.decode(r.value, { stream: true });
          const parsed = C._parseSSE(buf);
          buf = parsed.rest;
          for (const frame of parsed.frames) {
            handleFrame(frame);
            if (settled || ended) break;
          }
          if (settled || ended) break;
        }
        // 流结束时兜底冲刷残帧（末尾缺少空行分隔的情况）
        if (!settled && !ended && buf.trim()) {
          const parsed = C._parseSSE(buf + "\n\n");
          for (const frame of parsed.frames) {
            handleFrame(frame);
            if (settled || ended) break;
          }
        }
      } catch (e) {
        if (controller.signal.aborted) return;
        fail(e && e.message ? e.message : e);
        return;
      }
      if (settled) return; // error 帧已走 onError
      settled = true;
      const finalResult = result || (mainAcc ? { kind: "text", text: mainAcc } : null);
      // 会话历史由本函数内部 appendTurn 记录，页面不再重复补记；无结果不记空轮次
      if (opts.conversationKey && finalResult) {
        C.appendTurn(opts.conversationKey, opts.text || "", C.agentResultText(finalResult));
      }
      onDone(finalResult);
    })();

    return { abort: () => controller.abort(), done };
  };

  // result 帧提取纯文本（会话历史记录与任务摘要共用）
  C.agentResultText = (r) => {
    if (!r) return "";
    if (r.kind === "candidates") return (r.main && r.main.text) || "";
    if (r.kind === "review") {
      return (r.items || []).map((it) => "[" + (it.standard || "") + "] " + (it.note || "")).join("\n");
    }
    return r.text || "";
  };

  // ---------------------------------------------------------- 上下文组装
  function snippet(text, q, len) {
    const t = String(text || "").replace(/\s+/g, " ").trim();
    if (!q) return t.slice(0, len);
    const at = t.indexOf(q);
    if (at < 0) return t.slice(0, len);
    return "…" + t.slice(Math.max(0, at - len / 2), at + len / 2) + "…";
  }

  // 取当前小节及其前后各一节作为关注窗口，其余小节只给标题
  C.buildContext = async (c, focusIdx, query) => {
    const cacheKey = c.id + "|" + (query || "").slice(0, 40);
    let retrieved = sessionCache[cacheKey];
    let fallbackUsed = false;
    if (!retrieved) {
      const q = [query, c.title, (c.theoryPoints || []).join(" ")].filter(Boolean).join(" ");
      const r = await Store.search(q, {});
      retrieved = { knowledge: r.knowledge.slice(0, 3), materials: r.materials.slice(0, 3) };
      sessionCache[cacheKey] = retrieved;
    }
    // 检索命中不足时，用素材库中权威度最高、最近的素材兜底，保证模型总能看到真实列表
    let materials = retrieved.materials.map((r) => r.item);
    if (materials.length < 3) {
      fallbackUsed = true;
      const pool = Store.visibleMaterials().slice()
        .sort((a, b) => (b.credibility === "high") - (a.credibility === "high") ||
          String(b.collectedAt).localeCompare(String(a.collectedAt)));
      for (const m of pool) {
        if (materials.length >= 4) break;
        if (!materials.find((x) => x.id === m.id)) materials.push(m);
      }
    }
    const lines = [];
    lines.push("【当前案例】标题：" + c.title +
      "；类型：" + Store.typeName(c.typeId) +
      "；教学对象：" + Store.audienceName(c.audience) +
      "；课程：" + (c.course || "未定") + "；用途：" + (c.purpose || "日常授课"));
    if (c.summary) lines.push("【案例概述】" + c.summary);

    // 逻辑小节：以 h2 标题为界，当前光标所在小节 ±1 作为关注窗口
    const bs = Store.blocksOf(c);
    const secs = [];
    let cur = { title: "", text: [], from: 0, to: bs.length };
    bs.forEach((b, i) => {
      if (b.kind === "h2") {
        cur.to = i;
        if (cur.to > cur.from) secs.push(cur);
        cur = { title: b.text, text: [], from: i, to: bs.length };
      } else cur.text.push(b.text);
    });
    if (cur.to > cur.from) secs.push(cur);
    if (!secs.length) secs.push({ title: "", text: [], from: 0, to: bs.length });
    let fi = secs.findIndex((s) => (focusIdx || 0) >= s.from && (focusIdx || 0) < s.to);
    if (fi < 0) fi = 0;
    lines.push("【案例结构】" + (bs.length ? secs.map((s, i) => (i + 1) + "." + (s.title || "（开头）")).join("；") : "（空白）"));
    for (let i = Math.max(0, fi - 1); i <= Math.min(secs.length - 1, fi + 1); i++) {
      const body = secs[i].text.join("\n");
      lines.push("【" + (i === fi ? "当前小节" : "相邻小节") + "：" + (secs[i].title || "（开头）") + "】\n" + (body || "（空白）"));
    }
    if ((c.citations || []).length) {
      lines.push("【本案例已有引用】");
      c.citations.forEach((r, i) => {
        const kn = Store.knowledgeById(r.target);
        const m = kn ? null : Store.materialById(r.target);
        if (kn) lines.push(`〔${i + 1}〕知识：${kn.chapter} ${kn.title}${r.note ? "（" + r.note + "）" : ""}`);
        else if (m) lines.push(`〔${i + 1}〕素材：${m.title}（${m.source}，${m.credibility === "high" ? "权威来源" : m.credibility === "low" ? "待核实" : "一般来源"}）${r.note ? "（" + r.note + "）" : ""}`);
      });
    }
    if (retrieved.knowledge.length) {
      lines.push("【知识库相关摘录（《自然辩证法概论（2025版）》）】");
      retrieved.knowledge.forEach((r, i) => {
        lines.push((i + 1) + ". " + r.item.chapter + " " + r.item.title + "：" + snippet(r.item.text, (r.reasons[0] || "").split("「")[1], 260));
      });
    } else {
      lines.push("【知识库检索】未命中与当前需求直接相关的教材章节。");
    }
    if (materials.length) {
      lines.push(fallbackUsed && !retrieved.materials.length
        ? "【素材库检索】未命中直接相关素材；以下为素材库中权威度最高的素材，仅供一般参考："
        : "【可用素材（已按教师权限过滤）】");
      materials.forEach((m, i) => {
        lines.push((i + 1) + ". " + m.title + "（" + m.source + "，" +
          (m.credibility === "high" ? "权威来源" : m.credibility === "low" ? "待核实" : "一般来源") + "）：" +
          snippet(m.excerpt || m.summary, null, 200));
      });
    }
    // 本轮引用的来源列表（知识 topN + 素材，编号连续），供页面渲染来源 chips 与 U.linkifyCitations
    const sources = [];
    retrieved.knowledge.forEach((r) => sources.push({ n: sources.length + 1, type: "knowledge", id: r.item.id, title: r.item.chapter + " " + r.item.title }));
    materials.forEach((m) => sources.push({ n: sources.length + 1, type: "material", id: m.id, title: m.title }));
    C.lastSources = sources;
    return lines.join("\n");
  };

  // ---------------------------------------------------------- 快捷指令
  // scene：write=作者写作，review=审核员审校，prep=案例详情页备课生成
  C.quickCommands = (c, scene) => {
    const aud = c ? c.audience : Store.me().audience;
    const mk = (label, intent) => ({ label, intent, prompt: (INTENT_PROMPT[intent] || "").trim() });
    if (scene === "prep") {
      return [mk("生成教学设计", "kit-design"), mk("生成讨论题", "kit-discussion"), mk("生成 PPT 提纲", "kit-ppt")];
    }
    if (scene === "review") {
      return [
        mk("AI 辅助审校", "review"),
        mk("核查理论依据", "find-theory"),
        mk("核查权威素材", "find-material"),
      ];
    }
    const common = [
      mk("查找理论依据", "find-theory"),
      mk("查找权威素材", "find-material"),
      mk("检查引用与错别字", "review"),
      mk("润色当前节", "polish"),
    ];
    if (aud === "grad") common.push(mk("改成研究生20分钟小组研讨版", "adapt-grad"));
    if (aud === "ug") common.push(mk("改成本科课堂讲授版", "adapt-ug"));
    if (aud === "embed") common.push(mk("生成专业课嵌入式教学片段", "adapt-embed"));
    return common;
  };

  const INTENT_STAGES = {
    "find-theory": ["解析需求", "检索知识库", "整理理论依据", "完成"],
    "find-material": ["解析需求", "检索素材库", "核验来源可信度", "完成"],
    review: ["读取当前节", "检查引用", "检查文字与格式", "汇总问题清单"],
    polish: ["读取当前节", "润色改写", "校对", "完成"],
    "kit-design": ["分析案例结构", "生成教学目标与流程", "整理成稿", "完成"],
    "kit-discussion": ["分析案例矛盾点", "生成分层讨论题", "整理成稿", "完成"],
    "kit-ppt": ["分析案例结构", "生成提纲", "整理成稿", "完成"],
    "adapt-grad": ["分析当前内容", "按研究生研讨课重构", "调整研讨问题深度", "完成"],
    "adapt-ug": ["分析当前内容", "按本科课堂重构", "调整表达与节奏", "完成"],
    "adapt-embed": ["分析当前内容", "生成嵌入式教学片段", "完成"],
    draft: ["检索相关知识", "查找可用素材", "生成初稿", "校对引用", "完成"],
    chat: ["理解问题", "组织回答", "完成"],
  };

  const INTENT_PROMPT = {
    "find-theory": "教师需要理论支撑。请结合知识库摘录，列出本案例可引用的理论依据：每条给出教材章节、核心观点一句话、在案例中的使用位置建议。",
    "find-material": "教师需要素材。请结合可用素材列表，说明每条素材可支撑案例的哪个部分、可信度如何、使用时要注意什么；素材不足时直说。",
    review: "请审校【当前小节】：1. 引用与事实是否有着落；2. 错别字、标点、格式问题；3. 表述风险。按如下格式逐条输出（不要输出其他内容）：\n[问题类型] 原文片段 | 问题说明 | 修改建议\n问题类型取：引用 / 事实 / 文字 / 格式 / 风险",
    polish: "请润色【当前小节】的正文，保持原意与结构，提升书面表达质量。直接输出润色后的正文。",
    "kit-design": "请为本案例生成教学设计（教案）：含教学目标（知识/能力/价值三个维度）、课前准备、课堂流程（含时间安排）、板书要点、课后延伸。结合教学对象特点控制深度。",
    "kit-discussion": "请为本案例生成课堂讨论题 4-6 题：由浅入深分层，至少 1 题关联教材理论，注明每题适合的讨论形式（全班/小组/辩论）。",
    "kit-ppt": "请为本案例生成授课 PPT 提纲：每页一行，格式为“页码. 标题 —— 要点”，12-18 页，含导入、正文、讨论、总结页。",
    "adapt-grad": "请把【当前小节】改写为研究生 20 分钟小组研讨课版本：压缩叙述性文字，突出矛盾设置与可争论点，并在末尾给出 2-3 个递进的研讨问题。",
    "adapt-ug": "请把【当前小节】改写为本科课堂讲授版本：语言通俗、节奏明快，保留核心事实与价值点，末尾给出 1-2 个课堂提问。",
    "adapt-embed": "请基于本案例生成一段可嵌入专业课的思政教学片段（300 字以内），自然衔接专业内容，不喊口号。",
    draft: "请根据教师的要求生成案例内容，直接输出成稿。",
    chat: "",
  };

  C.stagesFor = (intent) => (INTENT_STAGES[intent] || INTENT_STAGES.chat).slice();

  // 组装发给模型的消息；skipDirective 用于快捷指令文案已在输入框中的情况。
  // 传 conversationKey 时：system + 上下文之后插入该会话最近若干轮历史，最后放当前 user。
  C.buildMessages = async (c, focusIdx, userText, intent, skipDirective, conversationKey) => {
    const ctx = await C.buildContext(c, focusIdx, userText);
    const directive = skipDirective ? "" : (INTENT_PROMPT[intent] || "");
    const prefs = Store.me().prefs || {};
    const prefLine = "教师偏好：语言风格" + (prefs.style || "简练") +
      (prefs.authorityFirst ? "；优先权威来源" : "") +
      (prefs.classForm ? "；常用课堂形式：" + prefs.classForm : "");
    const requirement = "【教师要求】" + (directive ? directive + "\n" : "") + userText;
    if (!conversationKey) {
      const user = ctx + "\n" + prefLine + "\n" + requirement;
      return [
        { role: "system", content: SYS_PROMPT },
        { role: "user", content: user },
      ];
    }
    const msgs = [
      { role: "system", content: SYS_PROMPT },
      { role: "user", content: ctx + "\n" + prefLine },
    ];
    (histories.get(conversationKey) || []).forEach((h) => {
      msgs.push({ role: h.role, content: h.content });
    });
    msgs.push({ role: "user", content: requirement });
    return msgs;
  };

  // ---------------------------------------------------------- 审校结果解析为批注
  C.parseReview = (c, content) => {
    const annos = [];
    const lines = String(content || "").split("\n").map((l) => l.trim()).filter(Boolean);
    for (const ln of lines) {
      const m = ln.match(/^[-*\d.、\s]*\[?(引用|事实|文字|格式|风险)\]?\s*[:：]?\s*(.+)$/);
      if (!m) continue;
      const parts = m[2].split("|").map((s) => s.trim());
      if (parts.length < 2) continue;
      const quote = (parts[0] || "").replace(/^[“"']|[”"']$/g, "");
      let section = -1;
      if (quote) {
        Store.blocksOf(c).forEach((b, i) => {
          if (section < 0 && b.text.includes(quote.slice(0, 20))) section = i;
        });
      }
      annos.push({
        kind: m[1] === "风险" ? "risk" : "ai",
        status: "pending",
        section: Math.max(0, section),
        quote: quote.slice(0, 60),
        text: "【" + m[1] + "】" + parts[1] + (parts[2] ? "；建议：" + parts[2] : ""),
        author: "Copilot",
        lowRisk: m[1] === "文字" || m[1] === "格式",
      });
    }
    return annos;
  };

  // ---------------------------------------------------------- 链接采集与联网检索
  C.fetchUrl = async (url) => U.postJSON("/api/fetch-url", { url });
  C.webSearch = async (query, maxResults) => U.postJSON("/api/web-search", { query, max_results: maxResults || 6 });

  // 依据白名单判定可信度
  C.credibilityFor = (url) => {
    try {
      const host = new URL(url).hostname;
      if (Store.db.whitelist.some((d) => host === d || host.endsWith("." + d))) return "high";
    } catch (e) { /* ignore */ }
    return "low";
  };

  // 查询理解：把自然语言查询改写成核心词 + 扩展词（LLM query rewrite）
  C.expandQuery = async (q) => {
    const res = await C.ask([
      { role: "system", content: "你是中文检索查询理解器。把用户的自然语言查询改写为检索词，只输出 JSON：{\"core\":[1-3个核心词],\"expand\":[2-6个同义词/上位词/相关词]}，不要输出任何其他内容。词长 2-6 字，面向高校思政教学案例库（主题含科技报国、课程思政、自然辩证法、科学家精神、交叉创新等）。" },
      { role: "user", content: q },
    ], { temperature: 0.1, max_tokens: 150 });
    if (!res.ok) return res;
    try {
      const m = res.content.match(/\{[\s\S]*\}/);
      const j = JSON.parse(m[0]);
      const clean = (arr) => (Array.isArray(arr) ? arr : []).map((x) => String(x).trim()).filter((x) => x.length >= 2 && x.length <= 10).slice(0, 8);
      return { ok: true, core: clean(j.core), expand: clean(j.expand) };
    } catch (e) {
      return { ok: false, error: "查询理解结果解析失败" };
    }
  };

  // 检索页 AI 回答：基于平台授权资源直接回答问题，句末标注资源编号
  C.answerQuery = async (q, results) => {
    const pool = [];
    results.cases.slice(0, 5).forEach((r) => pool.push({ kind: "案例", id: r.item.id, title: r.item.title, snippet: (r.item.summary || "").slice(0, 90) }));
    results.knowledge.slice(0, 5).forEach((r) => pool.push({ kind: "知识", id: r.item.id, title: r.item.chapter + " " + r.item.title, snippet: r.item.text.replace(/\s+/g, " ").slice(0, 90) }));
    results.materials.slice(0, 5).forEach((r) => pool.push({ kind: "素材", id: r.item.id, title: r.item.title, snippet: (r.item.excerpt || r.item.summary || "").replace(/\s+/g, " ").slice(0, 90) }));
    const numbered = pool.map((p, i) => `〔${i + 1}〕${p.kind}｜${p.title}｜${p.snippet}`).join("\n");
    const res = await C.ask([
      { role: "system", content: [
        "你是高校思政教学案例智能平台的检索助手，作用类似搜索引擎顶部的 AI 摘要。",
        "基于给出的平台资源回答用户问题：1. 先一两句直接回答（是什么、背景、要点）；2. 再分点展开：平台里有哪些可用资源、各自能支撑什么；3. 引用具体资源时在句末标注〔编号〕；4. 只能使用资源中的事实，平台资源未覆盖的部分明说，并可用常识简要补充（标注「通用知识」）；5. 中文、简练。",
      ].join("\n") },
      { role: "user", content: `用户问题：${q}\n\n平台资源（编号｜类型｜标题｜摘录）：\n${numbered || "（平台内未检索到相关资源）"}` },
    ], { temperature: 0.3, max_tokens: 900 });
    return { res, pool };
  };

  // ---------------------------------------------------------- 采纳 AI 内容时落地引用（WP3）
  // 结果文本中的〔n〕落成真实 citations：quote=所在句原文，evidence 从本次检索 chunk 填充；
  // 服务端后处理已把对不上 chunk 的编号改写为〔n·待核实〕（不匹配本正则），其 risks 由调用方转 risk 批注。
  const sentenceAt = (text, pos) => {
    const t = String(text || "");
    let s = Math.max(t.lastIndexOf("。", pos - 1), t.lastIndexOf("！", pos - 1),
      t.lastIndexOf("？", pos - 1), t.lastIndexOf("\n", pos - 1)) + 1;
    let e = t.length;
    for (const p of ["。", "！", "？", "\n"]) {
      const q = t.indexOf(p, pos);
      if (q >= 0 && q < e) e = q + 1;
    }
    return t.slice(s, e).replace(/〔\d+[^〕]*〕/g, "").trim().slice(0, 120);
  };

  C.materializeCitations = (c, msg) => {
    const chunks = (msg && msg.chunks) || [];
    if (!chunks.length) return [];
    const byN = {};
    chunks.forEach((ch) => { byN[Number(ch.n)] = ch; });
    const added = [];
    const re = /〔(\d+)〕/g;
    let m;
    while ((m = re.exec(msg.text || ""))) {
      const ch = byN[Number(m[1])];
      if (!ch) continue;
      const target = ch.materialId || ch.id;
      if (!target || Store.isCited(c, target)) continue;
      Store.cite(c, target, {
        quote: sentenceAt(msg.text, m.index),
        evidence: { materialId: target, sec: ch.sec || "",
                    snippet: ch.snippet || "", capturedAt: U.now() },
      });
      added.push(target);
    }
    return added;
  };

  window.Copilot = C;
})();
