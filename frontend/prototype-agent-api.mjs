import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const endpoint = "/api/prototype/agent-chat";
const skillId = "sizheng-case-generator.v2.1.m1";

function modelName(env) {
  return env.AI_DEFAULT_MODEL || env.AI_MODELS?.split(",").find(Boolean)?.trim();
}

function configured(env) {
  return Boolean(env.AI_BASE_URL && env.AI_API_KEY && modelName(env));
}

function resourcePath(root, name) {
  const base = "backend/app/modules/skills/resources/sizheng-case-generator/v2.1";
  return resolve(root, base, name);
}

function promptFiles(root, selectedSkills) {
  const base = resourcePath(root, "prompts/live-editor-base.md");
  if (!selectedSkills.includes(skillId)) return [base];
  return [resourcePath(root, "SKILL.md"), resourcePath(root, "prompts/live-editor-prototype.md"), base];
}

function systemPrompt(root, selectedSkills) {
  return promptFiles(root, selectedSkills).map((path) => readFileSync(path, "utf8")).join("\n\n");
}

function localOrigin(request) {
  const origin = request.headers.origin || "";
  return /^http:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/.test(origin);
}

function sendEvent(response, name, payload) {
  response.write(`event: ${name}\ndata: ${JSON.stringify(payload)}\n\n`);
}

function fail(response, status, message) {
  response.statusCode = status;
  response.setHeader("Content-Type", "application/json");
  response.end(JSON.stringify({ detail: message }));
}

function streamFailure(response) {
  if (!response.headersSent) return fail(response, 502, "AI 服务暂不可用");
  sendEvent(response, "error", { message: "AI 服务暂不可用" });
  response.end();
}

async function bodyOf(request) {
  let body = "";
  for await (const chunk of request) {
    body += chunk;
    if (body.length > 100_000) throw new Error("请求过长");
  }
  return JSON.parse(body);
}

function upstreamUrl(env) {
  return `${env.AI_BASE_URL.replace(/\/$/, "")}/chat/completions`;
}

function upstreamBody(env, root, payload) {
  return {
    model: modelName(env), stream: true,
    messages: [
      { role: "system", content: systemPrompt(root, payload.skillIds) },
      { role: "user", content: JSON.stringify(payload, null, 2) },
    ],
  };
}

function tokenOf(line) {
  if (!line.startsWith("data:") || line.slice(5).trim() === "[DONE]") return "";
  const data = JSON.parse(line.slice(5).trim());
  return data.choices?.[0]?.delta?.content || "";
}

function consumeLines(buffer, response) {
  const lines = buffer.split(/\r?\n/);
  lines.slice(0, -1).forEach((line) => {
    const token = tokenOf(line);
    if (token) sendEvent(response, "token", { text: token });
  });
  return lines.at(-1) || "";
}

async function relay(upstream, response) {
  const reader = upstream.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value, { stream: !done });
    buffer = consumeLines(buffer, response);
    if (done) break;
  }
  consumeLines(`${buffer}\n`, response);
}

async function callProvider(env, root, payload) {
  return fetch(upstreamUrl(env), {
    method: "POST",
    headers: { Authorization: `Bearer ${env.AI_API_KEY}`, "Content-Type": "application/json" },
    body: JSON.stringify(upstreamBody(env, root, payload)),
    signal: AbortSignal.timeout(Number(env.AI_TIMEOUT_SECONDS || 60) * 1000),
  });
}

async function handle(request, response, env, root) {
  if (request.method !== "POST") return fail(response, 405, "仅支持 POST");
  if (!localOrigin(request)) return fail(response, 403, "仅允许本机原型访问");
  if (!configured(env)) return fail(response, 503, "AI 服务未配置");
  const payload = await bodyOf(request);
  const upstream = await callProvider(env, root, payload);
  if (!upstream.ok || !upstream.body) return fail(response, 502, "AI 服务暂不可用");
  response.writeHead(200, { "Content-Type": "text/event-stream", "Cache-Control": "no-cache" });
  await relay(upstream, response);
  sendEvent(response, "done", {});
  response.end();
}

function middleware(env, root) {
  return (request, response, next) => {
    if (!request.url?.startsWith(endpoint)) return next();
    handle(request, response, env, root).catch(() => streamFailure(response));
  };
}

export function prototypeAgentApi(env, root) {
  return {
    name: "prototype-agent-api",
    apply: "serve",
    configureServer(server) { server.middlewares.use(middleware(env, root)); },
  };
}
