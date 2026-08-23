import http from "k6/http";
import { check, fail, sleep } from "k6";

const baseUrl = __ENV.BASE_URL || "http://frontend";
const backendUrl = __ENV.BACKEND_URL || "http://app:8001";
const meiliUrl = __ENV.MEILI_URL || "http://load-meilisearch:7700";
const indexUid = __ENV.CATALOG_INDEX_UID;
const expectedGeneration = __ENV.CATALOG_GENERATION;
const expectedEpoch = __ENV.CATALOG_INDEX_EPOCH;
const keyFile = __ENV.MEILI_KEY_FILE || "/run/secrets/meili_master_key";
const meiliKey = open(keyFile).trim();
const targetMaterials = 12_480;
const outboxLagSeconds = 11;
const token = __ENV.CATALOG_GATE_TOKEN || "catalog-gate";
const probeHeader = { "X-Load-Probe": "catalog-gate" };
const operations = [
  "gate-catalog-index", "gate-catalog-meta", "gate-material-count",
  "gate-user-login", "gate-case-create",
  "case-submit", "gate-admin-login", "case-start", "case-approve",
  "gate-catalog-search", "gate-lag-health",
];

export const options = {
  vus: 1,
  iterations: 1,
  discardResponseBodies: false,
  thresholds: gateThresholds(),
};

function gateThresholds() {
  const thresholds = { checks: ["rate==1"], http_req_failed: ["rate==0"] };
  operations.forEach((operation) => {
    thresholds[`http_reqs{operation:${operation}}`] = ["count>0"];
  });
  return thresholds;
}

function requireResponse(response, status, message) {
  const valid = check(response, { [message]: (result) => result.status === status });
  if (!valid) fail(`${message}: status=${response.status} body=${response.body}`);
  return response.json();
}

function jsonRequest(method, path, body, operation, csrf = "") {
  const headers = { ...probeHeader, "Content-Type": "application/json" };
  if (csrf) headers["X-CSRF-Token"] = csrf;
  return http.request(method, `${baseUrl}${path}`, JSON.stringify(body), {
    headers, responseType: "text", tags: { operation, phase: "gate" },
  });
}

function login(username, password, operation) {
  const response = jsonRequest("POST", "/api/auth/login", { username, password }, operation);
  return requireResponse(response, 200, `${operation} succeeds`).csrfToken;
}

function transition(caseView, csrf, command, extra = {}) {
  const body = { command, revision: caseView.revision, ...extra };
  const path = `/api/cases/${caseView.id}/lifecycle`;
  return requireResponse(jsonRequest("POST", path, body, `case-${command}`, csrf), 200,
    `case ${command} succeeds`);
}

function assertCatalogBaseline() {
  if (!indexUid || !expectedGeneration || !expectedEpoch) fail("catalog target is required");
  const headers = { Authorization: `Bearer ${meiliKey}` };
  const index = requireResponse(http.get(`${meiliUrl}/indexes/${indexUid}`, {
    headers, tags: { operation: "gate-catalog-index", phase: "gate" },
  }), 200, "catalog index exists");
  const metaPath = `/indexes/${indexUid}/documents/catalog-meta`;
  const meta = requireResponse(http.get(`${meiliUrl}${metaPath}`, {
    headers, tags: { operation: "gate-catalog-meta", phase: "gate" },
  }), 200,
    "catalog generation exists");
  const body = { q: "", filter: 'docClass = "material-full"', limit: 0 };
  const search = requireResponse(http.post(`${meiliUrl}/indexes/${indexUid}/search`,
    JSON.stringify(body), { headers: { ...headers, "Content-Type": "application/json" },
      tags: { operation: "gate-material-count", phase: "gate" } }), 200,
  "logical material count is searchable");
  if (meta.generation !== expectedGeneration) fail("catalog generation mismatch");
  if (index.updatedAt !== expectedEpoch) fail("catalog index epoch mismatch");
  if (search.estimatedTotalHits !== targetMaterials) fail(`materials=${search.estimatedTotalHits}`);
  console.log(`index_uid=${indexUid} generation=${meta.generation} logical_materials=${search.estimatedTotalHits}`);
}

function createPublishedCase() {
  const csrf = login(__ENV.LOAD_USERNAME || "user", __ENV.LOAD_PASSWORD || "user123", "gate-user-login");
  const title = `CapacityGate ${token}`;
  const created = requireResponse(jsonRequest("POST", "/api/cases", { title },
    "gate-case-create", csrf), 200, "gate case creation succeeds");
  const submitted = transition(created, csrf, "submit");
  const adminCsrf = login(__ENV.LOAD_ADMIN_USERNAME || "admin",
    __ENV.LOAD_ADMIN_PASSWORD || "admin123", "gate-admin-login");
  const started = transition(submitted.case, adminCsrf, "start");
  transition(started.case, adminCsrf, "approve", { submittedVersionId: submitted.version.id });
  return { id: created.id, title };
}

function searchItems(title) {
  const path = `/api/search?q=${encodeURIComponent(title)}&kind=case&pageSize=20`;
  const response = http.get(`${baseUrl}${path}`, {
    headers: probeHeader, responseType: "text",
    tags: { operation: "gate-catalog-search", phase: "gate" },
    responseCallback: http.expectedStatuses(200, 503),
  });
  return response.status === 200 ? response.json("items") : [];
}

function waitUntilSearchable(published) {
  const deadline = Date.now() + 30_000;
  while (Date.now() < deadline) {
    if (searchItems(published.title).some((item) => item.id === published.id)) return;
    sleep(0.25);
  }
  fail(`incremental case did not become searchable: ${published.id}`);
}

function assertLagHealthy() {
  sleep(outboxLagSeconds);
  const response = http.get(`${backendUrl}/health/ready`, {
    tags: { operation: "gate-lag-health", phase: "gate" },
  });
  requireResponse(response, 200, "catalog lag remains healthy");
}

export default function () {
  assertCatalogBaseline();
  const published = createPublishedCase();
  waitUntilSearchable(published);
  assertLagHealthy();
  console.log(`incremental_case=${published.id} searchable=true lag_health=ready`);
}
