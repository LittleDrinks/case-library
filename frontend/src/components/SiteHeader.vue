<script setup>
import { Bot, House, LibraryBig, LogIn, LogOut, Search, Settings } from "@lucide/vue";
import { computed } from "vue";
import { useRoute, useRouter } from "vue-router";
import { logout, session } from "../session.js";

const router = useRouter();
const route = useRoute();
const adminActive = computed(() => route.path.startsWith("/admin"));

async function leave() {
  try {
    await logout();
  } finally {
    await router.replace("/login");
  }
}
</script>

<template>
  <a class="skip-link" href="#main-content">跳到主要内容</a>
  <header class="site-header">
    <RouterLink class="site-brand" to="/" aria-label="“强国有我”思政案例库首页">
      <img src="/shanghai-university-horizontal-logo.png" alt="上海大学" />
      <span>“强国有我”思政案例库</span>
    </RouterLink>
    <nav class="site-nav" aria-label="主导航">
      <RouterLink to="/" aria-label="首页"><House :size="16" aria-hidden="true" /><span>首页</span></RouterLink>
      <RouterLink v-if="session.user" to="/my-cases" aria-label="我的案例"><LibraryBig :size="16" aria-hidden="true" /><span>我的案例</span></RouterLink>
      <RouterLink to="/search" aria-label="资源检索"><Search :size="16" aria-hidden="true" /><span>资源检索</span></RouterLink>
      <RouterLink v-if="session.user?.role === 'admin'" to="/admin" :class="{ 'admin-active': adminActive }" aria-label="管理后台"><Settings :size="16" aria-hidden="true" /><span>管理后台</span></RouterLink>
    </nav>
    <div v-if="session.user" class="site-account">
      <span>{{ session.user?.name }}</span>
      <RouterLink class="icon-button" :to="{ name: 'ai-settings' }" title="AI 模型设置" aria-label="AI 模型设置">
        <Bot :size="17" aria-hidden="true" />
      </RouterLink>
      <button class="icon-button" type="button" title="退出登录" aria-label="退出登录" @click="leave">
        <LogOut :size="17" aria-hidden="true" />
      </button>
    </div>
    <RouterLink v-else class="icon-button" to="/login" title="登录" aria-label="登录">
      <LogIn :size="17" aria-hidden="true" />
    </RouterLink>
  </header>
</template>
