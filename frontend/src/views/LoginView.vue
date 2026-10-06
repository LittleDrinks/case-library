<script setup>
import { ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { RouterLink } from "vue-router";
import CredentialForm from "../components/CredentialForm.vue";
import { login } from "../session.js";

const route = useRoute();
const router = useRouter();
const registeredUsername = typeof route.query.registered === "string"
  ? route.query.registered
  : "";
const username = ref(registeredUsername);
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
    const user = await login({ username: username.value.trim(), password: password.value });
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
      <p v-if="registeredUsername" class="form-success" role="status">账号创建成功，请登录</p>
      <CredentialForm
        v-model:username="username"
        v-model:password="password"
        :error="error"
        :submitting="submitting"
        password-autocomplete="current-password"
        submit-label="登录"
        submitting-label="登录中"
        @submit="submit"
      />
      <RouterLink class="login-register-link" to="/register">创建账号</RouterLink>
    </section>
  </main>
</template>
