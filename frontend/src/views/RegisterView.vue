<script setup>
import { ref } from "vue";
import { useRouter, RouterLink } from "vue-router";
import { ArrowRight, LoaderCircle } from "@lucide/vue";
import { api } from "../api.js";

const router = useRouter();
const username = ref("");
const password = ref("");
const error = ref("");
const submitting = ref(false);

async function submit() {
  error.value = "";
  submitting.value = true;
  try {
    const registered = username.value.trim();
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
      <form class="login-form" @submit.prevent="submit">
        <label>
          <span>用户名</span>
          <input
            v-model.trim="username"
            name="username"
            autocomplete="username"
            maxlength="80"
            autofocus
            required
          />
        </label>
        <label>
          <span>密码</span>
          <input
            v-model="password"
            name="password"
            type="password"
            autocomplete="new-password"
            maxlength="128"
            required
          />
        </label>
        <p class="field-hint">密码至少 12 个字符</p>
        <p v-if="error" class="form-error" role="alert">{{ error }}</p>
        <button class="login-submit" type="submit" :disabled="submitting">
          <LoaderCircle v-if="submitting" :size="17" class="spin" aria-hidden="true" />
          <span>{{ submitting ? "正在创建" : "创建账号" }}</span>
          <ArrowRight v-if="!submitting" :size="17" aria-hidden="true" />
        </button>
      </form>
      <RouterLink class="login-register-link" to="/login">返回登录</RouterLink>
    </section>
  </main>
</template>
