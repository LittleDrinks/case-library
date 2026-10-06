<script setup>
import { ref } from "vue";
import { useRouter } from "vue-router";
import { KeyRound, LoaderCircle, LogOut } from "@lucide/vue";
import { changePassword, logout } from "../session.js";

const router = useRouter();
const currentPassword = ref("");
const newPassword = ref("");
const confirmation = ref("");
const error = ref("");
const submitting = ref(false);

async function submit() {
  error.value = "";
  if (newPassword.value !== confirmation.value) {
    error.value = "两次输入的新密码不一致";
    return;
  }
  submitting.value = true;
  try {
    await changePassword({ currentPassword: currentPassword.value, newPassword: newPassword.value });
    await router.replace("/login");
  } catch (reason) {
    error.value = reason.message || "密码修改失败";
  } finally {
    submitting.value = false;
  }
}

async function leave() {
  try {
    await logout();
  } finally {
    await router.replace("/login");
  }
}
</script>

<template>
  <main class="login-page">
    <section class="login-panel" aria-labelledby="password-title">
      <img class="login-logo" src="/shanghai-university-horizontal-logo.png" alt="上海大学" />
      <div class="login-heading">
        <h1 id="password-title">修改登录密码</h1>
        <p>首次登录改密</p>
      </div>
      <form class="login-form" @submit.prevent="submit">
        <label>
          <span>当前密码</span>
          <input v-model="currentPassword" type="password" autocomplete="current-password" required />
        </label>
        <label>
          <span>新密码</span>
          <input v-model="newPassword" type="password" autocomplete="new-password" minlength="12" maxlength="128" required />
        </label>
        <label>
          <span>确认新密码</span>
          <input v-model="confirmation" type="password" autocomplete="new-password" minlength="12" maxlength="128" required />
        </label>
        <p v-if="error" class="form-error" role="alert">{{ error }}</p>
        <button class="login-submit" type="submit" :disabled="submitting">
          <LoaderCircle v-if="submitting" :size="17" class="spin" aria-hidden="true" />
          <KeyRound v-else :size="17" aria-hidden="true" />
          <span>{{ submitting ? "保存中" : "保存新密码" }}</span>
        </button>
      </form>
      <button class="login-secondary" type="button" @click="leave">
        <LogOut :size="16" aria-hidden="true" />
        <span>退出登录</span>
      </button>
    </section>
  </main>
</template>
