/**
 * Centralized auth state and token persistence.
 *
 * Uses clearly app-owned localStorage keys.
 * Provides reactive auth state, login/logout, and password change helpers.
 */

import { reactive, readonly } from "vue";
import { postForm, get } from "./client.js";

const TOKEN_KEY = "case_library_auth_token";
const USER_KEY = "case_library_auth_user";

function loadUser() {
  try {
    const raw = localStorage.getItem(USER_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

const state = reactive({
  token: localStorage.getItem(TOKEN_KEY) || null,
  user: loadUser(),
  loading: false,
  error: null,
});

export const auth = readonly(state);

export function isLoggedIn() {
  return !!state.token && !!state.user;
}

export function isAdmin() {
  return state.user?.role === "admin";
}

export function mustChangePassword() {
  return state.user?.must_change_password === true;
}

export function currentUser() {
  return state.user;
}

function setAuth(token, user) {
  state.token = token;
  state.user = user;
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(USER_KEY, JSON.stringify(user));
}

function clearAuth() {
  state.token = null;
  state.user = null;
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}

/**
 * Login with username and password.
 *
 * Backend contract:
 *   POST /api/auth/login
 *   Content-Type: application/x-www-form-urlencoded
 *   Body: username, password
 *   Response: { success: bool, data: { id, username, role, nickname, must_change_password, status, token } }
 */
export async function login(username, password) {
  state.loading = true;
  state.error = null;
  try {
    const data = await postForm("/api/auth/login", { username, password });
    if (data.success && data.data) {
      const { token, ...user } = data.data;
      setAuth(token, user);
      return { success: true };
    }
    throw new Error(data.message || "登录失败，请检查用户名和密码");
  } catch (err) {
    state.error = err.message || "登录失败";
    return { success: false, error: state.error };
  } finally {
    state.loading = false;
  }
}

/**
 * Change password.
 *
 * Backend contract:
 *   POST /api/auth/change-password
 *   Content-Type: application/x-www-form-urlencoded
 *   Body: username, old_password, new_password
 */
export async function changePassword(username, oldPassword, newPassword) {
  state.loading = true;
  state.error = null;
  try {
    const data = await postForm("/api/auth/change-password", {
      username,
      old_password: oldPassword,
      new_password: newPassword,
    });
    if (data.success) {
      if (state.user) {
        const updated = { ...state.user, must_change_password: false };
        state.user = updated;
        localStorage.setItem(USER_KEY, JSON.stringify(updated));
      }
      return { success: true };
    }
    throw new Error(data.message || "修改密码失败");
  } catch (err) {
    state.error = err.message || "修改密码失败";
    return { success: false, error: state.error };
  } finally {
    state.loading = false;
  }
}

export function logout() {
  clearAuth();
}

/**
 * Fetch constants / labels from the backend.
 */
export async function fetchConstants() {
  return get("/api/constants");
}
