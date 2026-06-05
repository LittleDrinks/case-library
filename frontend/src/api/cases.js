/**
 * Case CRUD and submission helpers.
 *
 * Wraps form-based create/update and the submit action. Keeps the mapping
 * between the wizard form and the backend case endpoints in one place.
 */

import { request, postForm, get } from "./client.js";

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
export async function submitCaseById(caseId) {
  return request(`/api/cases/${caseId}/submit`, { method: "POST" });
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
 * Delete a case by ID.
 *
 * Backend contract:
 *   DELETE /api/cases/{case_id}
 */
export async function deleteCaseById(caseId) {
  return request(`/api/cases/${caseId}`, { method: "DELETE" });
}
