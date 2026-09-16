// 只在服务端运行。从主仓 .env 读取 AI_BASE_URL / AI_API_KEY / AI_MODELS /
// AI_DEFAULT_MODEL / AI_TIMEOUT_SECONDS；不打印值，不回传密钥。
// 参考 backend/app/modules/ai/thinking.py 的官方思考型号清单（qwen 系）。
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

// 候选 worktree 没有 .env；按主控授权读取主仓根目录 .env。
const ENV_CANDIDATES = [
  "/home/q2635/wsl-workspace/case-library-v2/.env",
];
const ENV_FILE = ENV_CANDIDATES.find((file) => fs.existsSync(file)) || ENV_CANDIDATES[0];
const MAX_BODY = 512 * 1024;
const DEFAULT_EVENT_FILE = path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "events.log");

const HYBRID_THINKING = new Set([
  "qwen-plus", "qwen-plus-latest", "qwen-flash", "qwen-flash-latest",
  "qwen-turbo", "qwen-turbo-latest",
  "qwen3-max", "qwen3-max-preview", "qwen3-max-2026-01-23",
  "qwen3.5-plus", "qwen3.5-plus-2026-02-15",
  "qwen3.5-flash", "qwen3.5-flash-2026-02-23",
  "qwen3.6-max-preview", "qwen3.6-plus", "qwen3.6-plus-2026-04-02",
  "qwen3.6-flash", "qwen3.6-flash-2026-04-16",
  "qwen3.7-max", "qwen3.7-max-2026-05-20", "qwen3.7-max-2026-06-08",
  "qwen3.7-plus", "qwen3.7-plus-2026-05-26",
  "qwen3.7-flash", "qwen3.7-flash-2026-07-15",
  "qwen3.8-max", "qwen3.8-max-0902", "qwen3.8-flash",
]);
const THINKING_ONLY = new Set(["qwq-plus", "qwen3.7-max-preview", "qwen3.7-max-2026-05-17", "qwen3.8-2.4t-a95b"]);
const SNAPSHOT = /^(qwen-(?:plus|flash|turbo))-(\d{4})-(\d{2})-(\d{2})$/;
const SNAPSHOT_FLOORS = { "qwen-plus": [2025, 4, 28], "qwen-flash": [2025, 7, 28] };

function hybridSnapshot(model) {
  const match = SNAPSHOT.exec(model);
  const floor = match && SNAPSHOT_FLOORS[match[1]];
  if (!floor) return false;
  return match.slice(2).map(Number) >= floor;
}

export function thinkingSupported(model) {
  const name = String(model || "").trim();
  return HYBRID_THINKING.has(name) || THINKING_ONLY.has(name) || hybridSnapshot(name);
}

function loadEnv() {
  const raw = fs.readFileSync(ENV_FILE, "utf8");
  const values = {};
  for (const line of raw.split("\n")) {
    const match = /^([A-Z_]+)=(.*)$/.exec(line.trim());
    if (match) values[match[1]] = match[2].trim().replace(/^["']|["']$/g, "");
  }
  return values;
}

function resolveTarget(baseUrl) {
  const url = new URL(baseUrl);
  return { origin: url.origin, basePath: url.pathname.replace(/\/$/, "") };
}

function redactText(value, config) {
  let text = String(value ?? "");
  for (const secret of [config?.apiKey, config?.target?.origin, config?.target?.basePath].filter(Boolean)) {
    text = text.split(secret).join("<REDACTED>");
  }
  return text
    .replace(/Bearer\s+[^\s"']+/gi, "Bearer <REDACTED>")
    .replace(/(["']?(?:api[_-]?key|authorization|base[_-]?url)["']?\s*[:=]\s*)("[^"]*"|'[^']*'|[^\s,}]+)/gi, "$1<REDACTED>");
}

function logText(value, config) {
  return redactText(value, config);
}

function sampleMessages(messages, config) {
  return (Array.isArray(messages) ? messages : []).map((message) => ({
    role: message?.role,
    content: redactText(message?.content, config),
  }));
}

function logEvent(entry) {
  const file = process.env.PROTOTYPE_EVIDENCE_DIR
    ? path.join(process.env.PROTOTYPE_EVIDENCE_DIR, "ai-events.jsonl")
    : DEFAULT_EVENT_FILE;
  const line = `${new Date().toISOString()} ${JSON.stringify(entry)}\n`;
  try {
    fs.mkdirSync(path.dirname(file), { recursive: true });
    fs.appendFileSync(file, line);
  } catch { /* 日志失败不影响请求 */ }
}

function configError(res, code, message) {
  res.statusCode = 503;
  res.setHeader("content-type", "application/json; charset=utf-8");
  res.end(JSON.stringify({ error: "ai-unavailable", code, message }));
}

function readConfig() {
  const env = loadEnv();
  if (!env.AI_BASE_URL || !env.AI_API_KEY) throw new Error("env-missing");
  const config = {
    target: resolveTarget(env.AI_BASE_URL), apiKey: env.AI_API_KEY,
    timeoutMs: (Number(env.AI_TIMEOUT_SECONDS) || 60) * 1000,
    models: (env.AI_MODELS || "").split(",").map((s) => s.trim()).filter(Boolean),
    defaultModel: env.AI_DEFAULT_MODEL || "",
  };
  console.log(`[prototype-ai] target=locked base-url-configured=yes models=${config.models.length} default-configured=${Boolean(config.defaultModel)}`);
  return config;
}

async function readJson(req, res) {
  const chunks = [];
  let size = 0;
  for await (const chunk of req) {
    size += chunk.length;
    if (size > MAX_BODY) { configError(res, "body-too-large", "请求体过大"); return null; }
    chunks.push(chunk);
  }
  try { return JSON.parse(Buffer.concat(chunks).toString("utf8")); } catch {
    configError(res, "bad-json", "请求体不是合法 JSON"); return null;
  }
}

function sendConfig(res, config) {
  res.setHeader("content-type", "application/json; charset=utf-8");
  res.end(JSON.stringify({
    models: config.models, defaultModel: config.defaultModel,
    thinking: Object.fromEntries(config.models.map((m) => [m, thinkingSupported(m)])),
  }));
}

function makeChatState(req, res, config, body, model) {
  const controller = new AbortController();
  let clientClosed = Boolean(req.aborted);
  const abort = () => { clientClosed = true; controller.abort(); };
  req.once("aborted", abort);
  res.once("close", () => { if (!res.writableEnded) abort(); });
  return {
    controller, started: Date.now(), model, config,
    request: sampleMessages(body.messages, config),
    clientClosed: () => clientClosed, timedOut: false,
  };
}

function createUpstreamBody(body, model) {
  const upstreamBody = { model, messages: body.messages, stream: true };
  if (body.thinking && thinkingSupported(model)) upstreamBody.enable_thinking = true;
  return upstreamBody;
}

async function pipeStream(upstream, res, state) {
  const reader = upstream.body.getReader();
  const decoder = new TextDecoder();
  let bytes = 0; let full = ""; let done = false;
  while (true) {
    const item = await reader.read();
    if (item.done) break;
    bytes += item.value.length;
    full += decoder.decode(item.value, { stream: true });
    state.partial = full; // 取消/失败时 proxyError 据此保留已收到部分
    done ||= full.includes("data: [DONE]");
    if (!res.destroyed) res.write(item.value);
  }
  return { bytes, full, done };
}

function logChat(state, details) {
  logEvent({ kind: "chat", model: state.model, request: state.request, ms: Date.now() - state.started, ...details });
}

async function upstreamFailure(res, upstream, state) {
  const response = logText(await upstream.text().catch(() => ""), state.config);
  logChat(state, { outcome: "upstream-error", status: upstream.status, response });
  res.statusCode = 502;
  res.setHeader("content-type", "application/json; charset=utf-8");
  res.end(JSON.stringify({ error: "upstream", status: upstream.status, message: "真实模型上游请求失败，详情已脱敏记录" }));
}

async function proxyChat(res, state, body) {
  const upstream = await fetch(`${state.config.target.origin}${state.config.target.basePath}/chat/completions`, {
    method: "POST",
    headers: { "content-type": "application/json", authorization: `Bearer ${state.config.apiKey}` },
    body: JSON.stringify(createUpstreamBody(body, state.model)), signal: state.controller.signal,
  });
  if (!upstream.ok || !upstream.body) return upstreamFailure(res, upstream, state);
  res.writeHead(200, { "content-type": "text/event-stream; charset=utf-8", "cache-control": "no-cache", "x-prototype-abort": "1" });
  const result = await pipeStream(upstream, res, state);
  if (!res.destroyed && !res.writableEnded) res.end();
  logChat(state, {
    outcome: "complete", status: 200, thinking: Boolean(body.thinking && thinkingSupported(state.model)),
    bytes: result.bytes, done: result.done, response: logText(result.full, state.config),
  });
}

function proxyError(res, error, state) {
  const stopped = state.clientClosed();
  const timedOut = state.timedOut;
  logChat(state, {
    outcome: stopped ? "client-aborted" : timedOut ? "timeout" : "proxy-error",
    error: stopped ? "client-abort" : timedOut ? "timeout" : logText(error?.message, state.config),
    ...(state.partial != null
      ? { bytes: Buffer.byteLength(state.partial), partial: logText(state.partial, state.config) }
      : {}),
  });
  if (res.headersSent) { if (!res.writableEnded) res.end(); return; }
  res.statusCode = stopped ? 499 : timedOut ? 504 : 502;
  res.setHeader("content-type", "application/json; charset=utf-8");
  res.end(JSON.stringify({ error: stopped ? "aborted" : timedOut ? "timeout" : "proxy", message: stopped ? "请求已停止" : timedOut ? "真实模型请求超时" : "真实模型代理失败，详情已脱敏记录" }));
}

async function handleChat(req, res, config, body, model) {
  const state = makeChatState(req, res, config, body, model);
  const timer = setTimeout(() => { state.timedOut = true; state.controller.abort(); }, config.timeoutMs);
  try { await proxyChat(res, state, body); } catch (error) { proxyError(res, error, state); } finally { clearTimeout(timer); }
}

async function handleRequest(req, res, next, init) {
  if (!req.url?.startsWith("/prototype-ai/")) return next();
  let config;
  try { config = init(); } catch { return configError(res, "env-missing", "AI_BASE_URL / AI_API_KEY 未配置，原型无法接真实模型"); }
  const endpoint = req.url.slice("/prototype-ai/".length).split("?")[0];
  if (endpoint === "config") return sendConfig(res, config);
  if (endpoint !== "chat") return configError(res, "unknown-endpoint", "未知端点");
  const body = await readJson(req, res);
  if (!body) return undefined;
  const model = typeof body.model === "string" ? body.model.trim() : "";
  if (!model || !config.models.includes(model)) return configError(res, "bad-model", "模型不在可用清单");
  return handleChat(req, res, config, body, model);
}

export function createAiProxy() {
  let config = null;
  const init = () => config || (config = readConfig());
  return {
    name: "prototype-ai-proxy",
    configureServer(server) { server.middlewares.use((req, res, next) => handleRequest(req, res, next, init)); },
  };
}
