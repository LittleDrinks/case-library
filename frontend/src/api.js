export class ApiError extends Error {
  constructor(response, payload) {
    super(payload?.detail || `请求失败 (${response.status})`);
    this.name = "ApiError";
    this.status = response.status;
    this.currentRevision = payload?.currentRevision;
  }
}

async function readPayload(response) {
  if (response.status === 204) return null;
  return response.json().catch(() => null);
}

async function request(path, options = {}) {
  const response = await fetch(path, { credentials: "same-origin", ...options });
  const payload = await readPayload(response);
  if (!response.ok) throw new ApiError(response, payload);
  return payload;
}

function jsonOptions(method, body, csrfToken) {
  const headers = { "Content-Type": "application/json" };
  if (csrfToken) headers["X-CSRF-Token"] = csrfToken;
  return { method, headers, body: JSON.stringify(body) };
}

function attachmentForm(file, accessLevel, revision) {
  const body = new FormData();
  body.append("file", file);
  body.append("accessLevel", accessLevel);
  body.append("revision", String(revision));
  return body;
}

function materialImportForm(files, accessLevel) {
  const body = new FormData();
  files.forEach((file) => body.append("files", file));
  body.append("accessLevel", accessLevel);
  return body;
}

function attachmentRoot(id) {
  return `/api/cases/${encodeURIComponent(id)}/attachments`;
}

function versionQuery(versionId) {
  return versionId ? `?versionId=${encodeURIComponent(versionId)}` : "";
}

function annotationRoot(id) {
  return `/api/cases/${encodeURIComponent(id)}/annotations`;
}

function materialRoot(id) {
  return `/api/cases/${encodeURIComponent(id)}/materials`;
}

function appendSearchFilters(params, filters) {
  Object.entries(filters).forEach(([name, raw]) => {
    const values = Array.isArray(raw) ? raw : [raw];
    values.filter(value => value !== "" && value != null).forEach(value => params.append(name, value));
  });
}

function searchPath(query, kind, cursor, pageSize, filters = {}) {
  const params = new URLSearchParams({
    q: query, kind, pageSize: String(pageSize),
  });
  if (cursor) params.set("cursor", cursor);
  appendSearchFilters(params, filters);
  return `/api/search?${params}`;
}

export const api = {
  login: (credentials) => request("/api/auth/login", jsonOptions("POST", credentials)),
  session: () => request("/api/auth/session"),
  changePassword: (passwords, csrfToken) => request(
    "/api/auth/change-password", jsonOptions("POST", passwords, csrfToken),
  ),
  logout: (csrfToken) => request("/api/auth/logout", {
    method: "POST",
    headers: { "X-CSRF-Token": csrfToken },
  }),
  listCases: (scope) => request(`/api/cases${scope ? `?scope=${scope}` : ""}`),
  search: (query, kind = "all", cursor = null, pageSize = 20, filters = {}) => request(
    searchPath(query, kind, cursor, pageSize, filters),
  ),
  agentThread: (caseId) => request(
    `/api/cases/${encodeURIComponent(caseId)}/agent/thread`,
  ),
  aiSettings: () => request("/api/ai/settings"),
  saveAISettings: (settings, csrfToken) => request(
    "/api/ai/settings", jsonOptions("PUT", settings, csrfToken),
  ),
  discoverAIModels: (credentials, csrfToken) => request(
    "/api/ai/models/discover", jsonOptions("POST", credentials, csrfToken),
  ),
  adminAISettings: () => request("/api/admin/ai/settings"),
  saveAdminAISettings: (settings, csrfToken) => request(
    "/api/admin/ai/settings", jsonOptions("PUT", settings, csrfToken),
  ),
  listCaseMaterials: (id, versionId) => request(
    `${materialRoot(id)}${versionQuery(versionId)}`,
  ),
  mountCaseMaterial: (id, materialId, revision, csrfToken) => request(
    materialRoot(id), jsonOptions("POST", { materialId, revision }, csrfToken),
  ),
  unmountCaseMaterial: (id, materialId, revision, csrfToken) => request(
    `${materialRoot(id)}/${encodeURIComponent(materialId)}?revision=${revision}`,
    { method: "DELETE", headers: { "X-CSRF-Token": csrfToken } },
  ),
  createCase: (caseRecord, csrfToken) => request(
    "/api/cases", jsonOptions("POST", caseRecord, csrfToken),
  ),
  getCase: (id) => request(`/api/cases/${encodeURIComponent(id)}`),
  getPublicCase: (id) => request(`/api/cases/${encodeURIComponent(id)}/public`),
  saveCase: (id, snapshot, csrfToken) => request(
    `/api/cases/${encodeURIComponent(id)}`,
    jsonOptions("PATCH", snapshot, csrfToken),
  ),
  lifecycleCase: (id, command, csrfToken) => request(
    `/api/cases/${encodeURIComponent(id)}/lifecycle`,
    jsonOptions("POST", command, csrfToken),
  ),
  caseHistory: (id) => request(`/api/cases/${encodeURIComponent(id)}/history`),
  listAnnotations: (id) => request(annotationRoot(id)),
  createAnnotation: (id, annotation, csrfToken) => request(
    annotationRoot(id), jsonOptions("POST", annotation, csrfToken),
  ),
  updateAnnotation: (id, annotationId, annotation, csrfToken) => request(
    `${annotationRoot(id)}/${encodeURIComponent(annotationId)}`,
    jsonOptions("PATCH", annotation, csrfToken),
  ),
  deleteAnnotation: (id, annotationId, csrfToken) => request(
    `${annotationRoot(id)}/${encodeURIComponent(annotationId)}`,
    { method: "DELETE", headers: { "X-CSRF-Token": csrfToken } },
  ),
  replyAnnotation: (id, annotationId, reply, csrfToken) => request(
    `${annotationRoot(id)}/${encodeURIComponent(annotationId)}/replies`,
    jsonOptions("POST", reply, csrfToken),
  ),
  setAnnotationStatus: (id, annotationId, status, csrfToken) => request(
    `${annotationRoot(id)}/${encodeURIComponent(annotationId)}/status`,
    jsonOptions("PATCH", { status }, csrfToken),
  ),
  listAttachments: (id, versionId) => request(`${attachmentRoot(id)}${versionQuery(versionId)}`),
  uploadAttachment: (id, file, accessLevel, revision, csrfToken) => request(
    attachmentRoot(id), {
      method: "POST",
      headers: { "X-CSRF-Token": csrfToken },
      body: attachmentForm(file, accessLevel, revision),
    },
  ),
  deleteAttachment: (id, attachmentId, revision, csrfToken) => request(
    `${attachmentRoot(id)}/${encodeURIComponent(attachmentId)}?revision=${revision}`,
    { method: "DELETE", headers: { "X-CSRF-Token": csrfToken } },
  ),
  createMaterialImport: (files, accessLevel, csrfToken) => request(
    "/api/admin/material-imports", {
      method: "POST",
      headers: { "X-CSRF-Token": csrfToken },
      body: materialImportForm(files, accessLevel),
    },
  ),
  listMaterialCandidates: (status = "candidate", page = 1, pageSize = 20) => request(
    `/api/admin/material-candidates?status=${encodeURIComponent(status)}&page=${page}&pageSize=${pageSize}`,
  ),
  decideMaterialCandidate: (id, decision, csrfToken) => request(
    `/api/admin/material-candidates/${encodeURIComponent(id)}/decision`,
    jsonOptions("POST", decision, csrfToken),
  ),
  attachmentContentUrl: (id, attachmentId, versionId) => (
    `${attachmentRoot(id)}/${encodeURIComponent(attachmentId)}/content${versionQuery(versionId)}`
  ),
  materialContentUrl: (id) => `/api/materials/${encodeURIComponent(id)}/content`,
};
