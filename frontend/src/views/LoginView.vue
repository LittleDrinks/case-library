<script setup>
import { ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ArrowRight, LoaderCircle } from "@lucide/vue";
import { login } from "../session.js";

const route = useRoute();
const router = useRouter();
const username = ref("");
const password = ref("");
const error = ref("");
const submitting = ref(false);

function destination() {
  const target = String(route.query.redirect || "");
  const allowed = [
    "/my-cases", "/search", "/materials", "/ai-settings", "/workbench/",
    "/admin", "/admin/review/", "/admin/material-imports", "/admin/ai-settings",
  ];
  return allowed.some((prefix) => target.startsWith(prefix))
    ? target
    : "/";
}

async function submit() {
  error.value = "";
  submitting.value = true;
  try {
    const user = await login({ username: username.value, password: password.value });
    const target = user.mustChangePassword ? "/change-password" : destination();
    await router.replace(target);
  } catch (reason) {
    error.value = reason.message || "登录失败";
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <main class="login-page">
    <section class="login-panel" aria-labelledby="login-title">
      <img class="login-logo" src="/shanghai-university-horizontal-logo.png" alt="上海大学" />
      <div class="login-heading">
        <h1 id="login-title">“强国有我”思政案例库</h1>
        <p>账号登录</p>
      </div>
      <form class="login-form" @submit.prevent="submit">
        <label>
          <span>用户名</span>
          <input v-model.trim="username" name="username" autocomplete="username" autofocus required />
        </label>
        <label>
          <span>密码</span>
          <input v-model="password" name="password" type="password" autocomplete="current-password" required />
        </label>
        <p v-if="error" class="form-error" role="alert">{{ error }}</p>
        <button class="login-submit" type="submit" :disabled="submitting">
          <LoaderCircle v-if="submitting" :size="17" class="spin" aria-hidden="true" />
          <span>{{ submitting ? "登录中" : "登录" }}</span>
          <ArrowRight v-if="!submitting" :size="17" aria-hidden="true" />
        </button>
      </form>
    </section>
  </main>
</template>
