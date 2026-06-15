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

        <!-- Global header search -->
        <form class="global-search" @submit.prevent="submitHeaderSearch">
          <input
            v-model="headerSearchInput"
            type="text"
            placeholder="搜索案例…"
            aria-label="搜索案例"
          />
          <button type="submit" aria-label="查找案例">
            <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <circle cx="7" cy="7" r="5" />
              <path d="M11 11l3.5 3.5" />
            </svg>
          </button>
        </form>

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
      <CaseLibraryView v-else-if="currentView === 'library'" :search-trigger="searchTrigger" />
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

    <div class="toast-stack" aria-live="polite" aria-atomic="true">
      <div
        v-for="toast in toasts"
        :key="toast.id"
        :class="['toast', `toast-${toast.type}`]"
      >
        {{ toast.message }}
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onBeforeUnmount } from "vue";
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
import { TOAST_EVENT } from "./utils/toast.js";

const currentView = ref("home");
const showLogin = ref(false);
const toasts = ref([]);
let toastSeq = 0;

// Global header search state (passed to CaseLibraryView via prop)
const searchTrigger = ref({ keyword: "", nonce: 0 });
const headerSearchInput = ref("");

function submitHeaderSearch() {
  const kw = headerSearchInput.value.trim();
  searchTrigger.value = {
    keyword: kw,
    nonce: searchTrigger.value.nonce + 1,
  };
  headerSearchInput.value = "";
  navigate("library");
}

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
  currentView.value = "home";
  showLogin.value = true;
  handleToast({
    detail: {
      message: "密码已修改，请使用新密码重新登录。",
      type: "success",
    },
  });
}

function handleLogout() {
  logout();
  currentView.value = "home";
}

function handleToast(event) {
  const message = event.detail?.message || "";
  if (!message) return;
  const toast = {
    id: ++toastSeq,
    message,
    type: event.detail?.type || "info",
  };
  toasts.value = [...toasts.value, toast].slice(-4);
  window.setTimeout(() => {
    toasts.value = toasts.value.filter((item) => item.id !== toast.id);
  }, 3200);
}

// Optional: sync with hash for basic URL state
function readHash() {
  const hash = window.location.hash.replace("#", "");
  const viewId = hash.split("?")[0];
  const item = allNavItems.find((i) => i.id === viewId);
  if (item) {
    navigate(viewId);
  }
}

watch(currentView, (view) => {
  const hashView = window.location.hash.replace("#", "").split("?")[0];
  if (hashView !== view) {
    window.location.hash = view;
  }
});

window.addEventListener("hashchange", readHash);
readHash();

onMounted(() => {
  window.addEventListener(TOAST_EVENT, handleToast);
});

onBeforeUnmount(() => {
  window.removeEventListener(TOAST_EVENT, handleToast);
  window.removeEventListener("hashchange", readHash);
});
</script>
