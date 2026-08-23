import http from "k6/http";
import { check, sleep } from "k6";
import exec from "k6/execution";

const peakVus = Number(__ENV.PEAK_VUS || 200);
const resilienceVus = Number(__ENV.RESILIENCE_VUS || 1000);
const rampDuration = __ENV.RAMP_DURATION || "30s";
const peakDuration = __ENV.PEAK_DURATION || "2m";
const resilienceRamp = __ENV.RESILIENCE_RAMP_DURATION || "2m";
const resilienceDuration = __ENV.RESILIENCE_DURATION || "3m";
const latencyBudget = ["p(95)<500", "p(99)<1000"];
const readOperations = [
  "session", "case-read", "case-save", "catalog-search", "catalog-cursor",
  "material-page", "material-cursor",
];
const operations = [
  "login", "case-create", "setup-catalog-cursor", "setup-material-cursor",
  ...readOperations,
];

const profiles = {
  smoke: {
    vus: 2,
    duration: "15s",
  },
  peak: {
    stages: [
      { duration: rampDuration, target: peakVus },
      { duration: peakDuration, target: peakVus },
      { duration: rampDuration, target: 0 },
    ],
  },
  resilience: {
    stages: [
      { duration: resilienceRamp, target: resilienceVus },
      { duration: resilienceDuration, target: resilienceVus },
      { duration: resilienceRamp, target: 0 },
    ],
  },
  rate: {
    scenarios: {
      operations: {
        executor: "constant-arrival-rate",
        rate: Number(__ENV.LOAD_RATE || 450),
        timeUnit: "1s",
        duration: __ENV.RATE_DURATION || "2m",
        preAllocatedVUs: Number(__ENV.RATE_VUS || 200),
        maxVUs: Number(__ENV.RATE_MAX_VUS || 1000),
      },
    },
  },
};

const selectedProfile = __ENV.LOAD_PROFILE || "smoke";

export const options = {
  ...profiles[selectedProfile],
  discardResponseBodies: true,
  noCookiesReset: true,
  summaryTrendStats: ["avg", "min", "med", "max", "p(90)", "p(95)", "p(99)"],
  thresholds: loadThresholds(),
};

function loadThresholds() {
  const thresholds = baseThresholds();
  operations.forEach((operation) => {
    thresholds[`http_reqs{operation:${operation}}`] = ["count>0"];
    thresholds[`http_req_duration{operation:${operation}}`] = latencyBudget;
    thresholds[`http_req_failed{operation:${operation}}`] = ["rate==0"];
  });
  readOperations.forEach((operation) => {
    thresholds[`http_reqs{operation:${operation},phase:hold}`] = ["count>0"];
    thresholds[`http_req_duration{operation:${operation},phase:hold}`] = latencyBudget;
    thresholds[`http_req_failed{operation:${operation},phase:hold}`] = ["rate==0"];
  });
  if (selectedProfile === "rate") thresholds.dropped_iterations = ["count==0"];
  return thresholds;
}

function baseThresholds() {
  return {
    checks: ["rate>=0.999"],
    http_req_duration: latencyBudget,
    "checks{phase:hold}": ["rate>=0.999"],
    "http_req_duration{phase:hold}": latencyBudget,
    http_req_failed: ["rate<0.001"],
    "http_req_failed{phase:hold}": ["rate<0.001"],
  };
}

const baseUrl = __ENV.BASE_URL || "http://frontend";
const writePercent = Number(__ENV.WRITE_PERCENT || 5);
const searchPercent = Number(__ENV.SEARCH_PERCENT || 20);
const materialPercent = Number(__ENV.MATERIAL_PERCENT || 10);
const cursorPercent = Number(__ENV.CURSOR_PERCENT || 50);
const thinkTime = Number(__ENV.THINK_TIME_SECONDS || 2);
const catalogQuery = encodeURIComponent("思政");
let signedIn = false;
let csrfToken = "";
let ownedCase = null;
let holdCovered = false;

function durationMilliseconds(value) {
  const match = String(value).match(/^(\d+(?:\.\d+)?)(ms|s|m|h)$/);
  if (!match) throw new Error(`unsupported duration: ${value}`);
  const multiplier = { ms: 1, s: 1000, m: 60_000, h: 3_600_000 }[match[2]];
  return Number(match[1]) * multiplier;
}

function currentPhase() {
  if (selectedProfile === "smoke" || selectedProfile === "rate") return "hold";
  const ramp = selectedProfile === "peak" ? rampDuration : resilienceRamp;
  const hold = selectedProfile === "peak" ? peakDuration : resilienceDuration;
  const elapsed = Date.now() - exec.scenario.startTime;
  return elapsed >= durationMilliseconds(ramp)
    && elapsed < durationMilliseconds(ramp) + durationMilliseconds(hold) ? "hold" : "ramp";
}

function coverageRequired(phase) {
  return __VU === 1 && (__ITER === 0 || (phase === "hold" && !holdCovered));
}

function profileVus() {
  if (selectedProfile === "peak") return peakVus;
  if (selectedProfile === "resilience") return resilienceVus;
  if (selectedProfile === "rate") return Number(__ENV.RATE_MAX_VUS || 1000);
  return 2;
}

export function setup() {
  const operationsPerIteration = 2 + (writePercent + searchPercent + materialPercent) / 100;
  const estimatedRps = Math.round((profileVus() * operationsPerIteration) / Math.max(thinkTime, 0.001));
  const arrivalRps = Math.round(Number(__ENV.LOAD_RATE || 450) * operationsPerIteration);
  const target = selectedProfile === "rate" ? arrivalRps : estimatedRps;
  console.log(`profile=${selectedProfile} max_vus=${profileVus()} target_http_rps~=${target}`);
  login("setup");
  if (!signedIn) throw new Error("cursor setup login failed");
  return { cursors: discoverCursors() };
}

function firstPage(kind, pageSize, operation) {
  const q = kind === "all" ? catalogQuery : "";
  return http.get(`${baseUrl}/api/search?q=${q}&kind=${kind}&pageSize=${pageSize}`, {
    responseType: "text", tags: { operation, phase: "setup" },
  });
}

function discoverCursors() {
  const catalog = firstPage("all", 20, "setup-catalog-cursor");
  const material = firstPage("material", 50, "setup-material-cursor");
  if (!catalog.json("nextCursor") || !material.json("nextCursor")) throw new Error("cursor unavailable");
  return { catalog: catalog.json("nextCursor"), material: material.json("nextCursor") };
}

function jsonHeaders() {
  return {
    "Content-Type": "application/json",
    "X-CSRF-Token": csrfToken,
  };
}

function login(phase = currentPhase()) {
  const response = http.post(
    `${baseUrl}/api/auth/login`,
    JSON.stringify({
      username: __ENV.LOAD_USERNAME || "user",
      password: __ENV.LOAD_PASSWORD || "user123",
    }),
    {
      headers: { "Content-Type": "application/json" },
      responseType: "text",
      tags: { operation: "login", phase },
    },
  );
  signedIn = check(response, { "login succeeds": (result) => result.status === 200 }, { phase });
  if (signedIn) csrfToken = response.json("csrfToken");
}

function createOwnedCase(phase) {
  const response = http.post(
    `${baseUrl}/api/cases`,
    JSON.stringify({
      title: `Load test VU ${__VU}`,
      document: { type: "doc", content: [{ type: "paragraph" }] },
    }),
    { headers: jsonHeaders(), responseType: "text", tags: { operation: "case-create", phase } },
  );
  const created = check(response, {
    "case creation succeeds": (result) => result.status === 200 || result.status === 201,
  }, { phase });
  if (created) ownedCase = response.json();
}

function patchOwnedCase(force, phase) {
  if (!force && Math.random() * 100 >= writePercent) return;
  const response = http.patch(
    `${baseUrl}/api/cases/${ownedCase.id}`,
    JSON.stringify({ title: ownedCase.title, revision: ownedCase.revision }),
    { headers: jsonHeaders(), responseType: "text", tags: { operation: "case-save", phase } },
  );
  const saved = check(response, { "case save succeeds": (result) => result.status === 200 }, { phase });
  if (saved) ownedCase = response.json();
}

function cursorRequest(kind, pageSize, cursor, firstOperation, cursorOperation, phase, forced = null) {
  const useCursor = cursor && (forced === null ? Math.random() * 100 < cursorPercent : forced);
  const suffix = useCursor ? `&cursor=${encodeURIComponent(cursor)}` : "";
  const q = kind === "all" ? catalogQuery : "";
  const operation = useCursor ? cursorOperation : firstOperation;
  return ["GET", `${baseUrl}/api/search?q=${q}&kind=${kind}&pageSize=${pageSize}${suffix}`, null,
    { responseType: "text", tags: { operation, phase } }];
}

function coverageRequests(cursors, phase) {
  return [
    cursorRequest("all", 20, cursors.catalog, "catalog-search", "catalog-cursor", phase, false),
    cursorRequest("all", 20, cursors.catalog, "catalog-search", "catalog-cursor", phase, true),
    cursorRequest("material", 50, cursors.material, "material-page", "material-cursor", phase, false),
    cursorRequest("material", 50, cursors.material, "material-page", "material-cursor", phase, true),
  ];
}

function readRequests(cursors, phase, cover) {
  const requests = [
    ["GET", `${baseUrl}/api/auth/session`, null, { tags: { operation: "session", phase } }],
    ["GET", `${baseUrl}/api/cases/${ownedCase.id}`, null, { tags: { operation: "case-read", phase } }],
  ];
  if (cover) return [...requests, ...coverageRequests(cursors, phase)];
  if (Math.random() * 100 < searchPercent) requests.push(cursorRequest(
    "all", 20, cursors.catalog, "catalog-search", "catalog-cursor", phase,
  ));
  if (Math.random() * 100 < materialPercent) requests.push(cursorRequest(
    "material", 50, cursors.material, "material-page", "material-cursor", phase,
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
  const phase = currentPhase();
  const cover = coverageRequired(phase);
  if (!signedIn) login(phase);
  if (!signedIn) return;
  if (!ownedCase) {
    createOwnedCase(phase);
    if (ownedCase) patchOwnedCase(true, phase);
  }
  if (!ownedCase) return;

  checkReads(http.batch(readRequests(data.cursors, phase, cover)), phase);
  patchOwnedCase(cover, phase);
  if (phase === "hold") holdCovered = true;
  sleep(thinkTime);
}
