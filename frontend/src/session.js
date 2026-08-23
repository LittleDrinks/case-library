import { reactive } from "vue";
import { api } from "./api.js";

export const session = reactive({
  user: null,
  csrfToken: "",
  ready: false,
});

let restoration;

function assignSession(payload) {
  session.user = payload.user;
  session.csrfToken = payload.csrfToken;
}

function clearSession() {
  session.user = null;
  session.csrfToken = "";
}

export async function restoreSession() {
  if (session.ready) return session.user;
  restoration ||= restoreFromServer();
  return restoration;
}

async function restoreFromServer() {
  try {
    assignSession(await api.session());
  } catch (error) {
    if (error.status !== 401) console.error(error);
    clearSession();
  } finally {
    session.ready = true;
  }
  return session.user;
}

export async function login(credentials) {
  assignSession(await api.login(credentials));
  session.ready = true;
  return session.user;
}

export async function changePassword(passwords) {
  await api.changePassword(passwords, session.csrfToken);
  clearSession();
}

export async function logout() {
  try {
    await api.logout(session.csrfToken);
  } finally {
    clearSession();
  }
}
