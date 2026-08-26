import http from "k6/http";
import { check, fail, sleep } from "k6";
import exec from "k6/execution";

const baseUrl = __ENV.BASE_URL || "http://frontend";
const cookieName = "case_library_session";
const latencyBudget = ["p(95)<500", "p(99)<1000"];
const steadyVus = Number(__ENV.STEADY_VUS || 1000);
const steadyRamp = __ENV.STEADY_RAMP_DURATION || "2m";
const steadyDuration = __ENV.STEADY_DURATION || "15m";
const thinkTime = Number(__ENV.STEADY_THINK_TIME_SECONDS || 2);
const writePercent = Number(__ENV.STEADY_WRITE_PERCENT || 5);
const searchPercent = Number(__ENV.SEARCH_PERCENT || 20);
const materialPercent = Number(__ENV.MATERIAL_PERCENT || 10);
const cursorPercent = Number(__ENV.CURSOR_PERCENT || 50);
const catalogQuery = encodeURIComponent("思政");
const caseSelection = { stageId: "ug", typeId: "ct-figure", templateId: "tpl-general-v1" };
const operations = 2 + (writePercent + searchPercent + materialPercent) / 100;
const targetRps = Math.round((steadyVus * operations) / thinkTime);
let ownedCase = null;
let holdCovered = false;
const measuredOperations = [
  "session", "case-read", "case-save", "catalog-search", "catalog-cursor",
  "material-page", "material-cursor",
];
const setupOperations = [
  "setup-login", "setup-case-create", "setup-all-cursor", "setup-material-cursor",
];

export const options = {
  stages: [
    { duration: steadyRamp, target: steadyVus },
    { duration: steadyDuration, target: steadyVus },
    { duration: steadyRamp, target: 0 },
  ],
  discardResponseBodies: true,
  setupTimeout: __ENV.STEADY_SETUP_TIMEOUT || "5m",
  summaryTrendStats: ["avg", "min", "med", "max", "p(90)", "p(95)", "p(99)"],
  thresholds: loadThresholds(),
};

function loadThresholds() {
  const thresholds = baseThresholds();
  setupOperations.forEach((operation) => operationThresholds(thresholds, operation));
  measuredOperations.forEach((operation) => {
    operationThresholds(thresholds, operation, latencyBudget);
    holdThresholds(thresholds, operation);
  });
  return thresholds;
}

function baseThresholds() {
  return {
    checks: ["rate>=0.999"],
    "checks{phase:hold}": ["rate>=0.999"],
    "http_req_duration{phase:hold}": latencyBudget,
    http_req_failed: ["rate<0.001"],
    "http_req_failed{phase:hold}": ["rate<0.001"],
  };
}

function operationThresholds(thresholds, operation, duration = null) {
  thresholds[`http_reqs{operation:${operation}}`] = ["count>0"];
  thresholds[`http_req_failed{operation:${operation}}`] = ["rate==0"];
  if (duration) thresholds[`http_req_duration{operation:${operation}}`] = duration;
}

function holdThresholds(thresholds, operation) {
  thresholds[`http_reqs{operation:${operation},phase:hold}`] = ["count>0"];
  thresholds[`http_req_duration{operation:${operation},phase:hold}`] = latencyBudget;
  thresholds[`http_req_failed{operation:${operation},phase:hold}`] = ["rate==0"];
}

function durationMilliseconds(value) {
  const match = String(value).match(/^(\d+(?:\.\d+)?)(ms|s|m|h)$/);
  if (!match) fail(`unsupported duration: ${value}`);
  const multiplier = { ms: 1, s: 1000, m: 60_000, h: 3_600_000 }[match[2]];
  return Number(match[1]) * multiplier;
}

function currentPhase() {
  const elapsed = Date.now() - exec.scenario.startTime;
  const ramp = durationMilliseconds(steadyRamp);
  const hold = durationMilliseconds(steadyDuration);
  return elapsed >= ramp && elapsed < ramp + hold ? "hold" : "ramp";
}

function cookie(response) {
  const values = response.cookies[cookieName];
  if (!values || !values.length) fail("login did not return a session cookie");
  return values[0].value;
}

function authCookies(value) {
  return { [cookieName]: { value, replace: true } };
}

function authOptions(session, csrf = "") {
  const headers = {};
  if (csrf) headers["X-CSRF-Token"] = csrf;
  return { cookies: authCookies(session), headers };
}

function loginRequest() {
  const body = JSON.stringify({
    username: __ENV.LOAD_USERNAME || "user",
    password: __ENV.LOAD_PASSWORD || "user123",
  });
  return ["POST", `${baseUrl}/api/auth/login`, body, {
    headers: { "Content-Type": "application/json" },
    responseType: "text",
    tags: { operation: "setup-login", phase: "setup" },
  }];
}

function caseBody() {
  return JSON.stringify(caseSelection);
}

function requestOptions(session, csrf, operation, phase) {
  const options = authOptions(session, csrf);
  options.headers["Content-Type"] = "application/json";
  return { ...options, responseType: "text", tags: { operation, phase } };
}

function sessionView(response, index) {
  if (response.status !== 200) fail(`session ${index + 1} setup failed: ${response.status}`);
  return { session: cookie(response), csrf: response.json("csrfToken"), index };
}

function provisionSessions() {
  const sessions = [];
  for (let offset = 0; offset < steadyVus; offset += 20) {
    const count = Math.min(20, steadyVus - offset);
    const responses = http.batch(Array.from({ length: count }, loginRequest));
    sessions.push(...responses.map((response, index) => sessionView(response, offset + index)));
  }
  return sessions;
}

function caseRequest(context) {
  return [
    "POST",
    `${baseUrl}/api/cases`,
    caseBody(),
    requestOptions(context.session, context.csrf, "setup-case-create", "setup"),
  ];
}

function caseView(response) {
  if (response.status !== 200 && response.status !== 201) {
    fail(`case setup failed: ${response.status}`);
  }
  return { id: response.json("id"), title: response.json("title"), revision: response.json("revision") };
}

function provisionCases(sessions) {
  for (let offset = 0; offset < sessions.length; offset += 20) {
    const batch = sessions.slice(offset, offset + 20);
    const responses = http.batch(batch.map(caseRequest));
    responses.forEach((response, index) => { batch[index].case = caseView(response); });
  }
  return sessions;
}

function cursorResponse(context, kind, pageSize) {
  const q = kind === "all" ? catalogQuery : "";
  return http.get(`${baseUrl}/api/search?q=${q}&kind=${kind}&pageSize=${pageSize}`, {
    ...authOptions(context.session), responseType: "text",
    tags: { operation: `setup-${kind}-cursor`, phase: "setup" },
  });
}

function discoverCursors(context) {
  const catalog = cursorResponse(context, "all", 20);
  const material = cursorResponse(context, "material", 50);
  if (!catalog.json("nextCursor") || !material.json("nextCursor")) fail("cursor unavailable");
  return { catalog: catalog.json("nextCursor"), material: material.json("nextCursor") };
}

function assertUniqueContexts(sessions) {
  const uniqueSessions = new Set(sessions.map((row) => row.session)).size;
  const uniqueCases = new Set(sessions.map((row) => row.case.id)).size;
  if (uniqueSessions !== steadyVus) fail(`expected ${steadyVus} unique sessions`);
  if (uniqueCases !== steadyVus) fail(`expected ${steadyVus} unique cases`);
}

export function setup() {
  const sessions = provisionCases(provisionSessions());
  if (sessions.length !== steadyVus) fail(`expected ${steadyVus} sessions, got ${sessions.length}`);
  assertUniqueContexts(sessions);
  console.log(`profile=preauthenticated max_vus=${steadyVus} target_http_rps~=${targetRps}`);
  return { sessions, cursors: discoverCursors(sessions[0]) };
}

function vuContext(data) {
  const context = data.sessions[__VU - 1];
  if (!context) fail(`missing session for VU ${__VU}`);
  if (!ownedCase) ownedCase = { ...context.case };
  return context;
}

function maybeWrite(context, phase, force) {
  if (!force && (writePercent <= 0 || Math.random() * 100 >= writePercent)) return;
  const response = http.patch(
    `${baseUrl}/api/cases/${ownedCase.id}`,
    JSON.stringify({ title: ownedCase.title, revision: ownedCase.revision }),
    requestOptions(context.session, context.csrf, "case-save", phase),
  );
  if (check(response, { "writer save succeeds": (result) => result.status === 200 }, { phase })) {
    ownedCase = caseView(response);
  }
}

function cursorRequest(auth, kind, pageSize, cursor, firstOperation, cursorOperation,
  phase, forced = null) {
  const useCursor = cursor && (forced === null ? Math.random() * 100 < cursorPercent : forced);
  const suffix = useCursor ? `&cursor=${encodeURIComponent(cursor)}` : "";
  const q = kind === "all" ? catalogQuery : "";
  const operation = useCursor ? cursorOperation : firstOperation;
  return ["GET", `${baseUrl}/api/search?q=${q}&kind=${kind}&pageSize=${pageSize}${suffix}`, null,
    { ...auth, responseType: "text", tags: { operation, phase } }];
}

function coverageRequests(auth, cursors, phase) {
  return [
    cursorRequest(auth, "all", 20, cursors.catalog, "catalog-search", "catalog-cursor", phase, false),
    cursorRequest(auth, "all", 20, cursors.catalog, "catalog-search", "catalog-cursor", phase, true),
    cursorRequest(auth, "material", 50, cursors.material, "material-page", "material-cursor", phase, false),
    cursorRequest(auth, "material", 50, cursors.material, "material-page", "material-cursor", phase, true),
  ];
}

function readRequests(context, auth, cursors, phase, cover) {
  const requests = [
    ["GET", `${baseUrl}/api/auth/session`, null, {
      ...auth, tags: { operation: "session", phase },
    }],
    ["GET", `${baseUrl}/api/cases/${context.case.id}`, null, {
      ...auth, tags: { operation: "case-read", phase },
    }],
  ];
  if (cover) return [...requests, ...coverageRequests(auth, cursors, phase)];
  if (Math.random() * 100 < searchPercent) requests.push(cursorRequest(
    auth, "all", 20, cursors.catalog, "catalog-search", "catalog-cursor", phase,
  ));
  if (Math.random() * 100 < materialPercent) requests.push(cursorRequest(
    auth, "material", 50, cursors.material, "material-page", "material-cursor", phase,
  ));
  return requests;
}

function checkReads(responses, phase) {
  check(responses[0], { "session stays valid": (response) => response.status === 200 }, { phase });
  check(responses[1], { "case read succeeds": (response) => response.status === 200 }, { phase });
  responses.slice(2).forEach((response) => checkCatalog(response, phase));
}

function checkCatalog(response, phase) {
  if (response.status !== 200) console.error(JSON.stringify({
    status: response.status, errorCode: response.error_code,
    error: response.error, body: String(response.body || "").slice(0, 240),
  }));
  check(response, { "catalog read succeeds": (result) => result.status === 200 }, { phase });
}

export default function (data) {
  const context = vuContext(data);
  const auth = authOptions(context.session);
  const phase = currentPhase();
  const cover = __VU === 1 && (__ITER === 0 || (phase === "hold" && !holdCovered));
  checkReads(http.batch(readRequests(context, auth, data.cursors, phase, cover)), phase);
  maybeWrite(context, phase, cover);
  if (phase === "hold") holdCovered = true;
  sleep(thinkTime);
}
