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
