import { createRouter, createWebHashHistory } from "vue-router";
import { restoreSession, session } from "./session.js";
import ChangePasswordView from "./views/ChangePasswordView.vue";
import AISettingsView from "./views/AISettingsView.vue";
import AdminAISettingsView from "./views/AdminAISettingsView.vue";
import AdminDashboardView from "./views/AdminDashboardView.vue";
import CaseDetailView from "./views/CaseDetailView.vue";
import HomeView from "./views/HomeView.vue";
import LoginView from "./views/LoginView.vue";
import MaterialImportView from "./views/MaterialImportView.vue";
import MaterialExplorerView from "./views/MaterialExplorerView.vue";
import MyCasesView from "./views/MyCasesView.vue";
import SearchView from "./views/SearchView.vue";
import WorkbenchView from "./views/WorkbenchView.vue";

const routes = [
  { path: "/", name: "home", component: HomeView },
  { path: "/login", name: "login", component: LoginView },
  { path: "/search", name: "search", component: SearchView },
  {
    path: "/materials",
    name: "materials",
    component: MaterialExplorerView,
    meta: { requiresAuth: true },
  },
  {
    path: "/my-cases",
    name: "my-cases",
    component: MyCasesView,
    meta: { requiresAuth: true },
  },
  {
    path: "/change-password",
    name: "password-change",
    component: ChangePasswordView,
    meta: { requiresAuth: true },
  },
  {
    path: "/ai-settings",
    name: "ai-settings",
    component: AISettingsView,
    meta: { requiresAuth: true },
  },
  {
    path: "/workbench/:id",
    name: "workbench",
    component: WorkbenchView,
    meta: { requiresAuth: true },
  },
  { path: "/cases/:id", name: "case-public", component: CaseDetailView },
  {
    path: "/admin",
    name: "admin-dashboard",
    component: AdminDashboardView,
    meta: { requiresAuth: true, requiresAdmin: true },
  },
  {
    path: "/admin/review/:id",
    name: "case-review",
    component: WorkbenchView,
    meta: { requiresAuth: true, requiresAdmin: true },
  },
  {
    path: "/admin/material-imports",
    name: "material-imports",
    component: MaterialImportView,
    meta: { requiresAuth: true, requiresAdmin: true },
  },
  {
    path: "/admin/ai-settings",
    name: "admin-ai-settings",
    component: AdminAISettingsView,
    meta: { requiresAuth: true, requiresAdmin: true },
  },
  { path: "/:pathMatch(.*)*", redirect: "/" },
];

export const router = createRouter({
  history: createWebHashHistory(),
  routes,
  scrollBehavior: () => ({ top: 0 }),
});

router.beforeEach(async (to) => {
  await restoreSession();
  if (session.user?.mustChangePassword && to.name !== "password-change") {
    return { name: "password-change" };
  }
  if (to.meta.requiresAuth && !session.user) {
    return { name: "login", query: { redirect: to.fullPath } };
  }
  if (to.meta.requiresAdmin && session.user?.role !== "admin") {
    return { name: "home" };
  }
  if (to.name === "password-change" && !session.user?.mustChangePassword) {
    return { name: "home" };
  }
  if (to.name === "login" && session.user) {
    return { name: "home" };
  }
  return true;
});
