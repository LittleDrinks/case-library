/**
 * API client module.
 *
 * Supports JSON requests, form requests, consistent FastAPI error extraction,
 * and auth header injection from centralized token storage.
 */

const API_BASE = import.meta.env.VITE_API_BASE_URL || "";

function buildUrl(path) {
  if (path.startsWith("http://") || path.startsWith("https://")) {
    return path;
  }
  return `${API_BASE}${path}`;
}

/**
 * Extract a human-readable error message from a FastAPI-style response body.
 */
export function extractError(data) {
  if (typeof data === "string") {
    return data;
  }
  if (data == null) {
    return null;
  }
  if (data.detail != null) {
    if (typeof data.detail === "string") {
      return data.detail;
    }
    if (Array.isArray(data.detail)) {
      return data.detail
        .map((d) => (typeof d === "string" ? d : d.msg || JSON.stringify(d)))
        .join("; ");
    }
    return JSON.stringify(data.detail);
  }
  if (data.message != null) {
    return data.message;
  }
  return null;
}

/**
 * Core request wrapper.
 *
 * Options:
 *   - method: HTTP method (default GET)
 *   - json:   if true, sets Content-Type: application/json and serializes body
 *   - form:   if true, sets Content-Type: application/x-www-form-urlencoded
 *   - body:   RequestBody, string, or URLSearchParams
 *   - headers: extra headers object
 */
export async function request(path, options = {}) {
  const url = buildUrl(path);

  const headers = { ...(options.headers || {}) };

  if (options.json) {
    headers["Content-Type"] = "application/json";
  } else if (options.form) {
    headers["Content-Type"] = "application/x-www-form-urlencoded";
  }

  // Inject auth token from centralized storage
  const token = localStorage.getItem("case_library_auth_token");
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  let body = options.body;
  if (options.json && body != null && typeof body !== "string") {
    body = JSON.stringify(body);
  }
  if (options.form && body != null) {
    if (!(body instanceof URLSearchParams)) {
      const params = new URLSearchParams();
      for (const [key, value] of Object.entries(body)) {
        if (value != null) {
          params.set(key, String(value));
        }
      }
      body = params;
    }
  }

  const fetchOptions = {
    method: options.method || "GET",
    headers,
    body: body || undefined,
  };

  const response = await fetch(url, fetchOptions);

  let data;
  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    try {
      data = await response.json();
    } catch {
      data = null;
    }
  } else {
    try {
      data = await response.text();
    } catch {
      data = null;
    }
  }

  if (!response.ok) {
    const message = extractError(data) || `请求失败 (HTTP ${response.status})`;
    const error = new Error(message);
    error.status = response.status;
    error.data = data;
    throw error;
  }

  return data;
}

export function get(path, options = {}) {
  return request(path, { ...options, method: "GET" });
}

export function post(path, options = {}) {
  return request(path, { ...options, method: "POST" });
}

export function postJSON(path, body) {
  return request(path, { method: "POST", json: true, body });
}

export function postForm(path, formData) {
  return request(path, { method: "POST", form: true, body: formData });
}
