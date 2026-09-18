import { beforeEach, expect, it, vi } from "vitest";

const sessionState = { user: null, csrfToken: "", ready: false };
let restoreSessionMock;
let resetId = 0;

vi.mock("./api.js", () => ({ api: {} }));
vi.mock("./session.js", () => ({
  session: sessionState,
  restoreSession: (...args) => restoreSessionMock(...args),
}));

const { router } = await import("./router.js");

async function navigate(to) {
  await router.push(to);
  return router.currentRoute.value;
}

function loggedIn(user = { id: "u-1", role: "teacher" }) {
  restoreSessionMock = vi.fn(async () => {
    sessionState.user = user;
    sessionState.ready = true;
    return sessionState.user;
  });
}

beforeEach(async () => {
  sessionState.user = null;
  sessionState.csrfToken = "";
  sessionState.ready = false;
  restoreSessionMock = vi.fn(async () => {
    sessionState.ready = true;
    return null;
  });
  window.scrollTo = vi.fn();
  await router.push({ name: "home", query: { _testReset: String(++resetId) } });
});

it("restores the session before judging a protected route", async () => {
  loggedIn();
  const route = await navigate({ name: "my-cases" });
  expect(restoreSessionMock).toHaveBeenCalled();
  expect(route.name).toBe("my-cases");
});

it("redirects a protected route to login when no session is restored", async () => {
  const route = await navigate({ name: "my-cases" });
  expect(route.name).toBe("login");
  expect(route.query.redirect).toBe("/my-cases");
});

it("keeps non-admin users out of admin routes", async () => {
  loggedIn();
  const route = await navigate({ name: "admin-skills" });
  expect(route.name).toBe("home");
});

it("admits admins to admin routes", async () => {
  loggedIn({ id: "a-1", role: "admin" });
  const route = await navigate({ name: "admin-skills" });
  expect(route.name).toBe("admin-skills");
});

it("forces a pending password change before any other route", async () => {
  loggedIn({ id: "u-1", role: "teacher", mustChangePassword: true });
  const route = await navigate({ name: "my-cases" });
  expect(route.name).toBe("password-change");
});

it("allows staying on password-change only while the flag is set", async () => {
  loggedIn();
  const route = await navigate({ name: "password-change" });
  expect(route.name).toBe("home");
});

it("sends logged-in users away from the login page", async () => {
  loggedIn();
  const route = await navigate({ name: "login" });
  expect(route.name).toBe("home");
});
