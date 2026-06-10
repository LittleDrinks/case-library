/**
 * Case CRUD and submission helpers.
 *
 * Wraps form-based create/update and the submit action. Keeps the mapping
 * between the wizard form and the backend case endpoints in one place.
 */

import { request, postForm, get, post } from "./client.js";

/**
 * Fetch runtime labels from the backend.
 *
 * Response shape (under data):
 *   case_types: Record<string, string>
 *   themes: string[]
 *   statuses: Record<string, string>
 */
export async function fetchCaseConstants() {
  const data = await get("/api/constants");
  return data?.data || null;
}

/**
 * Create a new case.
 *
 * Backend contract:
 *   POST /api/cases
 *   Content-Type: application/x-www-form-urlencoded
 *   Body: title, content, department, type, theme, status, auto_process
 */
export async function createCase(form) {
  return postForm("/api/cases", form);
}

/**
 * Update an existing case.
 *
 * Backend contract:
 *   PUT /api/cases/{case_id}
 *   Content-Type: application/x-www-form-urlencoded
 *   Body: title, content, author, department, type, theme, change_reason
 */
export async function updateCase(caseId, form) {
  return request(`/api/cases/${caseId}`, {
    method: "PUT",
    form: true,
    body: form,
  });
}

/**
 * Submit an existing draft case for expert review.
 *
 * Backend contract:
 *   POST /api/cases/{case_id}/submit
 */
export async function submitCaseById(caseId, versionId = null) {
  const options = { method: "POST" };
  if (versionId) {
    options.form = true;
    options.body = { version_id: versionId };
  }
  return request(`/api/cases/${caseId}/submit`, options);
}

/**
 * List current user's cases by status tab.
 *
 * Backend contract:
 *   GET /api/cases?author=<username>&status=<status>
 */
export async function listMyCases(username, status) {
  const params = new URLSearchParams();
  params.set("author", username);
  params.set("status", status);
  return get(`/api/cases?${params.toString()}`);
}

/**
 * Fetch a single case detail.
 *
 * Backend contract:
 *   GET /api/cases/{case_id}?increment_view=<bool>
 */
export async function fetchCaseDetail(caseId, incrementView = false) {
  return get(`/api/cases/${caseId}?increment_view=${incrementView}`);
}

/**
 * Fetch review records for a case.
 *
 * Backend contract:
 *   GET /api/reviews/{case_id}
 */
export async function fetchCaseReviews(caseId) {
  return get(`/api/reviews/${caseId}`);
}

/**
 * Fetch read-only version history for a case.
 *
 * Backend contract:
 *   GET /api/versions/{case_id}
 */
export async function fetchCaseVersions(caseId) {
  return get(`/api/versions/${caseId}`);
}

/**
 * Delete a case by ID.
 *
 * Backend contract:
 *   DELETE /api/cases/{case_id}
 */
export async function deleteCaseById(caseId) {
  return request(`/api/cases/${caseId}`, { method: "DELETE" });
}

/**
 * List cases for admin review by status tab.
 *
 * Backend contract:
 *   GET /api/cases?status=<status>
 *
 * Tab mappings:
 *   pending   -> pending_review
 *   approved  -> approved_all
 *   rejected  -> rejected
 *   all       -> all
 */
export async function listReviewCases(status) {
  const params = new URLSearchParams();
  params.set("status", status);
  return get(`/api/cases?${params.toString()}`);
}

/**
 * Review a case as admin.
 *
 * Backend contract:
 *   POST /api/reviews/{case_id}
 *   Content-Type: application/x-www-form-urlencoded
 *   Body: comment, status
 *
 * Status values accepted by backend:
 *   "approve" | "approved"  -> approved
 *   "reject"  | "rejected"  -> rejected / needs_revision
 */
export async function reviewCase(caseId, { comment, status, version_id, paragraph_comments }) {
  const body = { comment, status };
  if (version_id) body.version_id = version_id;
  if (paragraph_comments) {
    body.paragraph_comments = Array.isArray(paragraph_comments)
      ? JSON.stringify(paragraph_comments)
      : paragraph_comments;
  }
  return postForm(`/api/reviews/${caseId}`, body);
}

/**
 * Set a case's visibility (hide or show).
 *
 * Backend contract:
 *   POST /api/cases/{case_id}/visibility
 *   Content-Type: application/x-www-form-urlencoded
 *   Body: hidden (bool)
 */
export async function setCaseVisibility(caseId, hidden) {
  return postForm(`/api/cases/${caseId}/visibility`, {
    hidden: hidden ? "true" : "false",
  });
}

// ============================================================================
// Public visitor API (no login required)
// ============================================================================

/**
 * List approved, non-hidden cases for the public library.
 *
 * Backend contract:
 *   GET /api/cases?status=approved&offset=<>&limit=<>
 */
export async function listPublicCases(offset = 0, limit = 50) {
  return get(`/api/cases?status=approved&offset=${offset}&limit=${limit}`);
}

/**
 * Search and filter approved cases.
 *
 * Uses /api/search/advanced when any filter or keyword is present;
 * falls back to listPublicCases for the unfiltered list.
 *
 * Backend contract:
 *   GET /api/search/advanced?status=approved&type=<>&theme=<>&keyword=<>&limit=<>
 */
export async function searchPublicCases({ keyword, type, theme, limit = 50 }) {
  const params = new URLSearchParams();
  params.set("status", "approved");
  params.set("limit", String(limit));
  if (keyword) params.set("keyword", keyword);
  if (type) params.set("type", type);
  if (theme) params.set("theme", theme);
  return get(`/api/search/advanced?${params.toString()}`);
}

/**
 * Fetch public case detail with view count increment.
 *
 * Backend contract:
 *   GET /api/cases/{case_id}?increment_view=true
 */
export async function fetchPublicCaseDetail(caseId) {
  return get(`/api/cases/${caseId}?increment_view=true`);
}

/**
 * Like a case. No authentication required.
 *
 * Backend contract:
 *   POST /api/cases/{case_id}/like
 */
export async function likeCase(caseId) {
  return post(`/api/cases/${caseId}/like`);
}

/**
 * Unlike a case. No authentication required.
 *
 * Backend contract:
 *   POST /api/cases/{case_id}/unlike
 */
export async function unlikeCase(caseId) {
  return post(`/api/cases/${caseId}/unlike`);
}

// ============================================================================
// Public dashboard API (no login required)
// ============================================================================

/**
 * Fetch public statistics.
 *
 * Backend contract:
 *   GET /api/statistics
 *
 * Response data shape:
 *   { total_cases, total_views, total_likes, by_type: Record, by_theme: Record }
 */
export async function fetchStatistics() {
  return get("/api/statistics");
}

/**
 * Fetch trending approved cases.
 *
 * Backend contract:
 *   GET /api/trending?limit=...
 */
export async function fetchTrendingCases(limit = 6) {
  return get(`/api/trending?limit=${limit}`);
}

/**
 * Fetch latest approved cases.
 *
 * Backend contract:
 *   GET /api/latest?limit=...
 */
export async function fetchLatestCases(limit = 6) {
  return get(`/api/latest?limit=${limit}`);
}
