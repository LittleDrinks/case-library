<template>
  <div class="app">
    <!-- Header -->
    <header class="app-header">
      <div class="header-inner">
        <!-- Branding -->
        <div class="brand">
          <div class="brand-logo">
            <div class="logo-shu">上大</div>
          </div>
          <div class="brand-text">
            <div class="brand-university">上海大学 / SHANGHAI UNIVERSITY</div>
            <div class="brand-wordmark">
              <span class="wordmark-red">强国有我</span>
              <span class="wordmark-black">思政案例库</span>
            </div>
          </div>
        </div>

        <!-- Navigation -->
        <nav class="main-nav">
          <a
            v-for="item in visibleNavItems"
            :key="item.id"
            :class="['nav-link', { active: currentView === item.id }]"
            href="javascript:void(0)"
            @click="navigate(item.id)"
          >
            {{ item.label }}
          </a>
        </nav>

        <!-- Right cluster: user actions -->
        <div class="header-actions">
          <template v-if="isLoggedIn()">
            <div class="user-chip">
              <span class="user-avatar">{{ userInitials }}</span>
              <span class="user-name">{{ displayName }}</span>
              <button type="button" class="btn-logout" @click="handleLogout">
                退出
              </button>
            </div>
          </template>
          <template v-else>
            <button type="button" class="btn-login" @click="showLogin = true">
              登录
            </button>
          </template>
        </div>
      </div>
    </header>

    <!-- Main content -->
    <main class="app-main">
      <HomeView v-if="currentView === 'home'" />
      <CaseLibraryView v-else-if="currentView === 'library'" />
      <CreateCaseView v-else-if="currentView === 'create'" />
      <MySubmissionsView v-else-if="currentView === 'submissions'" />
      <AdminReviewView v-else-if="currentView === 'admin'" />
    </main>

    <!-- Footer -->
    <footer class="app-footer">
      <p>© 上海大学 思政案例库</p>
    </footer>

    <!-- Login Modal -->
    <LoginModal v-if="showLogin" @close="showLogin = false" @success="onLoginSuccess" />

    <!-- Forced Password Change Modal (cannot dismiss) -->
    <PasswordChangeModal v-if="showPasswordChange" @success="onPasswordChanged" />
  </div>
</template>

<script setup>
import { ref, computed, watch } from "vue";
import {
  auth,
  isLoggedIn,
  isAdmin,
  mustChangePassword,
  currentUser,
  logout,
} from "./api/auth.js";
import LoginModal from "./components/LoginModal.vue";
import PasswordChangeModal from "./components/PasswordChangeModal.vue";
import HomeView from "./views/HomeView.vue";
import CaseLibraryView from "./views/CaseLibraryView.vue";
import CreateCaseView from "./views/CreateCaseView.vue";
import MySubmissionsView from "./views/MySubmissionsView.vue";
import AdminReviewView from "./views/AdminReviewView.vue";

const currentView = ref("home");
const showLogin = ref(false);

const showPasswordChange = computed(() => {
  return isLoggedIn() && mustChangePassword();
});

const displayName = computed(() => {
  const user = currentUser();
  return user?.nickname || user?.username || "";
});

const userInitials = computed(() => {
  const name = displayName.value;
  if (!name) return "?";
  return name.slice(0, 1).toUpperCase();
});

const allNavItems = [
  { id: "home", label: "首页", public: true },
  { id: "library", label: "案例库", public: true },
  { id: "create", label: "创建案例", public: false },
  { id: "submissions", label: "我的提交", public: false },
  { id: "admin", label: "审核管理", public: false, admin: true },
];

const visibleNavItems = computed(() => {
  return allNavItems.filter((item) => {
    if (item.admin && !isAdmin()) return false;
    if (!item.public && !isLoggedIn()) return false;
    return true;
  });
});

function navigate(viewId) {
  const item = allNavItems.find((i) => i.id === viewId);
  if (item && !item.public && !isLoggedIn()) {
    showLogin.value = true;
    return;
  }
  if (item && item.admin && !isAdmin()) {
    return;
  }
  currentView.value = viewId;
}

function onLoginSuccess() {
  showLogin.value = false;
}

function onPasswordChanged() {
  // Modal closes automatically via computed
}

function handleLogout() {
  logout();
  currentView.value = "home";
}

// Optional: sync with hash for basic URL state
function readHash() {
  const hash = window.location.hash.replace("#", "");
  const item = allNavItems.find((i) => i.id === hash);
  if (item) {
    navigate(hash);
  }
}

watch(currentView, (view) => {
  window.location.hash = view;
});

window.addEventListener("hashchange", readHash);
readHash();
</script>
