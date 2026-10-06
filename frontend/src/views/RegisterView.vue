<script setup>
import { ref } from "vue";
import { useRouter, RouterLink } from "vue-router";
import CredentialForm from "../components/CredentialForm.vue";
import { api } from "../api.js";

const router = useRouter();
const username = ref("");
const password = ref("");
const error = ref("");
const submitting = ref(false);

async function submit() {
  error.value = "";
  const registered = username.value.trim();
  if (!registered) {
    error.value = "请输入用户名";
    return;
  }
  submitting.value = true;
  try {
    await api.register({ username: registered, password: password.value });
    await router.replace({ name: "login", query: { registered } });
  } catch (reason) {
    error.value = reason.message || "注册失败";
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <main class="login-page">
    <section class="login-panel" aria-labelledby="register-title">
      <img class="login-logo" src="/shanghai-university-horizontal-logo.png" alt="上海大学" />
      <div class="login-heading">
        <h1 id="register-title">“强国有我”思政案例库</h1>
        <p>创建账号</p>
      </div>
      <CredentialForm
        v-model:username="username"
        v-model:password="password"
        :error="error"
        :submitting="submitting"
        password-autocomplete="new-password"
        password-hint="密码至少 12 个字符，且不超过 72 字节"
        submit-label="创建账号"
        submitting-label="正在创建"
        @submit="submit"
      />
      <RouterLink class="login-register-link" to="/login">返回登录</RouterLink>
    </section>
  </main>
</template>
